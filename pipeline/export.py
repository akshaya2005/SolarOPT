"""Serialize the canonical energy table for browser visualizations."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from pipeline.optimize import DEFAULT_LAMBDA, recommend_configuration, score
from pipeline.system_config import SystemConfig

SCHEMA_VERSION = "1.0"
METADATA_FIELDS = (
    "system",
    "energy_basis",
    "years",
    "requested_location",
    "weather_sources",
    "models",
    "pvlib_version",
)


def _summary(values: pd.Series, lambda_: float) -> dict | None:
    if values.empty:
        return None
    return {
        "count": len(values),
        "mean_kwh": float(values.mean()),
        "std_kwh": float(values.std(ddof=0)),
        "min_kwh": float(values.min()),
        "max_kwh": float(values.max()),
        "score": score(values, lambda_),
    }


def build_dashboard_payload(
    energy_table: pd.DataFrame,
    train_years: list[int],
    *,
    lambda_: float = DEFAULT_LAMBDA,
) -> dict:
    """Return versioned JSON data derived from one location's annual energy table.

    Metadata is an explicit allowlist, not a dump of raw provider headers or local
    environment. All configurations retain annual values and training statistics
    so the frontend can rerank for another lambda without involving held-out years.
    """
    missing = set(METADATA_FIELDS) - set(energy_table.attrs)
    if missing:
        raise ValueError(f"Energy table is missing provenance metadata: {sorted(missing)}")
    metadata = {key: energy_table.attrs[key] for key in METADATA_FIELDS}
    metadata["system"] = asdict(SystemConfig(**metadata["system"]))
    if metadata["energy_basis"] != "AC kWh":
        raise ValueError("Energy table must report AC kWh")
    location = metadata["requested_location"]
    result = recommend_configuration(
        energy_table,
        train_years,
        lambda_=lambda_,
        latitude=location["lat"],
    )
    years = sorted(int(y) for y in energy_table["year"].unique())
    if metadata["years"] != years or set(metadata["weather_sources"]) != {str(y) for y in years}:
        raise ValueError("Provenance years must match the energy table")
    if location["name"] != result["location"]:
        raise ValueError("Provenance location must match the energy table")
    configurations = []
    for (tilt, azimuth), rows in energy_table.groupby(["tilt", "azimuth"], sort=True):
        values = rows.sort_values("year").set_index("year")["kwh"]
        configurations.append(
            {
                "tilt": float(tilt),
                "azimuth": float(azimuth),
                "per_year": {str(int(year)): float(kwh) for year, kwh in values.items()},
                "training": _summary(values.loc[result["train_years"]], lambda_),
                "held_out": _summary(values.loc[result["held_out_years"]], lambda_),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "metadata": metadata,
        "recommendation": result,
        "configurations": configurations,
    }
    # Fail before writing on NaN, Infinity, or non-JSON metadata.
    json.dumps(payload, allow_nan=False)
    return payload


def write_dashboard_json(payload: dict, output: Path) -> Path:
    """Atomically replace one bundle so a browser cannot read a partial export."""
    text = json.dumps(payload, allow_nan=False, indent=2) + "\n"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            temporary = Path(f.name)
            f.write(text)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output
