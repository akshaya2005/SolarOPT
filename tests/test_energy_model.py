"""Physics, annual integration, and fetch-to-optimizer integration checks (offline)."""

from dataclasses import asdict, replace

import numpy as np
import pandas as pd
import pvlib
import pytest

from pipeline import energy_model
from pipeline.energy_model import compute_energy_table, simulate_configuration
from pipeline.optimize import recommend_configuration
from pipeline.system_config import DEFAULT_SYSTEM_CONFIG, TEMPERATURE_MODELS, SystemConfig

LOCATION = {"name": "Denver, CO", "lat": 39.62, "lon": -104.61}


def weather_for(index):
    site = pvlib.location.Location(LOCATION["lat"], LOCATION["lon"], altitude=1797)
    weather = site.get_clearsky(index)
    weather["temp_air"] = 20.0
    weather["wind_speed"] = 2.0
    weather["surface_albedo"] = 0.2
    weather.index.name = "timestamp"
    weather.attrs = {
        "latitude": LOCATION["lat"],
        "longitude": LOCATION["lon"],
        "elevation": 1797.0,
        "year": int(index[0].year),
        "source_version": "synthetic-clear-sky",
        "location_id": "test",
    }
    return weather


@pytest.fixture
def weather():
    return weather_for(pd.date_range("2023-06-20 00:30", periods=72, freq="h", tz="UTC"))


def test_physical_behavior_and_input_preservation(weather):
    original = weather.copy(deep=True)
    south = simulate_configuration(weather, 30, 180)
    night = weather["ghi"] == 0
    assert (south.loc[night, ["ac_w", "dc_w", "kwh"]] == 0).all().all()
    assert np.isfinite(south.to_numpy()).all()
    assert south["kwh"].sum() > 0
    assert south["ac_w"].max() <= (
        DEFAULT_SYSTEM_CONFIG.capacity_kw * 1000 / DEFAULT_SYSTEM_CONFIG.dc_ac_ratio
    )
    pd.testing.assert_frame_equal(weather, original)
    assert weather.attrs == original.attrs
    # A horizontal module has no preferred compass direction.
    east = simulate_configuration(weather, 0, 90)
    west = simulate_configuration(weather, 0, 270)
    np.testing.assert_allclose(east["ac_w"], west["ac_w"], atol=1e-9)


def test_temperature_wind_reflectivity_and_capacity_affect_energy(weather):
    system = SystemConfig(dc_ac_ratio=0.8)

    def energy(frame, config=system):
        return simulate_configuration(frame, 60, 180, system=config)["kwh"].sum()

    base = energy(weather)
    assert energy(weather.assign(temp_air=45)) < base
    assert energy(weather.assign(wind_speed=10)) > base
    assert energy(weather.assign(surface_albedo=0.8)) > base
    assert energy(weather, replace(system, losses_percent=30)) < base
    assert energy(weather, replace(system, capacity_kw=5)) == pytest.approx(5 * base)


def test_agrees_with_independently_configured_pvlib_modelchain(weather):
    config = SystemConfig()
    dc_rating = config.capacity_kw * 1000
    module = {"pdc0": dc_rating, "gamma_pdc": config.gamma_pdc}
    losses = {
        key: 0
        for key in [
            "soiling",
            "shading",
            "snow",
            "mismatch",
            "wiring",
            "connections",
            "lid",
            "nameplate_rating",
            "age",
            "availability",
        ]
    }
    losses["soiling"] = config.losses_percent  # Equivalent aggregate derate for this comparison.
    system = pvlib.pvsystem.PVSystem(
        surface_tilt=35,
        surface_azimuth=180,
        module_parameters=module,
        inverter_parameters={
            "pdc0": dc_rating / config.dc_ac_ratio / config.inverter_efficiency,
            "eta_inv_nom": config.inverter_efficiency,
        },
        temperature_model_parameters=TEMPERATURE_MODELS[config.temperature_model],
        losses_parameters=losses,
    )
    site = pvlib.location.Location(LOCATION["lat"], LOCATION["lon"], altitude=1797)
    chain = pvlib.modelchain.ModelChain(
        system,
        site,
        dc_model="pvwatts",
        ac_model="pvwatts",
        aoi_model="physical",
        spectral_model="no_loss",
        temperature_model="sapm",
        losses_model="pvwatts",
        transposition_model="perez-driesse",
    )
    chain.run_model(weather.rename(columns={"surface_albedo": "albedo"}))
    modeled = simulate_configuration(weather, 35, 180)
    daylight = chain.results.solar_position["apparent_zenith"] < 90
    np.testing.assert_allclose(
        modeled.loc[daylight, "ac_w"], chain.results.ac.loc[daylight], rtol=1e-8, atol=1e-8
    )


