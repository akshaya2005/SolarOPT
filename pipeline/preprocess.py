"""Clean raw NSRDB pulls into the hourly series the energy model needs."""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

import pandas as pd
import pvlib.iotools

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# Required output columns in the exact specified schema
REQUIRED_COLUMNS = [
    "ghi",
    "dni",
    "dhi",
    "temp_air",
    "wind_speed",
    "surface_albedo",
    "cloud_type",
    "fill_flag",
]

# Mapping raw and pvlib column names to canonical schema
COLUMN_MAP = {
    "ghi": "ghi",
    "dni": "dni",
    "dhi": "dhi",
    "temp_air": "temp_air",
    "temperature": "temp_air",
    "air_temperature": "temp_air",
    "wind_speed": "wind_speed",
    "wind speed": "wind_speed",
    "surface_albedo": "surface_albedo",
    "surface albedo": "surface_albedo",
    "albedo": "surface_albedo",
    "cloud_type": "cloud_type",
    "cloud type": "cloud_type",
    "fill_flag": "fill_flag",
    "fill flag": "fill_flag",
}

# Expected physical ranges for plausibility validation
PHYSICAL_RANGES = {
    "ghi": (0.0, 1500.0),
    "dni": (0.0, 1500.0),
    "dhi": (0.0, 1500.0),
    "temp_air": (-90.0, 65.0),
    "wind_speed": (0.0, 120.0),
    "surface_albedo": (0.0, 1.0),
    "cloud_type": (-15, 20),
    "fill_flag": (0, 100),
}


def _validate_units(meta_dict: dict[str, str]) -> None:
    """Validate that reported units in NSRDB metadata match physical expectations."""
    expected_units = {
        "DHI Units": "w/m2",
        "DNI Units": "w/m2",
        "GHI Units": "w/m2",
        "Temperature Units": "c",
        "Wind Speed Units": "m/s",
    }
    for unit_name, expected in expected_units.items():
        if unit_name in meta_dict:
            actual = meta_dict[unit_name].strip().lower()
            if actual != expected:
                raise ValueError(
                    f"Unit mismatch for '{unit_name}': expected '{expected}', found '{actual}'."
                )


