"""Tests for pipeline/fetch_nsrdb.py."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from conftest import make_mock_nsrdb_csv

from pipeline.fetch_nsrdb import (
    DEFAULT_COORD_TOL,
    download_nsrdb_csv,
    fetch_location_year,
    find_cached_file,
    get_expected_record_count,
    get_raw_filename,
    load_credentials,
    sanitize_url,
    validate_api_response,
    validate_conus_coordinates,
    validate_raw_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_sanitize_url():
    """Verify that sensitive API keys are masked in URL strings and error messages."""
    url = "https://developer.nlr.gov/api/nsrdb?api_key=SECRET12345&email=user@test.com"
    masked = sanitize_url(url)
    assert "SECRET12345" not in masked
    assert "api_key=[REDACTED]" in masked
    assert "email=user@test.com" in masked


def test_validate_conus_coordinates():
    """Verify CONUS geographic bounds enforcement."""
    # Valid CONUS points
    validate_conus_coordinates(39.62, -104.61)  # Denver
    validate_conus_coordinates(25.76, -80.19)  # Miami
    validate_conus_coordinates(47.60, -122.33)  # Seattle

    # Non-CONUS points should raise informative ValueError
    with pytest.raises(ValueError, match="outside CONUS"):
        validate_conus_coordinates(21.31, -157.86)  # Honolulu, HI

    with pytest.raises(ValueError, match="outside CONUS"):
        validate_conus_coordinates(61.22, -149.90)  # Anchorage, AK


def test_get_expected_record_count():
    """Check observation count calculation for leap vs non-leap years."""
    # Non-leap year 2023: 365 days * 24 hours = 8,760
    assert get_expected_record_count(2023, interval=60) == 8760
    # Leap year 2024: 366 days * 24 hours = 8,784
    assert get_expected_record_count(2024, interval=60, leap_day=True) == 8784
    assert get_expected_record_count(2024, interval=60, leap_day=False) == 8760


def test_load_credentials_from_args():
    """Credentials passed via arguments take precedence and are returned stripped."""
    key, mail = load_credentials(api_key=" test_key ", email=" test@example.com ")
    assert key == "test_key"
    assert mail == "test@example.com"


def test_load_credentials_from_env(monkeypatch):
    """Credentials set in environment variables are loaded properly."""
    monkeypatch.setenv("NSRDB_API_KEY", "env_key_123")
    monkeypatch.setenv("NSRDB_EMAIL", "env_mail@example.com")

    key, mail = load_credentials()
    assert key == "env_key_123"
    assert mail == "env_mail@example.com"


def test_load_credentials_missing_raises_error(monkeypatch):
    """Missing key or email must raise ValueError with signup instructions."""
    monkeypatch.setattr("pipeline.fetch_nsrdb.load_dotenv", lambda **kwargs: None)
    monkeypatch.delenv("NSRDB_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("NSRDB_EMAIL", raising=False)
    monkeypatch.delenv("NREL_EMAIL", raising=False)

    with pytest.raises(ValueError, match="Missing NSRDB API key"):
        load_credentials()

    with pytest.raises(ValueError, match="Missing NSRDB email"):
        load_credentials(api_key="some_key", email=None)


def test_get_raw_filename():
    """Test deterministic and collision-resistant filename formatting."""
    name1 = get_raw_filename(39.62, -104.61, 2023)
    assert name1 == "nsrdb_39.6200_-104.6100_2023.csv"

    name2 = get_raw_filename(39.62001, -104.61001, 2023)
    assert name2 == "nsrdb_39.6200_-104.6100_2023.csv"

    name3 = get_raw_filename(40.0, -105.0, 2022)
    assert name3 == "nsrdb_40.0000_-105.0000_2022.csv"


def test_validate_raw_file_valid_full_year(sample_csv_path: Path):
    """Full-year valid file passes validation."""
    assert validate_raw_file(
        sample_csv_path,
        expected_lat=39.62,
        expected_lon=-104.61,
        expected_year=2023,
        expected_interval=60,
    )


def test_validate_raw_file_rejects_truncated_file(truncated_csv_path: Path):
    """A file containing only one observation must be rejected as truncated."""
    # When year is specified, validation must verify full-year observation count
    assert not validate_raw_file(
        truncated_csv_path,
        expected_lat=39.62,
        expected_lon=-104.61,
        expected_year=2023,
        expected_interval=60,
    )


def test_validate_raw_file_rejects_coordinate_mismatch(sample_csv_path: Path):
    """Cached file with mismatching coordinates must be rejected."""
    assert not validate_raw_file(
        sample_csv_path,
        expected_lat=42.0,
        expected_lon=-71.0,
        expected_year=2023,
    )


def test_cache_coordinate_tolerance_regression(sample_csv_path: Path, tmp_path: Path):
    """Verify that cached files are only matched within strict 0.02 deg grid tolerance.

    The NSRDB PSM v4 grid resolution is ~2 km (~0.018 deg lat, ~0.024 deg lon).
    A tolerance of 0.05 was too loose and could mistakenly conflate neighboring locations
    (e.g. points 0.03 deg away). A tolerance of 0.02 correctly matches the nearest grid point
    (<= 0.02 deg) but rejects distinct locations (> 0.02 deg away).
    """
    assert DEFAULT_COORD_TOL == 0.02

    # sample_csv_path has metadata lat=39.62, lon=-104.61

    # 1. Coordinates within 0.02 tolerance (offset <= 0.02 deg) are accepted
    assert validate_raw_file(
        sample_csv_path,
        expected_lat=39.63,  # offset: 0.010 <= 0.02
        expected_lon=-104.61,
        expected_year=2023,
    )
    assert validate_raw_file(
        sample_csv_path,
        expected_lat=39.62,
        expected_lon=-104.625,  # offset: 0.015 <= 0.02
        expected_year=2023,
    )

    # 2. Coordinates outside 0.02 tolerance (offset > 0.02 deg) MUST be rejected.
    # Note: an offset of 0.03 was erroneously accepted under the legacy 0.05 tolerance.
    assert not validate_raw_file(
        sample_csv_path,
        expected_lat=39.65,  # offset: 0.030 > 0.02
        expected_lon=-104.61,
        expected_year=2023,
    )
    assert not validate_raw_file(
        sample_csv_path,
        expected_lat=39.62,
        expected_lon=-104.64,  # offset: 0.030 > 0.02
        expected_year=2023,
    )

    # 3. Test find_cached_file behavior with 0.02 tolerance
    raw_dir = tmp_path / "cache_tolerance_dir"
    raw_dir.mkdir()
    cached_file = raw_dir / "nsrdb_39.6200_-104.6100_2023.csv"
    shutil.copy(sample_csv_path, cached_file)

    # Request within 0.02 deg matches cached file
    hit = find_cached_file(raw_dir, lat=39.63, lon=-104.61, year=2023)
    assert hit == cached_file

    # Request outside 0.02 deg does not match cached file
    miss = find_cached_file(raw_dir, lat=39.65, lon=-104.61, year=2023)
    assert miss is None


def test_validate_raw_file_rejects_interval_mismatch(tmp_path: Path):
    """Cached file with 30-min sampling interval must be rejected when expecting 60-min."""
    thirty_min_csv = tmp_path / "thirty_min.csv"
    thirty_min_csv.write_text(
        make_mock_nsrdb_csv(year=2023, num_records=8760 * 2, interval_min=30),
        encoding="utf-8",
    )
    assert not validate_raw_file(
        thirty_min_csv,
        expected_lat=39.62,
        expected_lon=-104.61,
        expected_year=2023,
        expected_interval=60,
    )


def test_validate_raw_file_rejects_corrupted_files(tmp_path: Path):
    """Non-existent, empty, JSON-error, and HTML-error files must be rejected."""
    # Non-existent file
    assert not validate_raw_file(tmp_path / "nope.csv")

    # Empty file
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert not validate_raw_file(empty)

    # Corrupt: JSON error message saved as CSV
    json_err = tmp_path / "err.csv"
    json_err.write_text('{"errors": ["Invalid API key"]}\n', encoding="utf-8")
    assert not validate_raw_file(json_err)

    # Corrupt: HTML error page
    html_err = tmp_path / "err.html"
    html_err.write_text(
        "<!DOCTYPE html><html><body>503 Service Unavailable</body></html>",
        encoding="utf-8",
    )
    assert not validate_raw_file(html_err)


def test_cache_reuse_success(sample_csv_path: Path, tmp_path: Path):
    """When a complete valid file exists in cache, fetch_location_year returns it without API."""
    with patch("requests.get") as mock_get:
        res_path = fetch_location_year(39.62, -104.61, 2023, raw_dir=tmp_path)
        assert res_path == sample_csv_path
        # Network must not be called
        mock_get.assert_not_called()


def test_cache_reuse_rejects_truncated_cache(truncated_csv_path: Path, tmp_path: Path):
    """Truncated file in cache is rejected and triggers API download."""
    truncated_cached = tmp_path / "nsrdb_39.6200_-104.6100_2023.csv"
    shutil.copy(truncated_csv_path, truncated_cached)

    full_content = make_mock_nsrdb_csv(year=2023, num_records=8760)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = full_content

    with patch("requests.get", return_value=mock_resp) as mock_get:
        res_path = fetch_location_year(
            39.62, -104.61, 2023, raw_dir=tmp_path, api_key="k", email="e@e.com"
        )
        assert res_path.is_file()
        # Must have initiated download because cached file was truncated
        mock_get.assert_called_once()


def test_restrict_interval_to_60_minutes():
    """Passing a non-60-minute interval must raise a clear ValueError."""
    with pytest.raises(ValueError, match="requires 60-minute"):
        fetch_location_year(39.62, -104.61, 2023, interval=30)

    with pytest.raises(ValueError, match="requires 60-minute"):
        download_nsrdb_csv(39.62, -104.61, 2023, api_key="k", email="e@e.com", interval=15)


def test_mocked_successful_api_download(sample_csv_text: str, tmp_path: Path):
    """Mock a 200 response from NSRDB and verify downloaded file structure and parameters."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_csv_text

    with patch("requests.get", return_value=mock_resp) as mock_get:
        out_path = fetch_location_year(
            lat=39.62,
            lon=-104.61,
            year=2023,
            raw_dir=tmp_path,
            api_key="fake_key",
            email="fake@test.com",
            force_download=True,
        )

        assert out_path.is_file()
        assert out_path.name == "nsrdb_39.6200_-104.6100_2023.csv"
        assert out_path.read_text(encoding="utf-8") == sample_csv_text

        # Verify query parameters sent to API
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["api_key"] == "fake_key"
        assert params["email"] == "fake@test.com"
        assert params["wkt"] == "POINT(-104.6100 39.6200)"
        assert params["names"] == "2023"
        assert params["interval"] == "60"
        assert params["utc"] == "true"
        assert params["leap_day"] == "true"
        assert "ghi" in params["attributes"]


