"""Pull hourly NSRDB data for a location/year and cache it under data/raw/."""

from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch_location_year(lat: float, lon: float, year: int) -> Path:
    """Fetch (or reuse a cached copy of) one location-year of NSRDB data.

    Returns the path to the cached raw file.
    """
    raise NotImplementedError


if __name__ == "__main__":
    pass
