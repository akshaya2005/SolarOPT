"""Exercise cached raw weather through modeling, optimization and browser JSON."""

import json
from pathlib import Path

import pandas as pd
import pytest
from conftest import make_mock_nsrdb_csv

from pipeline import run
from pipeline.export import build_dashboard_payload, write_dashboard_json
from pipeline.fetch_nsrdb import get_raw_filename


def test_complete_runner_and_offline_export(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    for year in (2022, 2023):
        (raw / get_raw_filename(39.62, -104.61, year)).write_text(
            make_mock_nsrdb_csv(year=year), encoding="utf-8"
        )

    def no_network(*args, **kwargs):
        pytest.fail("Cached checkpoint run must not require network access")

    monkeypatch.setattr("requests.get", no_network)
    output = tmp_path / "public"
    processed = tmp_path / "processed"
    settings = tmp_path / "system.json"
    settings.write_text('{"capacity_kw": 5}', encoding="utf-8")
    assert (
        run.main(
            [
                "--name",
                "Denver, CO",
                "--lat",
                "39.62",
                "--lon",
                "-104.61",
                "--years",
                "2022",
                "2023",
                "--train-years",
                "2022",
                "--raw-dir",
                str(raw),
                "--processed-dir",
                str(processed),
                "--output-dir",
                str(output),
                "--system-config",
                str(settings),
            ]
        )
        == 0
    )
    bundle_path = output / "denver_co.json"
    payload = json.loads(bundle_path.read_text())
    assert payload["schema_version"] == "1.0"
    assert payload["metadata"]["system"]["capacity_kw"] == 5
    assert payload["recommendation"]["train_years"] == [2022]
    assert payload["recommendation"]["held_out_years"] == [2023]
    assert len(payload["configurations"]) == 361
    recommended = payload["recommendation"]["recommended"]
    selected = next(
        c
        for c in payload["configurations"]
        if c["tilt"] == recommended["tilt"] and c["azimuth"] == recommended["azimuth"]
    )
    assert selected["training"]["score"] == pytest.approx(payload["recommendation"]["score"])
    assert selected["held_out"]["mean_kwh"] == pytest.approx(
        payload["recommendation"]["per_year"]["2023"]
    )
    table_path = processed / "energy_denver_co.parquet"
    table = pd.read_parquet(table_path)
    assert len(table) == 722
    assert {str(year) for year in table.year.unique()} == set(selected["per_year"])
    monkeypatch.setattr(run, "compute_energy_table", no_network)
    # Re-exporting the table is deterministic, independent of modeling or credentials.
    previous = bundle_path.read_bytes()
    assert (
        run.main(
            [
                "--energy-table",
                str(table_path),
                "--train-years",
                "2022",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert bundle_path.read_bytes() == previous
    assert (
        run.main(
            [
                "--energy-table",
                str(table_path),
                "--train-years",
                "2023",
                "--output-dir",
                str(output),
            ]
        )
        == 1
    )
    assert bundle_path.read_bytes() == previous
    # Inconsistent provenance and nonfinite values cannot reach the browser.
    table.attrs["years"] = [2022]
    with pytest.raises(ValueError, match="Provenance years"):
        build_dashboard_payload(table, [2022])


def test_invalid_json_preserves_previous_export(tmp_path):
    output = tmp_path / "bundle.json"
    output.write_text('{"previous": true}')
    with pytest.raises(ValueError):
        write_dashboard_json({"energy": float("nan")}, output)
    assert json.loads(output.read_text()) == {"previous": True}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "extra",
    [
        ["--train-years", "2023"],
        ["--train-years", "2022", "--lambda", "nan"],
        ["--train-years", "2022", "2022"],
    ],
)
def test_invalid_run_fails_before_download(extra, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid request must fail before fetching or modeling")

    monkeypatch.setattr(run, "compute_energy_table", unexpected)
    assert (
        run.main(
            [
                "--name",
                "Denver",
                "--lat",
                "39.62",
                "--lon",
                "-104.61",
                "--years",
                "2022",
                "2023",
                *extra,
            ]
        )
        == 1
    )


def test_single_year_bundle_has_no_held_out_statistics():
    # Checked-in real sample lets frontend developers work without API credentials.
    root = Path(__file__).resolve().parents[1]
    sample = json.loads((root / "web/public/data/denver_co.json").read_text())
    assert sample["recommendation"]["held_out_years"] == []
    assert all(c["held_out"] is None for c in sample["configurations"])
    assert sample["metadata"]["energy_basis"] == "AC kWh"
    assert len(sample["configurations"]) == 361