def test_api_key_sanitized_in_request_exception(tmp_path: Path):
    """Generic request exception containing the API key in the URL must be sanitized."""
    sensitive_url = "https://developer.nlr.gov/api/nsrdb?api_key=SUPER_SECRET_KEY&email=me@gt.edu"
    req_err = requests.exceptions.RequestException(
        f"Failed to establish connection to {sensitive_url}"
    )

    with patch("requests.get", side_effect=req_err):
        with pytest.raises(RuntimeError) as exc_info:
            fetch_location_year(
                39.62,
                -104.61,
                2023,
                raw_dir=tmp_path,
                api_key="SUPER_SECRET_KEY",
                email="me@gt.edu",
                force_download=True,
            )

        error_message = str(exc_info.value)
        assert "SUPER_SECRET_KEY" not in error_message
        assert "api_key=[REDACTED]" in error_message


def test_mocked_auth_failure_401_403(tmp_path: Path):
    """Mock a 403 Forbidden response and verify clean PermissionError without leaking key."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(
            PermissionError, match="authentication failed \\(HTTP 403\\)"
        ) as exc_info:
            fetch_location_year(
                39.62,
                -104.61,
                2023,
                raw_dir=tmp_path,
                api_key="secret_super_key",
                email="t@t.com",
                force_download=True,
            )
        assert "secret_super_key" not in str(exc_info.value)


def test_mocked_rate_limit_429(tmp_path: Path):
    """Mock a 429 Too Many Requests response and verify rate limit error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="rate limit exceeded \\(HTTP 429\\)"):
            fetch_location_year(
                39.62,
                -104.61,
                2023,
                raw_dir=tmp_path,
                api_key="k",
                email="e@e.com",
                force_download=True,
            )


