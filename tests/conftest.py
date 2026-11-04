import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

META_LINE_1 = (
    "Source,Location ID,City,State,Country,Latitude,Longitude,Time Zone,Elevation,Local Time Zone,"
    "Clearsky DHI Units,Clearsky DNI Units,Clearsky GHI Units,Dew Point Units,DHI Units,DNI Units,"
    "GHI Units,Solar Zenith Angle Units,Temperature Units,Pressure Units,Relative Humidity Units,"
    "Precipitable Water Units,Wind Direction Units,Wind Speed Units,Cloud Type -15,Cloud Type 0,"
    "Cloud Type 1,Cloud Type 2,Cloud Type 3,Cloud Type 4,Cloud Type 5,Cloud Type 6,Cloud Type 7,"
    "Cloud Type 8,Cloud Type 9,Cloud Type 10,Cloud Type 11,Cloud Type 12,Fill Flag 0,Fill Flag 1,"
    "Fill Flag 2,Fill Flag 3,Fill Flag 4,Fill Flag 5,Surface Albedo Units,Version"
)


def make_mock_nsrdb_csv(
    year: int = 2023,
    lat: float = 39.62,
    lon: float = -104.61,
    num_records: int = 8760,
    interval_min: int = 60,
) -> str:
    """Generate mock NSRDB PSM v4 CSV text with metadata and hourly observations."""
    meta_line_2 = (
        f"NSRDB,995709,-,-,-,{lat},{lon},0,1797,-7,w/m2,w/m2,w/m2,c,w/m2,w/m2,w/m2,Degree,c,mbar,"
        "%,cm,Degrees,m/s,N/A,Clear,Probably Clear,Fog,Water,Super-Cooled Water,Mixed,Opaque Ice,"
        "Cirrus,Overlapping,Overshooting,Unknown,Dust,Smoke,N/A,Missing Image,Low Irradiance,"
        "Exceeds Clearsky,Missing CLoud Properties,Rayleigh Violation,N/A,4.0.1"
    )
    cols_line = (
        "Year,Month,Day,Hour,Minute,Temperature,Wind Speed,Surface Albedo,"
        "DHI,DNI,GHI,Cloud Type,Fill Flag"
    )

    lines = [META_LINE_1, meta_line_2, cols_line]

    cur = datetime.datetime(year, 1, 1, 0, 30)
    for i in range(num_records):
        is_day = 6 <= cur.hour <= 18
        ghi = 300.0 if is_day else 0.0
        dni = 500.0 if is_day else 0.0
        dhi = 100.0 if is_day else 0.0
        temp = 15.0 if is_day else -2.5
        cloud = 0 if i % 2 == 0 else 7
        flag = 0 if i % 10 != 0 else 7
        lines.append(
            f"{cur.year},{cur.month},{cur.day},{cur.hour},{cur.minute},"
            f"{temp},2.5,0.65,{dhi:.0f},{dni:.0f},{ghi:.0f},{cloud},{flag}"
        )
        cur += datetime.timedelta(minutes=interval_min)

    return "\n".join(lines) + "\n"


@pytest.fixture
def sample_csv_text() -> str:
    """Return full-year 8,760-record CSV text for year 2023."""
    return make_mock_nsrdb_csv(year=2023, num_records=8760)


@pytest.fixture
def sample_csv_path(tmp_path: Path) -> Path:
    """Write and return a full-year 8,760-record valid raw CSV file."""
    fixture_file = tmp_path / "nsrdb_39.6200_-104.6100_2023.csv"
    fixture_file.write_text(make_mock_nsrdb_csv(year=2023, num_records=8760), encoding="utf-8")
    return fixture_file


@pytest.fixture
def sample_24h_csv_path(tmp_path: Path) -> Path:
    """Write and return a 24-hour sample CSV file for quick unit checks."""
    fixture_file = tmp_path / "sample_24h_2023.csv"
    fixture_file.write_text(make_mock_nsrdb_csv(year=2023, num_records=24), encoding="utf-8")
    return fixture_file


@pytest.fixture
def truncated_csv_path(tmp_path: Path) -> Path:
    """Write and return a truncated CSV containing only one observation."""
    fixture_file = tmp_path / "truncated_2023.csv"
    fixture_file.write_text(make_mock_nsrdb_csv(year=2023, num_records=1), encoding="utf-8")
    return fixture_file