def _read_raw_csv_direct(
    raw_path: Path, meta_dict: dict[str, str]
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Fallback parser reading SAM CSV directly with pandas and metadata header."""
    raw_df = pd.read_csv(raw_path, skiprows=2)
    time_cols = ["Year", "Month", "Day", "Hour", "Minute"]
    missing_time = [c for c in time_cols if c not in raw_df.columns]
    if missing_time:
        raise ValueError(f"Missing required timestamp columns in raw CSV: {missing_time}")

    dt_series = pd.to_datetime(raw_df[time_cols])
    time_zone_val = int(meta_dict.get("Time Zone", 0))
    tz_str = f"Etc/GMT{'+' if -time_zone_val >= 0 else ''}{-time_zone_val}"
    raw_df.index = pd.DatetimeIndex(dt_series).tz_localize(tz_str).tz_convert("UTC")
    raw_df.index.name = "timestamp"

    # Drop the date component columns now that DatetimeIndex is built
    raw_df = raw_df.drop(columns=time_cols)
    return raw_df, meta_dict


def load_and_clean(raw_path: Path) -> pd.DataFrame:
    """Load one raw NSRDB file and return a cleaned hourly DataFrame.

    Conforms to the SolarOPT standardized schema:
      - DatetimeIndex: timezone-aware UTC named 'timestamp'
      - Columns: ghi, dni, dhi, temp_air, wind_speed, surface_albedo, cloud_type, fill_flag
      - Retains location & source metadata in df.attrs
    """
    path = Path(raw_path)
    if not path.is_file():
        raise FileNotFoundError(f"Raw NSRDB file not found: {path}")

    # 1. Parse metadata rows (rows 1 and 2) and verify file structure
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        try:
            meta_keys = next(reader)
            meta_vals = next(reader)
            _ = next(reader)
        except StopIteration as exc:
            raise ValueError(f"File {path} must contain at least 3 header rows.") from exc

    meta_dict = {k.strip(): v.strip() for k, v in zip(meta_keys, meta_vals) if k.strip()}
    _validate_units(meta_dict)

    # 2. Parse weather observations using pvlib with direct fallback
    pvlib_meta: dict[str, str | float | int] = {}
    try:
        data, parsed_pvlib_meta = pvlib.iotools.read_nsrdb_psm4(path)
        pvlib_meta = parsed_pvlib_meta
        # Ensure UTC timezone-aware DatetimeIndex named 'timestamp'
        data.index = pd.DatetimeIndex(data.index).tz_convert("UTC")
        data.index.name = "timestamp"
    except Exception as exc:
        logger.debug("pvlib.iotools.read_nsrdb_psm4 failed (%s), using direct CSV parser", exc)
        data, _ = _read_raw_csv_direct(path, meta_dict)

    # 3. Normalize column names to canonical schema
    normalized_names = {}
    for col in data.columns:
        clean_key = str(col).strip().lower()
        if clean_key in COLUMN_MAP:
            normalized_names[col] = COLUMN_MAP[clean_key]

    df = data.rename(columns=normalized_names)

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required weather column(s): {missing_cols}. "
            f"Present columns: {list(df.columns)}"
        )

    # Select only required columns in strict schema order
    df = df[REQUIRED_COLUMNS].copy()

    # 4. Enforce numeric types
    float_cols = ["ghi", "dni", "dhi", "temp_air", "wind_speed", "surface_albedo"]
    int_cols = ["cloud_type", "fill_flag"]

    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="raise").astype("float64")
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")

    # 5. Data validation checks
    # Check for NaN / missing values
    if df.isna().any().any():
        cols_with_nan = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Dataset contains missing/NaN values in column(s): {cols_with_nan}")

    # Check for duplicate timestamps
    if df.index.duplicated().any():
        num_dups = int(df.index.duplicated().sum())
        raise ValueError(f"Dataset contains {num_dups} duplicate timestamp(s).")

    # Check for strictly monotonically increasing timestamps
    if not df.index.is_monotonic_increasing:
        raise ValueError("Timestamps are not strictly monotonically increasing.")

    # Check for hourly frequency consistency
    if len(df) > 1:
        time_diffs = df.index[1:] - df.index[:-1]
        expected_diff = pd.Timedelta(hours=1)
        if (time_diffs != expected_diff).any():
            raise ValueError(
                "Timestamps do not have consistent hourly intervals "
                "(expected 1 hour between consecutive records)."
            )

    # Physical bounds validation
    for col, (min_val, max_val) in PHYSICAL_RANGES.items():
        if (df[col] < min_val).any():
            bad_val = df.loc[df[col] < min_val, col].iloc[0]
            raise ValueError(
                f"Column '{col}' has value {bad_val} below physical lower bound {min_val}."
            )
        if (df[col] > max_val).any():
            bad_val = df.loc[df[col] > max_val, col].iloc[0]
            raise ValueError(
                f"Column '{col}' has value {bad_val} above physical upper bound {max_val}."
            )

    # 6. Retain location and source metadata
    lat_val = float(pvlib_meta.get("latitude", meta_dict.get("Latitude", 0.0)))
    lon_val = float(pvlib_meta.get("longitude", meta_dict.get("Longitude", 0.0)))
    elev_val = float(pvlib_meta.get("altitude", meta_dict.get("Elevation", 0.0)))
    version_val = str(meta_dict.get("Version", pvlib_meta.get("Version", "unknown")))
    year_val = int(df.index[0].year)
    location_id_val = str(meta_dict.get("Location ID", pvlib_meta.get("Location ID", "")))

    df.attrs["latitude"] = lat_val
    df.attrs["longitude"] = lon_val
    df.attrs["elevation"] = elev_val
    df.attrs["source_version"] = version_val
    df.attrs["year"] = year_val
    df.attrs["location_id"] = location_id_val
    df.attrs["raw_metadata"] = meta_dict

    logger.info(
        "Successfully cleaned %d records from %s (lat=%.4f, lon=%.4f, year=%d)",
        len(df),
        path.name,
        lat_val,
        lon_val,
        year_val,
    )
    return df


def save_cleaned_to_parquet(df: pd.DataFrame, output_path: Path) -> Path:
    """Save cleaned DataFrame to a Parquet file, creating directories if needed."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow")
    logger.info("Saved %d cleaned records to %s", len(df), out)
    return out


def main(argv: list[str] | None = None) -> int:
    """Command-line interface for preprocessing raw NSRDB CSV files."""
    parser = argparse.ArgumentParser(
        description="Preprocess raw NSRDB CSV into a clean, validated hourly Parquet dataset."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Path to raw NSRDB CSV file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to save processed Parquet (default: data/processed/<stem>.parquet)",
    )

    args = parser.parse_args(argv)

    try:
        df = load_and_clean(args.input)
        output_file = args.output
        if output_file is None:
            output_file = PROCESSED_DIR / f"{args.input.stem}.parquet"

        save_cleaned_to_parquet(df, output_file)
        print(f"Cleaned dataset saved successfully: {output_file}")
        print(f"Summary: {len(df)} records, {len(df.columns)} columns")
        print(f"Time range: {df.index.min()} to {df.index.max()}")
        lat_disp = df.attrs.get("latitude")
        lon_disp = df.attrs.get("longitude")
        elev_disp = df.attrs.get("elevation")
        print(f"Location metadata: lat={lat_disp}, lon={lon_disp}, elevation={elev_disp}m")
        return 0
    except Exception as exc:
        logger.error("Preprocessing failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