def test_mocked_invalid_response_body_not_cached(tmp_path: Path):
    """If API returns 200 but body contains JSON error or HTML, it must not be saved."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"errors": ["Coordinates out of bounds"]}'

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Coordinates out of bounds"):
            fetch_location_year(
                39.62,
                -104.61,
                2023,
                raw_dir=tmp_path,
                api_key="k",
                email="e@e.com",
                force_download=True,
            )

    # Ensure no corrupted file was saved to cache
    assert len(list(tmp_path.glob("*.csv"))) == 0


def test_validate_api_response_rejects_truncated_payload():
    """Truncated API response body must trigger ValueError."""
    one_row_csv = make_mock_nsrdb_csv(year=2023, num_records=1)
    with pytest.raises(ValueError, match="truncated or incomplete"):
        validate_api_response(one_row_csv, expected_year=2023, expected_interval=60)


def test_mocked_network_timeout(tmp_path: Path):
    """Network timeouts must be caught and raised as informative RuntimeErrors."""
    with patch("requests.get", side_effect=requests.exceptions.Timeout("Timed out")):
        with pytest.raises(RuntimeError, match="timed out"):
            fetch_location_year(
                39.62,
                -104.61,
                2023,
                raw_dir=tmp_path,
                api_key="k",
                email="e@e.com",
                force_download=True,
            )


def test_mocked_connection_error(tmp_path: Path):
    """Network connection errors must be caught and raised as informative RuntimeErrors."""
    with patch(
        "requests.get",
        side_effect=requests.exceptions.ConnectionError("Connection refused"),
    ):
        with pytest.raises(RuntimeError, match="Failed to connect to NSRDB API"):
            fetch_location_year(
                39.62,
                -104.61,
                2023,
                raw_dir=tmp_path,
                api_key="k",
                email="e@e.com",
                force_download=True,
            )


def test_fetch_cli_cache_hit(sample_csv_path: Path, tmp_path: Path):
    """Verify CLI execution works when cache hit occurs."""
    cmd = [
        sys.executable,
        "-m",
        "pipeline.fetch_nsrdb",
        "--lat",
        "39.62",
        "--lon",
        "-104.61",
        "--year",
        "2023",
        "--output-dir",
        str(tmp_path),
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    assert res.returncode == 0
    assert "Success:" in res.stdout
    assert str(sample_csv_path) in res.stdout
