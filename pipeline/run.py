"""Checkpoint runner: location -> weather -> annual energy -> recommendation -> JSON.

Use --energy-table to export an existing model result entirely offline.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
from pathlib import Path

import pandas as pd

from pipeline.energy_model import DEFAULT_AZIMUTHS, DEFAULT_TILTS, compute_energy_table
from pipeline.export import build_dashboard_payload, write_dashboard_json
from pipeline.optimize import DEFAULT_LAMBDA
from pipeline.preprocess import PROCESSED_DIR
from pipeline.system_config import DEFAULT_SYSTEM_CONFIG, SystemConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--energy-table", type=Path, help="Export an existing Parquet without downloads"
    )
    parser.add_argument("--name")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--years", type=int, nargs="+")
    parser.add_argument(
        "--train-years",
        type=int,
        nargs="+",
        required=True,
        help="Earlier years used for selection; remaining years are held out",
    )
    parser.add_argument("--lambda", dest="lambda_", type=float, default=DEFAULT_LAMBDA)
    parser.add_argument(
        "--system-config",
        type=Path,
        help="JSON object of SystemConfig overrides (new simulations only)",
    )
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "web/public/data")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.lambda_) or args.lambda_ < 0:
            raise ValueError("lambda must be finite and nonnegative")
        if len(set(args.train_years)) != len(args.train_years):
            raise ValueError("train-years must not contain duplicates")
        if args.energy_table is not None:
            if any(
                v is not None
                for v in (
                    args.name,
                    args.lat,
                    args.lon,
                    args.years,
                    args.system_config,
                    args.raw_dir,
                )
            ):
                raise ValueError("--energy-table cannot be combined with new-simulation inputs")
            table = pd.read_parquet(args.energy_table)
            energy_path = args.energy_table
        else:
            if any(v is None for v in (args.name, args.lat, args.lon, args.years)):
                raise ValueError("Provide --energy-table or all of --name, --lat, --lon, --years")
            if not set(args.train_years).issubset(args.years):
                raise ValueError("train-years must be included in years")
            held_out = set(args.years) - set(args.train_years)
            if held_out and min(held_out) <= max(args.train_years):
                raise ValueError("Held-out years must be later than all training years")
            system = DEFAULT_SYSTEM_CONFIG
            if args.system_config is not None:
                settings = json.loads(args.system_config.read_text(encoding="utf-8"))
                if not isinstance(settings, dict):
                    raise ValueError("system-config must contain a JSON object")
                system = SystemConfig(**settings)
            table = compute_energy_table(
                {"name": args.name, "lat": args.lat, "lon": args.lon},
                args.years,
                DEFAULT_TILTS,
                DEFAULT_AZIMUTHS,
                system=system,
                raw_dir=args.raw_dir,
            )
            slug = re.sub(r"[^a-z0-9]+", "_", args.name.lower()).strip("_") or "location"
            energy_path = args.processed_dir / f"energy_{slug}.parquet"
        payload = build_dashboard_payload(table, args.train_years, lambda_=args.lambda_)
        slug = re.sub(r"[^a-z0-9]+", "_", payload["recommendation"]["location"].lower()).strip("_")
        if args.energy_table is None:
            energy_path.parent.mkdir(parents=True, exist_ok=True)
            table.to_parquet(energy_path, engine="pyarrow", index=False)
        output = write_dashboard_json(payload, args.output_dir / f"{slug or 'location'}.json")
        print(f"Energy table: {energy_path}")
        print(f"Dashboard bundle: {output}")
        print(f"Recommendation: {payload['recommendation']['recommended']}")
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        logger.error("Pipeline failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
