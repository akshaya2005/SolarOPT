"""Pull hourly NSRDB data for a location/year and cache it under data/raw/."""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime
import json
import logging
import math
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
NSRDB_CONUS_PSM4_URL = (
    "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-conus-v4-0-0-download.csv"
)
DEFAULT_ATTRIBUTES = "ghi,dni,dhi,air_temperature,wind_speed,surface_albedo,cloud_type,fill_flag"
DEFAULT_INTERVAL = 60
DEFAULT_TIMEOUT = 60

# NSRDB PSM v4 has a ~2 km spatial grid resolution (~0.018 deg lat, ~0.024 deg lon).
# Default tolerance of 0.02 deg ensures cache hits on the same/nearest grid point
# without conflating distinct neighboring locations.
DEFAULT_COORD_TOL: float = 0.02

# Continental United States (CONUS) approximate bounding box
CONUS_LAT_BOUNDS = (24.0, 50.0)
CONUS_LON_BOUNDS = (-125.0, -66.0)

REQUIRED_WEATHER_FIELDS = [
    {"ghi"},
    {"dni"},
    {"dhi"},
    {"temperature", "temp_air", "air_temperature"},
    {"wind speed", "wind_speed"},
    {"surface albedo", "surface_albedo", "albedo"},
    {"cloud type", "cloud_type"},
    {"fill flag", "fill_flag"},
]