@pytest.mark.parametrize("year,hours", [(2023, 8760), (2024, 8784)])
def test_annual_integration_and_stc_conversion(year, hours, monkeypatch, tmp_path):
    index = pd.date_range(f"{year}-01-01 00:30", periods=hours, freq="h", tz="UTC")
    weather = weather_for(index).assign(ghi=1000.0, dni=800.0, dhi=200.0)
    # Controlled overhead sun: horizontal POA is 1000 W/m², IAM is 1.
    # gamma=0 removes temperature dependence; inverter at rated input is 96%.
    solar = pd.DataFrame({"apparent_zenith": 0.0, "azimuth": 180.0}, index=index)
    monkeypatch.setattr(
        energy_model,
        "_solar_inputs",
        lambda _: (solar, pd.Series(1367.0, index=index), pd.Series(1.0, index=index)),
    )
    config = SystemConfig(gamma_pdc=0, losses_percent=0, dc_ac_ratio=1 / 0.96)
    table = compute_energy_table(
        LOCATION, [year], [0], [180], system=config, weather_by_year={year: weather}
    )
    assert table.loc[0, "kwh"] == pytest.approx(hours * 0.96)
    assert table.columns.tolist() == ["location", "tilt", "azimuth", "year", "kwh"]
    path = tmp_path / "energy.parquet"
    table.to_parquet(path, index=False)
    reloaded = pd.read_parquet(path)
    assert reloaded.attrs == table.attrs
    assert reloaded.attrs["weather_sources"][str(year)]["records"] == hours


def test_inverter_clips_at_ac_rating(weather):
    frame = weather.assign(ghi=1500.0, dni=0.0, dhi=1500.0)
    result = simulate_configuration(
        frame, 0, 180, system=SystemConfig(dc_ac_ratio=2, gamma_pdc=0, losses_percent=0)
    )
    assert result["ac_w"].max() == pytest.approx(500)


def test_multiple_years_generators_and_consistent_grid(monkeypatch):
    frames = {
        year: weather_for(pd.date_range(f"{year}-01-01 00:30", periods=8760, freq="h", tz="UTC"))
        for year in (2022, 2023)
    }

    def unexpected(*args, **kwargs):
        pytest.fail("Preprocessed weather must not trigger a network request")

    monkeypatch.setattr(energy_model, "fetch_location_year", unexpected)
    table = compute_energy_table(
        LOCATION, iter([2023, 2022]), iter([20, 35]), iter([90, 180]), weather_by_year=frames
    )
    assert table.groupby("year").size().to_dict() == {2022: 4, 2023: 4}
    result = recommend_configuration(table, [2022], latitude=39.62)
    assert set(result["per_year"]) == {"2022", "2023"}
    assert np.isfinite(result["held_out_test_score"])
    frames[2023].attrs["latitude"] += 0.01
    with pytest.raises(ValueError, match="same grid point"):
        compute_energy_table(LOCATION, [2022, 2023], [35], [180], weather_by_year=frames)


