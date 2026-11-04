"""Tests for pipeline/preprocess.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from pipeline.preprocess import (
    REQUIRED_COLUMNS,
    load_and_clean,
    save_cleaned_to_parquet,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_SAMPLE_PATH = REPO_ROOT / "data" / "raw" / "995709_39.62_-104.61_2023.csv"
if not REAL_SAMPLE_PATH.is_file():
    for alt_path in (
        REPO_ROOT / "data" / "raw" / "nsrdb_39.6200_-104.6100_2023.csv",
        REPO_ROOT.parent / "995709_39.62_-104.61_2023.csv",
    ):
        if alt_path.is_file():
            REAL_SAMPLE_PATH = alt_path
            break


def test_load_and_clean_sample_fixture(sample_24h_csv_path: Path):
    """Verify that sample 24-hour fixture is cleaned and adheres to schema."""
    df = load_and_clean(sample_24h_csv_path)

    # 24 hourly records
    assert len(df) == 24

    # Exact required columns and order
    assert list(df.columns) == REQUIRED_COLUMNS

    # Column dtypes
    for col in ["ghi", "dni", "dhi", "temp_air", "wind_speed", "surface_albedo"]:
        assert df[col].dtype == "float64"
    for col in ["cloud_type", "fill_flag"]:
        assert df[col].dtype == "int64"

    # Index properties
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.name == "timestamp"
    assert str(df.index.tz) == "UTC"

    # Timing: hourly intervals at HH:30 preserved
    assert (df.index.minute == 30).all()
    assert (df.index[1:] - df.index[:-1] == pd.Timedelta(hours=1)).all()

    # Metadata attributes
    assert df.attrs["latitude"] == pytest.approx(39.62, abs=0.01)
    assert df.attrs["longitude"] == pytest.approx(-104.61, abs=0.01)
    assert df.attrs["elevation"] == 1797
    assert df.attrs["source_version"] == "4.0.1"
    assert df.attrs["year"] == 2023
    assert df.attrs["location_id"] == "995709"

    # Quality flags and cloud types preserved
    assert set(df["fill_flag"].unique()) == {0, 7}
    assert 7 in df["cloud_type"].unique()

    # Nighttime values and negative temperatures preserved
    assert (df.loc["2023-01-01 00:30:00+00:00", ["ghi", "dni", "dhi"]] == 0.0).all()
    assert (df["temp_air"] < 0).any()


def test_load_and_clean_full_real_sample():
    """Verify loading and cleaning the full 2023 real NSRDB sample dataset."""
    if not REAL_SAMPLE_PATH.is_file():
        pytest.skip(
            f"Real sample CSV not found at {REAL_SAMPLE_PATH}. "
            "Please ensure 995709_39.62_-104.61_2023.csv is located in data/raw/ to run this test."
        )
    df = load_and_clean(REAL_SAMPLE_PATH)

    # Exactly 8,760 hourly records for non-leap year 2023
    assert len(df) == 8760
    assert list(df.columns) == REQUIRED_COLUMNS

    # Full year date range
    assert df.index.min() == pd.Timestamp("2023-01-01 00:30:00+00:00")
    assert df.index.max() == pd.Timestamp("2023-12-31 23:30:00+00:00")

    # Temporal consistency
    assert df.index.is_monotonic_increasing
    assert not df.index.duplicated().any()
    diffs = df.index[1:] - df.index[:-1]
    assert (diffs == pd.Timedelta(hours=1)).all()

    # No NaNs or fabricated missing values
    assert not df.isna().any().any()

    # Quality flags: preserve original fill flags (sample contains 0, 1, 5, 7)
    flags = set(df["fill_flag"].unique())
    assert {0, 1, 5, 7}.issubset(flags)

    # Negative temperatures preserved (min is ~ -17.3)
    assert df["temp_air"].min() < -15.0

    # Retain metadata
    assert df.attrs["latitude"] == pytest.approx(39.62, abs=0.01)
    assert df.attrs["longitude"] == pytest.approx(-104.61, abs=0.01)
    assert df.attrs["elevation"] == 1797
    assert df.attrs["year"] == 2023


def test_missing_file_raises_not_found(tmp_path: Path):
    """Attempting to clean a non-existent file must raise FileNotFoundError."""
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match="not found"):
        load_and_clean(missing)


def test_missing_header_rows(tmp_path: Path):
    """A file with fewer than 3 lines must raise ValueError."""
    bad_file = tmp_path / "short.csv"
    bad_file.write_text("Source,Location ID\nNSRDB,1234\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at least 3 header rows"):
        load_and_clean(bad_file)


def test_unit_mismatch_raises_error(sample_24h_csv_path: Path, tmp_path: Path):
    """Unexpected physical units in metadata must trigger a ValueError."""
    content = sample_24h_csv_path.read_text(encoding="utf-8")
    # Alter temperature unit from c to f
    bad_content = content.replace(",Degree,c,mbar,", ",Degree,f,mbar,")
    bad_file = tmp_path / "bad_units.csv"
    bad_file.write_text(bad_content, encoding="utf-8")

    with pytest.raises(ValueError, match="Unit mismatch for 'Temperature Units'"):
        load_and_clean(bad_file)


def test_missing_required_column_raises_error(sample_24h_csv_path: Path, tmp_path: Path):
    """Dropping a required measurement column must raise ValueError."""
    lines = sample_24h_csv_path.read_text(encoding="utf-8").splitlines()
    # Remove 'GHI' column from header line 3
    header_cols = lines[2].split(",")
    ghi_idx = header_cols.index("GHI")
    new_header = [c for i, c in enumerate(header_cols) if i != ghi_idx]
    lines[2] = ",".join(new_header)
    for idx in range(3, len(lines)):
        row = lines[idx].split(",")
        lines[idx] = ",".join([v for i, v in enumerate(row) if i != ghi_idx])

    bad_file = tmp_path / "missing_ghi.csv"
    bad_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required weather column"):
        load_and_clean(bad_file)


def test_missing_nan_value_raises_error(sample_24h_csv_path: Path, tmp_path: Path):
    """An observation with an empty/NaN value must raise ValueError without fabricating data."""
    lines = sample_24h_csv_path.read_text(encoding="utf-8").splitlines()
    # Replace Temperature in first observation row with empty
    row = lines[3].split(",")
    row[5] = ""  # empty temperature
    lines[3] = ",".join(row)

    bad_file = tmp_path / "nan_val.csv"
    bad_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ValueError, match="(missing/NaN values|could not convert)"):
        load_and_clean(bad_file)


def test_duplicate_timestamps_raises_error(sample_24h_csv_path: Path, tmp_path: Path):
    """Duplicate observation timestamps must raise ValueError."""
    lines = sample_24h_csv_path.read_text(encoding="utf-8").splitlines()
    # Duplicate line 4 (second observation copied over third)
    lines[5] = lines[4]

    bad_file = tmp_path / "dup_time.csv"
    bad_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate timestamp"):
        load_and_clean(bad_file)


def test_non_monotonic_timestamps_raises_error(sample_24h_csv_path: Path, tmp_path: Path):
    """Out-of-order timestamps must raise ValueError."""
    lines = sample_24h_csv_path.read_text(encoding="utf-8").splitlines()
    # Swap row 4 and row 5
    lines[4], lines[5] = lines[5], lines[4]

    bad_file = tmp_path / "unordered_time.csv"
    bad_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ValueError, match="(strictly monotonically increasing|hourly intervals)"):
        load_and_clean(bad_file)


def test_irregular_hourly_spacing_raises_error(sample_24h_csv_path: Path, tmp_path: Path):
    """Gaps between observations must raise ValueError."""
    lines = sample_24h_csv_path.read_text(encoding="utf-8").splitlines()
    # Delete row 5 (creates a 2-hour jump)
    del lines[5]

    bad_file = tmp_path / "gap_time.csv"
    bad_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ValueError, match="consistent hourly intervals"):
        load_and_clean(bad_file)


@pytest.mark.parametrize(
    ("col_name", "bad_value", "expected_msg"),
    [
        ("GHI", "-10", "below physical lower bound 0.0"),
        ("GHI", "2000", "above physical upper bound 1500.0"),
        ("Surface Albedo", "1.5", "above physical upper bound 1.0"),
        ("Surface Albedo", "-0.1", "below physical lower bound 0.0"),
        ("Wind Speed", "-1.0", "below physical lower bound 0.0"),
        ("Temperature", "-100", "below physical lower bound -90.0"),
    ],
)
def test_physical_bounds_violation(
    sample_24h_csv_path: Path,
    tmp_path: Path,
    col_name: str,
    bad_value: str,
    expected_msg: str,
):
    """Values outside physical plausibility bounds must be detected."""
    lines = sample_24h_csv_path.read_text(encoding="utf-8").splitlines()
    header_cols = lines[2].split(",")
    col_idx = header_cols.index(col_name)

    row = lines[4].split(",")
    row[col_idx] = bad_value
    lines[4] = ",".join(row)

    bad_file = tmp_path / f"bad_{col_name.replace(' ', '_')}.csv"
    bad_file.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_msg):
        load_and_clean(bad_file)


def test_save_parquet_roundtrip_preserves_schema_and_attrs(
    sample_24h_csv_path: Path, tmp_path: Path
):
    """Cleaned DataFrame saved to Parquet retains schema, DatetimeIndex, and metadata attrs."""
    df = load_and_clean(sample_24h_csv_path)
    out_parquet = tmp_path / "test_output.parquet"

    save_cleaned_to_parquet(df, out_parquet)
    assert out_parquet.is_file()

    reloaded = pd.read_parquet(out_parquet)
    assert len(reloaded) == len(df)
    assert list(reloaded.columns) == list(df.columns)
    assert (reloaded.dtypes == df.dtypes).all()
    assert reloaded.index.name == "timestamp"
    assert str(reloaded.index.tz) == "UTC"

    # Verify attributes preserved
    assert reloaded.attrs.get("latitude") == pytest.approx(39.62, abs=0.01)
    assert reloaded.attrs.get("year") == 2023


def test_preprocess_cli_execution(sample_24h_csv_path: Path, tmp_path: Path):
    """Test CLI execution of pipeline.preprocess module."""
    out_file = tmp_path / "cli_output.parquet"
    cmd = [
        sys.executable,
        "-m",
        "pipeline.preprocess",
        "--input",
        str(sample_24h_csv_path),
        "--output",
        str(out_file),
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0
    assert out_file.is_file()
    assert "Cleaned dataset saved successfully" in res.stdout