def sanitize_url(text: str) -> str:
    """Mask sensitive API keys in text, URLs, and error messages."""
    return re.sub(r"(api_key=)[^&\s'\"]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)


def validate_conus_coordinates(lat: float, lon: float) -> None:
    """Validate that coordinates fall within the Continental United States (CONUS).

    The NSRDB GOES CONUS PSM v4 dataset exclusively covers the continental US.
    Non-CONUS locations (such as Hawaii or Alaska) require separate regional or full-disk datasets.
    """
    if not (CONUS_LAT_BOUNDS[0] <= lat <= CONUS_LAT_BOUNDS[1]) or not (
        CONUS_LON_BOUNDS[0] <= lon <= CONUS_LON_BOUNDS[1]
    ):
        raise ValueError(
            f"Coordinates (lat={lat:.2f}, lon={lon:.2f}) are outside CONUS. "
            f"The NSRDB GOES CONUS PSM v4 API only covers CONUS locations "
            f"(lat {CONUS_LAT_BOUNDS}, lon {CONUS_LON_BOUNDS}). "
            "Non-CONUS regions (such as Hawaii or Alaska) require separate datasets."
        )


def get_expected_record_count(year: int, interval: int = 60, leap_day: bool = True) -> int:
    """Calculate expected observation count for a full calendar year at a given minute interval."""
    is_leap = calendar.isleap(year) and leap_day
    days = 366 if is_leap else 365
    return days * (1440 // interval)


def load_credentials(api_key: str | None = None, email: str | None = None) -> tuple[str, str]:
    """Load NSRDB API credentials from arguments or environment variables.

    Reads .env using python-dotenv. Never prints or logs the raw API key.
    """
    load_dotenv()

    resolved_key = api_key or os.getenv("NSRDB_API_KEY") or os.getenv("NREL_API_KEY")
    resolved_email = email or os.getenv("NSRDB_EMAIL") or os.getenv("NREL_EMAIL")

    if not resolved_key or not resolved_key.strip():
        raise ValueError(
            "Missing NSRDB API key. Please set NSRDB_API_KEY in your .env file or environment, "
            "or pass api_key directly. "
            "Register for a free key at https://developer.nlr.gov/signup/."
        )
    if not resolved_email or not resolved_email.strip():
        raise ValueError(
            "Missing NSRDB email. Please set NSRDB_EMAIL in your .env file or environment, "
            "or pass email directly. The NSRDB API requires a contact email."
        )

    return resolved_key.strip(), resolved_email.strip()


def get_raw_filename(lat: float, lon: float, year: int) -> str:
    """Generate a consistent, collision-resistant filename for a location and year."""
    lat_str = f"{lat:+.4f}".replace("+", "")
    lon_str = f"{lon:+.4f}".replace("+", "")
    return f"nsrdb_{lat_str}_{lon_str}_{year}.csv"


def _check_required_columns(cols: list[str]) -> bool:
    """Check that the header contains timestamp and required weather fields."""
    normalized_cols = {c.strip().lower() for c in cols if c.strip()}
    time_fields = {"year", "month", "day", "hour", "minute"}
    if not time_fields.issubset(normalized_cols):
        return False

    for field_options in REQUIRED_WEATHER_FIELDS:
        if not normalized_cols.intersection(field_options):
            return False
    return True


def validate_raw_file(
    path: Path,
    expected_lat: float | None = None,
    expected_lon: float | None = None,
    expected_year: int | None = None,
    expected_interval: int = 60,
    coord_tol: float = DEFAULT_COORD_TOL,
    leap_day: bool = True,
) -> bool:
    """Validate that a cached raw CSV file contains valid, complete NSRDB data.

    Verifies:
      - Correct SAM CSV headers and metadata
      - Location coordinates match requested point within tolerance
      - Target year and full yearly observation count (detects truncated files)
      - Sampling interval matches expected interval (e.g. 60 min)
      - Presence of all required weather data columns
    """
    if not path.is_file() or path.stat().st_size == 0:
        return False

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            line1 = f.readline()
            line2 = f.readline()
            line3 = f.readline()
            line4 = f.readline()
            line5 = f.readline()

            # Check header structure
            if "Source" not in line1 or "Location ID" not in line1:
                return False
            if line1.strip().startswith(("{", "<", "Error", "error")):
                return False

            # Parse metadata
            meta_header = next(csv.reader([line1]))
            meta_vals = next(csv.reader([line2]))
            meta_dict = dict(zip(meta_header, meta_vals))

            # Validate coordinates if expected
            if expected_lat is not None and expected_lon is not None:
                file_lat = float(meta_dict.get("Latitude", meta_dict.get("latitude", "nan")))
                file_lon = float(meta_dict.get("Longitude", meta_dict.get("longitude", "nan")))
                if not (
                    math.isclose(file_lat, expected_lat, abs_tol=coord_tol)
                    and math.isclose(file_lon, expected_lon, abs_tol=coord_tol)
                ):
                    return False

            # Validate column presence
            header_cols = next(csv.reader([line3]))
            if not _check_required_columns(header_cols):
                return False

            # Check first observation row
            if not line4 or not line4.strip():
                return False
            row4 = next(csv.reader([line4]))
            first_year = int(row4[header_cols.index("Year")])
            first_month = int(row4[header_cols.index("Month")])
            first_day = int(row4[header_cols.index("Day")])
            first_hour = int(row4[header_cols.index("Hour")])
            first_min = int(row4[header_cols.index("Minute")])

            if expected_year is not None and first_year != expected_year:
                return False
            if first_month != 1 or first_day != 1:
                return False

            # Check interval using second observation row if available
            if line5 and line5.strip():
                row5 = next(csv.reader([line5]))
                dt1 = datetime.datetime(first_year, first_month, first_day, first_hour, first_min)
                dt2 = datetime.datetime(
                    int(row5[header_cols.index("Year")]),
                    int(row5[header_cols.index("Month")]),
                    int(row5[header_cols.index("Day")]),
                    int(row5[header_cols.index("Hour")]),
                    int(row5[header_cols.index("Minute")]),
                )
                diff_min = int((dt2 - dt1).total_seconds() / 60)
                if diff_min != expected_interval:
                    return False

            # Read remaining lines to verify complete, untruncated yearly observation count
            # 2 lines read after line3: line4 and line5
            rem_lines = 2 if (line5 and line5.strip()) else 1
            last_line = line5 if (line5 and line5.strip()) else line4
            for line in f:
                if line.strip():
                    rem_lines += 1
                    last_line = line

        # If year is specified, verify total observation count matches full calendar year
        if expected_year is not None:
            expected_count = get_expected_record_count(
                expected_year, interval=expected_interval, leap_day=leap_day
            )
            if rem_lines != expected_count:
                return False

            # Verify final observation is at year end (Dec 31)
            last_row = next(csv.reader([last_line]))
            last_month = int(last_row[header_cols.index("Month")])
            last_day = int(last_row[header_cols.index("Day")])
            if last_month != 12 or last_day != 31:
                return False

        return True
    except (OSError, csv.Error, ValueError, KeyError):
        return False


def _extract_file_metadata(path: Path) -> tuple[float | None, float | None, int | None]:
    """Extract latitude, longitude, and year from a raw NSRDB CSV file header."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader)
            values = next(reader)
            cols = next(reader)
            first_row = next(reader)

        header_dict = dict(zip(header, values))
        lat = float(header_dict.get("Latitude", header_dict.get("latitude", "nan")))
        lon = float(header_dict.get("Longitude", header_dict.get("longitude", "nan")))

        year_col_idx = cols.index("Year") if "Year" in cols else 0
        year = int(first_row[year_col_idx])
        return lat, lon, year
    except (OSError, csv.Error, ValueError, KeyError):
        return None, None, None


def find_cached_file(
    raw_dir: Path,
    lat: float,
    lon: float,
    year: int,
    interval: int = 60,
    coord_tol: float = DEFAULT_COORD_TOL,
    leap_day: bool = True,
) -> Path | None:
    """Search for an existing valid raw NSRDB file for the target location and year."""
    if not raw_dir.is_dir():
        return None

    # 1. Primary check: standard filename
    primary_candidate = raw_dir / get_raw_filename(lat, lon, year)
    if primary_candidate.is_file() and validate_raw_file(
        primary_candidate,
        expected_lat=lat,
        expected_lon=lon,
        expected_year=year,
        expected_interval=interval,
        coord_tol=coord_tol,
        leap_day=leap_day,
    ):
        return primary_candidate

    # 2. Secondary check: search existing CSV files in raw_dir
    # Validates matching coordinates, year, sampling interval, and full observation count
    for candidate in raw_dir.glob("*.csv"):
        if candidate.name.startswith(".tmp_"):
            continue
        if validate_raw_file(
            candidate,
            expected_lat=lat,
            expected_lon=lon,
            expected_year=year,
            expected_interval=interval,
            coord_tol=coord_tol,
            leap_day=leap_day,
        ):
            return candidate

    return None


def validate_api_response(
    text: str,
    expected_year: int | None = None,
    expected_interval: int = 60,
    leap_day: bool = True,
) -> None:
    """Verify that the API response contains valid CSV weather data rather than an error."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("Received empty response from NSRDB API.")

    # Detect JSON error responses
    if stripped.startswith("{") or '"errors"' in stripped[:300] or '"error"' in stripped[:300]:
        try:
            err_data = json.loads(stripped)
            err_msg = err_data.get("errors") or err_data.get("error") or stripped
            clean_err = sanitize_url(str(err_msg))
            raise RuntimeError(f"NSRDB API error: {clean_err}")
        except json.JSONDecodeError:
            pass

    # Detect HTML error responses
    is_html = (
        stripped.startswith("<")
        or "<html" in stripped[:150].lower()
        or "<!doctype" in stripped[:150].lower()
    )
    if is_html:
        raise RuntimeError("NSRDB API returned an HTML error response instead of CSV weather data.")

    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) < 4:
        raise ValueError(
            f"NSRDB API response contains only {len(lines)} line(s); "
            "expected metadata, headers, and observations."
        )

    if "Source" not in lines[0] or "Location ID" not in lines[0]:
        raise ValueError("NSRDB API response is missing expected metadata headers.")

    header_cols = next(csv.reader([lines[2]]))
    if not _check_required_columns(header_cols):
        raise ValueError("NSRDB API response is missing required weather column headers.")

    # Truncation check against full yearly observation count
    if expected_year is not None:
        expected_obs = get_expected_record_count(
            expected_year, interval=expected_interval, leap_day=leap_day
        )
        expected_lines = 3 + expected_obs
        if len(lines) != expected_lines:
            raise ValueError(
                f"NSRDB API response is truncated or incomplete: expected {expected_lines} lines "
                f"({expected_obs} observations for year {expected_year}), "
                f"but received {len(lines)} lines."
            )


def download_nsrdb_csv(
    lat: float,
    lon: float,
    year: int,
    api_key: str,
    email: str,
    *,
    interval: int = DEFAULT_INTERVAL,
    leap_day: bool = True,
    attributes: str = DEFAULT_ATTRIBUTES,
    base_url: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Download raw NSRDB CSV from the official GOES CONUS PSM v4 API."""
    if interval != 60:
        raise ValueError(
            f"SolarOPT currently requires 60-minute (hourly) observations; "
            f"received interval={interval}."
        )

    validate_conus_coordinates(lat, lon)

    url = base_url or os.getenv("NSRDB_API_BASE_URL") or NSRDB_CONUS_PSM4_URL

    params = {
        "api_key": api_key,
        "email": email,
        "wkt": f"POINT({lon:.4f} {lat:.4f})",
        "names": str(year),
        "interval": str(interval),
        "utc": "true",
        "leap_day": "true" if leap_day else "false",
        "attributes": attributes,
        "full_name": "SolarOPT Team",
        "affiliation": "Georgia Tech",
        "reason": "SolarOPT",
        "mailing_list": "false",
    }

    masked_url = sanitize_url(f"{url}?wkt=POINT({lon:.4f}+{lat:.4f})&names={year}")
    logger.info("Requesting NSRDB data from %s", masked_url)

    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Connection to NSRDB API timed out after {timeout} seconds. "
            "Please verify your connection."
        ) from None
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Failed to connect to NSRDB API. "
            "Please verify network access and endpoint availability."
        ) from None
    except requests.exceptions.RequestException as exc:
        sanitized_err = sanitize_url(str(exc))
        raise RuntimeError(f"NSRDB API request failed: {sanitized_err}") from None

    if response.status_code in (401, 403):
        raise PermissionError(
            f"NSRDB API authentication failed (HTTP {response.status_code}). "
            "Please check your NSRDB_API_KEY in .env."
        )
    if response.status_code == 429:
        raise RuntimeError(
            "NSRDB API rate limit exceeded (HTTP 429). Please wait before retrying or register "
            "for a personal key at https://developer.nlr.gov/signup/."
        )
    if response.status_code >= 400:
        error_detail = sanitize_url(response.text.strip())
        try:
            error_json = response.json()
            error_detail = sanitize_url(
                str(error_json.get("errors") or error_json.get("error") or error_detail)
            )
        except Exception:
            pass
        raise RuntimeError(
            f"NSRDB API returned error status {response.status_code}: {error_detail}"
        )

    validate_api_response(
        response.text,
        expected_year=year,
        expected_interval=interval,
        leap_day=leap_day,
    )
    return response.text


def fetch_location_year(
    lat: float,
    lon: float,
    year: int,
    *,
    raw_dir: Path | None = None,
    force_download: bool = False,
    api_key: str | None = None,
    email: str | None = None,
    interval: int = DEFAULT_INTERVAL,
    coord_tol: float = DEFAULT_COORD_TOL,
    leap_day: bool = True,
    attributes: str = DEFAULT_ATTRIBUTES,
) -> Path:
    """Fetch (or reuse a cached copy of) one location-year of NSRDB data.

    Returns the path to the cached raw CSV file.
    """
    if interval != 60:
        raise ValueError(
            f"SolarOPT currently requires 60-minute (hourly) observations; "
            f"received interval={interval}."
        )

    validate_conus_coordinates(lat, lon)

    target_dir = Path(raw_dir) if raw_dir else RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check cache first
    if not force_download:
        cached = find_cached_file(
            target_dir,
            lat,
            lon,
            year,
            interval=interval,
            coord_tol=coord_tol,
            leap_day=leap_day,
        )
        if cached is not None:
            logger.info("Found cached NSRDB file for (%s, %s, %s): %s", lat, lon, year, cached)
            return cached

    # Credentials check
    resolved_key, resolved_email = load_credentials(api_key, email)

    # Download from API
    csv_text = download_nsrdb_csv(
        lat=lat,
        lon=lon,
        year=year,
        api_key=resolved_key,
        email=resolved_email,
        interval=interval,
        leap_day=leap_day,
        attributes=attributes,
    )

    # Save to data/raw/ using atomic file write
    filename = get_raw_filename(lat, lon, year)
    final_path = target_dir / filename
    temp_path = target_dir / f".tmp_{filename}"

    temp_path.write_text(csv_text, encoding="utf-8")
    temp_path.replace(final_path)

    # Extract source location metadata to log actual NSRDB grid point coordinates
    grid_lat, grid_lon, _ = _extract_file_metadata(final_path)
    if grid_lat is not None and grid_lon is not None:
        logger.info(
            "Saved NSRDB data to %s (requested: %.4f, %.4f; nearest grid point: %.4f, %.4f)",
            final_path,
            lat,
            lon,
            grid_lat,
            grid_lon,
        )
    else:
        logger.info("Saved NSRDB data to %s", final_path)

    return final_path


def main(argv: list[str] | None = None) -> int:
    """Command-line interface for fetching NSRDB weather data."""
    parser = argparse.ArgumentParser(
        description="Fetch solar weather data from NSRDB PSM v4 API and cache under data/raw/."
    )
    parser.add_argument(
        "--lat", type=float, required=True, help="Latitude in decimal degrees (e.g. 39.62)"
    )
    parser.add_argument(
        "--lon", type=float, required=True, help="Longitude in decimal degrees (e.g. -104.61)"
    )
    parser.add_argument(
        "--year", type=int, required=True, help="Historical year to fetch (e.g. 2023)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RAW_DIR,
        help="Directory to store cached raw CSVs (default: data/raw/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force download from API even if a valid cached file exists",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        choices=[60],
        help="Observation interval in minutes (SolarOPT currently requires 60-minute observations)",
    )

    args = parser.parse_args(argv)

    try:
        saved_path = fetch_location_year(
            lat=args.lat,
            lon=args.lon,
            year=args.year,
            raw_dir=args.output_dir,
            force_download=args.force,
            interval=args.interval,
        )
        print(f"Success: {saved_path}")
        return 0
    except Exception as exc:
        logger.error("Failed to fetch NSRDB data: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