def test_missing_year_in_offline_mapping_and_daytime_calculation_error(weather, monkeypatch):
    with pytest.raises(ValueError, match="every requested year"):
        compute_energy_table(LOCATION, [2022, 2023], [30], [180], weather_by_year={2023: weather})
    monkeypatch.setattr(pvlib.inverter, "pvwatts", lambda dc, **kwargs: dc * np.nan)
    with pytest.raises(ValueError, match="nonfinite"):
        simulate_configuration(weather, 30, 180)


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {
            "capacity_kw": 5.0,
            "dc_ac_ratio": 1.1,
            "inverter_efficiency": 0.97,
            "gamma_pdc": -0.0035,
            "losses_percent": 10.0,
            "temperature_model": "close_mount_glass_glass",
        },
    ],
)
def test_fetch_preprocess_grid_cli_and_optimizer(sample_csv_path, tmp_path, monkeypatch, settings):
    calls = []

    def fetch(lat, lon, year, **kwargs):
        calls.append((lat, lon, year))
        return sample_csv_path

    monkeypatch.setattr(energy_model, "fetch_location_year", fetch)
    output = tmp_path / "energy.parquet"
    config_args = []
    for name, value in settings.items():
        config_args.extend([f"--{name.replace('_', '-')}", str(value)])
    assert (
        energy_model.main(
            [
                "--name",
                "Denver, CO",
                "--lat",
                "39.62",
                "--lon",
                "-104.61",
                "--years",
                "2023",
                "--tilts",
                "0",
                "35",
                "--azimuths",
                "90",
                "180",
                "--output",
                str(output),
            ]
            + config_args
        )
        == 0
    )
    assert calls == [(39.62, -104.61, 2023)]
    table = pd.read_parquet(output)
    assert table.attrs["system"] == asdict(SystemConfig(**settings))
    assert len(table) == 4
    assert not table.duplicated(["tilt", "azimuth", "year"]).any()
    assert np.isfinite(table["kwh"]).all()
    assert recommend_configuration(table, [2023], latitude=39.62)["score"] > 0


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda w: w.drop(columns="dni"), "Missing weather"),
        (lambda w: w.assign(ghi=np.nan), "ghi must be finite"),
        (lambda w: w.assign(dni=np.inf), "dni must be finite"),
        (lambda w: w.assign(surface_albedo=1.1), "surface_albedo"),
        (lambda w: w.assign(wind_speed=-1), "wind_speed"),
        (lambda w: w.iloc[[0, 0]], "unique"),
        (lambda w: w.iloc[[0, 2]], "hourly"),
        (lambda w: w.iloc[::-1], "hourly"),
        (lambda w: w.set_axis(w.index.tz_localize(None)), "timezone-aware"),
    ],
)
def test_rejects_invalid_weather(weather, mutate, match):
    with pytest.raises(ValueError, match=match):
        simulate_configuration(mutate(weather), 30, 180)


def test_rejects_partial_wrong_year_and_wrong_location(weather):
    with pytest.raises(ValueError, match="full UTC year"):
        compute_energy_table(LOCATION, [2023], [30], [180], weather_by_year={2023: weather})
    full = weather_for(pd.date_range("2023-01-01 00:30", periods=8760, freq="h", tz="UTC"))
    with pytest.raises(ValueError, match="full UTC year"):
        compute_energy_table(LOCATION, [2022], [30], [180], weather_by_year={2022: full})
    full.attrs["latitude"] = 40.0
    with pytest.raises(ValueError, match="grid point"):
        compute_energy_table(LOCATION, [2023], [30], [180], weather_by_year={2023: full})
    del full.attrs["latitude"]
    with pytest.raises(ValueError, match="metadata"):
        simulate_configuration(full, 30, 180)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capacity_kw": 0},
        {"dc_ac_ratio": -1},
        {"inverter_efficiency": 1.1},
        {"losses_percent": 100},
        {"gamma_pdc": np.nan},
        {"temperature_model": "unknown"},
        {"capacity_kw": "5"},
        {"capacity_kw": True},
        {"losses_percent": None},
        {"temperature_model": []},
    ],
)
def test_rejects_invalid_system(kwargs):
    with pytest.raises(ValueError):
        SystemConfig(**kwargs)


@pytest.mark.parametrize(
    "years,tilts,azimuths",
    [
        ([], [30], [180]),
        ([2023, 2023], [30], [180]),
        ([2023.5], [30], [180]),
        ([2023], [], [180]),
        ([2023], [95], [180]),
        ([2023], [30], [np.nan]),
        ([2023], [30, 30], [180]),
        ([2023], [30], [0, 360]),
    ],
)
def test_invalid_request_fails_before_download(years, tilts, azimuths, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid request must not trigger a download")

    monkeypatch.setattr(energy_model, "fetch_location_year", unexpected)
    with pytest.raises(ValueError):
        compute_energy_table(LOCATION, years, tilts, azimuths)
