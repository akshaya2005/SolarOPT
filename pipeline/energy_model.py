"""Historical AC energy from NSRDB weather using pvlib's physical PV models.

Solar position -> Perez-Driesse plane-of-array irradiance -> physical incidence
loss -> SAPM cell temperature -> PVWatts DC -> losses -> PVWatts inverter.
The optimizer consumes one annual kWh value per location/configuration/year.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

from pipeline.fetch_nsrdb import DEFAULT_COORD_TOL, fetch_location_year, validate_conus_coordinates
from pipeline.preprocess import PHYSICAL_RANGES, PROCESSED_DIR, load_and_clean
from pipeline.system_config import DEFAULT_SYSTEM_CONFIG, TEMPERATURE_MODELS, SystemConfig

logger = logging.getLogger(__name__)
WEATHER_COLUMNS = ("ghi", "dni", "dhi", "temp_air", "wind_speed", "surface_albedo")
DEFAULT_TILTS = tuple(range(0, 91, 5))
DEFAULT_AZIMUTHS = tuple(range(90, 271, 10))


def _angles(values: Iterable[float], name: str, maximum: float) -> list[float]:
    result = [float(v) for v in values]
    if not result or any(not math.isfinite(v) or not 0 <= v <= maximum for v in result):
        raise ValueError(f"{name} must contain finite angles between 0 and {maximum}")
    if maximum == 360:
        result = [v % 360 for v in result]
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _validate_weather(weather: pd.DataFrame, year: int | None = None) -> None:
    """Reject missing data instead of silently turning it into zero production."""
    if weather.empty or not weather.columns.is_unique:
        raise ValueError("weather must be nonempty with unique columns")
    missing = set(WEATHER_COLUMNS) - set(weather.columns)
    if missing:
        raise ValueError(f"Missing weather columns: {sorted(missing)}")
    index = weather.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("weather must have a timezone-aware UTC DatetimeIndex")
    if str(index.tz) != "UTC" or index.hasnans or not index.is_unique:
        raise ValueError("weather timestamps must be unique, nonmissing and in UTC")
    if not index.is_monotonic_increasing or (
        len(index) > 1 and not ((index[1:] - index[:-1]) == pd.Timedelta(hours=1)).all()
    ):
        raise ValueError("weather must have consecutive hourly timestamps")
    for col in WEATHER_COLUMNS:
        if not pd.api.types.is_numeric_dtype(weather[col]):
            raise ValueError(f"{col} must be numeric")
        low, high = PHYSICAL_RANGES[col]
        if (
            weather[col].isna().any()
            or not np.isfinite(weather[col]).all()
            or not weather[col].between(low, high).all()
        ):
            raise ValueError(f"{col} must be finite and between {low} and {high}")
    for key, low, high in (
        ("latitude", -90, 90),
        ("longitude", -180, 180),
        ("elevation", -500, 9000),
    ):
        value = weather.attrs.get(key)
        if value is None or not math.isfinite(float(value)) or not low <= float(value) <= high:
            raise ValueError(f"weather metadata requires valid {key}")
    if year is not None:
        start = pd.Timestamp(year=year, month=1, day=1, tz="UTC")
        # Preserve native timestamp phase, including NSRDB's usual HH:30.
        offset = index[0] - start
        count = (366 if calendar.isleap(year) else 365) * 24
        if not pd.Timedelta(0) <= offset < pd.Timedelta(hours=1) or len(index) != count:
            raise ValueError(f"weather must cover the full UTC year {year}, including leap day")
        expected = pd.date_range(start + offset, periods=count, freq="h")
        if not index.equals(expected) or weather.attrs.get("year") != year:
            raise ValueError(f"weather timestamps and metadata must match requested year {year}")


def _solar_inputs(weather: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    site = pvlib.location.Location(
        latitude=float(weather.attrs["latitude"]),
        longitude=float(weather.attrs["longitude"]),
        altitude=float(weather.attrs["elevation"]),
        tz="UTC",
    )
    solar = site.get_solarposition(weather.index, temperature=weather["temp_air"])
    extra = pvlib.irradiance.get_extra_radiation(weather.index)
    airmass = pvlib.atmosphere.get_relative_airmass(solar["apparent_zenith"])
    return solar, extra, airmass


def _simulate(
    weather: pd.DataFrame,
    tilt: float,
    azimuth: float,
    system: SystemConfig,
    solar_inputs: tuple[pd.DataFrame, pd.Series, pd.Series],
) -> pd.DataFrame:
    solar, extra, airmass = solar_inputs
    # Evaluate transposition only above the apparent horizon. Nighttime airmass
    # is undefined; do not use blanket fillna(0), which could hide daytime errors.
    daylight = solar["apparent_zenith"] < 90
    w = weather.loc[daylight]
    s = solar.loc[daylight]
    out = pd.DataFrame(
        0.0,
        index=weather.index,
        columns=["poa_global", "effective_irradiance", "temp_cell", "dc_w", "ac_w", "kwh"],
    )
    out["temp_cell"] = weather["temp_air"].astype(float)
    if daylight.any():
        poa = pvlib.irradiance.get_total_irradiance(
            tilt,
            azimuth,
            s["apparent_zenith"],
            s["azimuth"],
            w["dni"],
            w["ghi"],
            w["dhi"],
            dni_extra=extra.loc[daylight],
            airmass=airmass.loc[daylight],
            albedo=w["surface_albedo"],
            model="perez-driesse",
        )
        aoi = pvlib.irradiance.aoi(tilt, azimuth, s["apparent_zenith"], s["azimuth"])
        # Same direct/diffuse treatment as ModelChain: IAM on direct irradiance;
        # diffuse passes through, with no additional spectral correction.
        effective = poa["poa_direct"] * pvlib.iam.physical(aoi) + poa["poa_diffuse"]
        cell = pvlib.temperature.sapm_cell(
            poa["poa_global"],
            w["temp_air"],
            w["wind_speed"],
            **TEMPERATURE_MODELS[system.temperature_model],
        )
        dc = pvlib.pvsystem.pvwatts_dc(
            effective,
            cell,
            pdc0=system.capacity_kw * 1000,
            gamma_pdc=system.gamma_pdc,
        ).clip(lower=0) * (1 - system.losses_percent / 100)
        # pvlib inverter pdc0 is the DC input limit, NOT the array STC rating.
        ac_rating = system.capacity_kw * 1000 / system.dc_ac_ratio
        ac = pvlib.inverter.pvwatts(
            dc,
            pdc0=ac_rating / system.inverter_efficiency,
            eta_inv_nom=system.inverter_efficiency,
        )
        for name, values in (
            ("poa_global", poa["poa_global"]),
            ("effective_irradiance", effective),
            ("temp_cell", cell),
            ("dc_w", dc),
            ("ac_w", ac),
        ):
            out.loc[daylight, name] = values
    if not np.isfinite(out.to_numpy()).all() or (out[["dc_w", "ac_w"]] < 0).any().any():
        raise ValueError("PV calculation produced invalid power or nonfinite intermediate values")
    # Each observation represents one hour. Sum rectangular hourly energy,
    # including the final interval; trapezoidal integration would lose endpoints.
    out["kwh"] = out["ac_w"] / 1000
    return out


def simulate_configuration(
    weather: pd.DataFrame,
    tilt: float,
    azimuth: float,
    *,
    system: SystemConfig | None = None,
) -> pd.DataFrame:
    """Return hourly POA (W/m²), cell temperature (°C), power (W), and AC kWh.

    Accepts consecutive hourly periods of any length for diagnostics. Annual
    completeness is enforced separately by compute_energy_table.
    Tilt is from horizontal; azimuth is clockwise from north (south = 180°).
    """
    _validate_weather(weather)
    tilt = _angles([tilt], "tilt", 90)[0]
    azimuth = _angles([azimuth], "azimuth", 360)[0]
    return _simulate(
        weather, tilt, azimuth, system or DEFAULT_SYSTEM_CONFIG, _solar_inputs(weather)
    )


def compute_energy_table(
    location: dict,
    years: Iterable[int],
    tilts: Iterable[float],
    azimuths: Iterable[float],
    *,
    system: SystemConfig | None = None,
    weather_by_year: Mapping[int, pd.DataFrame] | None = None,
    raw_dir: Path | None = None,
) -> pd.DataFrame:
    """Fetch/clean weather once per year and evaluate every fixed orientation.

    location = {name, lat, lon}. Supply weather_by_year to use preprocessed
    weather entirely offline. Returns the optimizer's five-column schema with
    system assumptions and source provenance in attrs (preserved by Parquet).
    """
    if not {"name", "lat", "lon"}.issubset(location) or not str(location["name"]).strip():
        raise ValueError("location requires a nonempty name, lat and lon")
    lat, lon = float(location["lat"]), float(location["lon"])
    validate_conus_coordinates(lat, lon)
    years = list(years)
    if not years or any(isinstance(y, bool) or not isinstance(y, Integral) for y in years):
        raise ValueError("years must be a nonempty iterable of integers")
    years = [int(y) for y in years]
    if len(set(years)) != len(years) or any(not 1900 <= y <= 2200 for y in years):
        raise ValueError("years must be unique and between 1900 and 2200")
    tilts = _angles(tilts, "tilts", 90)
    azimuths = _angles(azimuths, "azimuths", 360)
    system = system or DEFAULT_SYSTEM_CONFIG
    if weather_by_year is not None and set(years) - set(weather_by_year):
        raise ValueError("weather_by_year must include every requested year")
    rows, sources = [], {}
    grid_point = None
    for year in sorted(years):
        if weather_by_year is None:
            raw_path = fetch_location_year(lat, lon, year, raw_dir=raw_dir)
            weather = load_and_clean(raw_path)
        else:
            weather = weather_by_year[year]
        _validate_weather(weather, year)
        point = tuple(float(weather.attrs[k]) for k in ("latitude", "longitude", "elevation"))
        if abs(point[0] - lat) > DEFAULT_COORD_TOL or abs(point[1] - lon) > DEFAULT_COORD_TOL:
            raise ValueError("Weather grid point does not match the requested location")
        if grid_point is not None and not np.allclose(point, grid_point, atol=1e-6, rtol=0):
            raise ValueError("All weather years must use the same grid point and elevation")
        grid_point = point
        sources[str(year)] = {
            "latitude": point[0],
            "longitude": point[1],
            "elevation": point[2],
            "source_version": str(weather.attrs.get("source_version", "unknown")),
            "location_id": str(weather.attrs.get("location_id", "")),
            "records": len(weather),
            "start": str(weather.index[0]),
            "end": str(weather.index[-1]),
        }
        solar_inputs = _solar_inputs(weather)
        for tilt in tilts:
            for azimuth in azimuths:
                hourly = _simulate(weather, tilt, azimuth, system, solar_inputs)
                rows.append(
                    (str(location["name"]), tilt, azimuth, year, float(hourly["kwh"].sum()))
                )
        logger.info(
            "Modeled %s: %d configurations for %d",
            location["name"],
            len(tilts) * len(azimuths),
            year,
        )
    table = pd.DataFrame(rows, columns=["location", "tilt", "azimuth", "year", "kwh"])
    table.attrs = {
        "system": asdict(system),
        "energy_basis": "AC kWh",
        "years": sorted(years),
        "requested_location": {"name": str(location["name"]), "lat": lat, "lon": lon},
        "weather_sources": sources,
        "pvlib_version": pvlib.__version__,
        "models": {
            "transposition": "perez-driesse",
            "temperature": "sapm",
            "dc": "pvwatts",
            "inverter": "pvwatts",
            "aoi": "physical",
            "spectral": "none",
        },
    }
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estimate historical AC energy from NSRDB weather."
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--tilts", type=float, nargs="+", default=DEFAULT_TILTS)
    parser.add_argument("--azimuths", type=float, nargs="+", default=DEFAULT_AZIMUTHS)
    parser.add_argument("--capacity-kw", type=float, default=DEFAULT_SYSTEM_CONFIG.capacity_kw)
    parser.add_argument("--dc-ac-ratio", type=float, default=DEFAULT_SYSTEM_CONFIG.dc_ac_ratio)
    parser.add_argument(
        "--losses-percent", type=float, default=DEFAULT_SYSTEM_CONFIG.losses_percent
    )
    parser.add_argument(
        "--inverter-efficiency", type=float, default=DEFAULT_SYSTEM_CONFIG.inverter_efficiency
    )
    parser.add_argument("--gamma-pdc", type=float, default=DEFAULT_SYSTEM_CONFIG.gamma_pdc)
    parser.add_argument(
        "--temperature-model",
        choices=list(TEMPERATURE_MODELS),
        default=DEFAULT_SYSTEM_CONFIG.temperature_model,
    )
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        system = SystemConfig(
            capacity_kw=args.capacity_kw,
            dc_ac_ratio=args.dc_ac_ratio,
            losses_percent=args.losses_percent,
            inverter_efficiency=args.inverter_efficiency,
            gamma_pdc=args.gamma_pdc,
            temperature_model=args.temperature_model,
        )
        table = compute_energy_table(
            {"name": args.name, "lat": args.lat, "lon": args.lon},
            args.years,
            args.tilts,
            args.azimuths,
            system=system,
            raw_dir=args.raw_dir,
        )
        slug = re.sub(r"[^a-z0-9]+", "_", args.name.lower()).strip("_") or "location"
        output = args.output or PROCESSED_DIR / f"energy_{slug}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(output, engine="pyarrow", index=False)
        print(f"Saved {len(table)} annual AC energy estimates to {output}")
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        logger.error("Energy estimation failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
