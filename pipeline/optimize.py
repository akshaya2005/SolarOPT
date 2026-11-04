"""Pick a recommended configuration from an energy table and score it.

Output schema (see docs/data_contract.md): recommended configuration,
scores, and per-year spread, as JSON the frontend loads directly.
"""

from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"location", "tilt", "azimuth", "year", "kwh"}
DEFAULT_LAMBDA = 0.5
BASELINE_AZIMUTH = 180.0


def _validate_lambda(lambda_: float) -> None:
    if (
        isinstance(lambda_, bool)
        or not isinstance(lambda_, Real)
        or not math.isfinite(lambda_)
        or lambda_ < 0
    ):
        raise ValueError("lambda must be a finite nonnegative number")


def score(kwh_by_year: pd.Series, lambda_: float = DEFAULT_LAMBDA) -> float:
    """mean - lambda * std across years.

    Population std (ddof=0) so a single-year series scores as its mean (0.0,
    not NaN) instead of failing to represent variability at all.
    """
    _validate_lambda(lambda_)
    if (
        kwh_by_year.empty
        or not pd.api.types.is_numeric_dtype(kwh_by_year)
        or kwh_by_year.isna().any()
        or not np.isfinite(kwh_by_year).all()
        or (kwh_by_year < 0).any()
    ):
        raise ValueError("Annual energy must contain finite nonnegative numbers")
    return float(kwh_by_year.mean() - lambda_ * kwh_by_year.std(ddof=0))


def _best_configuration(table: pd.DataFrame, lambda_: float) -> tuple[float, float, float]:
    """Rank (tilt, azimuth) pairs by score over whatever years `table` contains."""
    scored = table.groupby(["tilt", "azimuth"])["kwh"].apply(lambda s: score(s, lambda_))
    best_tilt, best_azimuth = scored.idxmax()
    return float(best_tilt), float(best_azimuth), float(scored.max())


def _lat_tilt_baseline(table: pd.DataFrame, latitude: float, lambda_: float) -> dict:
    """Fixed-rule baseline: tilt = latitude (snapped to the grid), azimuth = 180 deg (due south)."""
    # Select an actual pair even if the supplied grid is sparse. Equal angular
    # distances are resolved by tilt, then azimuth, independent of input order.
    pairs = table[["tilt", "azimuth"]].drop_duplicates().itertuples(index=False, name=None)
    tilt, azimuth = min(
        pairs,
        key=lambda pair: (
            (pair[0] - latitude) ** 2 + (pair[1] - BASELINE_AZIMUTH) ** 2,
            pair[0],
            pair[1],
        ),
    )
    subset = table[(table["tilt"] == tilt) & (table["azimuth"] == azimuth)]
    return {"tilt": float(tilt), "azimuth": float(azimuth), "score": score(subset["kwh"], lambda_)}


def _tmy_best_baseline(table: pd.DataFrame, lambda_: float) -> dict:
    """Representative-year baseline: best single config for the train year closest to 'typical'.

    We don't have a true TMY dataset (that's a separate NSRDB product pulled per-month
    across years) -- as a proxy, "representative year" is the train year whose mean kwh
    across all configs is closest to the mean across train years. Revisit this if/when
    real TMY data is pulled (see docs/design_decisions.md).

    TMY would give us a synthetic representative year by stitching together the most statistically
    typical month across several real years.
    """
    yearly_mean = table.groupby("year")["kwh"].mean()
    representative_year = int((yearly_mean - yearly_mean.mean()).abs().idxmin())
    year_table = table[table["year"] == representative_year].sort_values(["tilt", "azimuth"])
    best_row = year_table.loc[year_table["kwh"].idxmax()]
    tilt, azimuth = float(best_row["tilt"]), float(best_row["azimuth"])
    subset = table[(table["tilt"] == tilt) & (table["azimuth"] == azimuth)]
    return {
        "tilt": tilt,
        "azimuth": azimuth,
        "score": score(subset["kwh"], lambda_),
        "representative_year": representative_year,
    }


def recommend_configuration(
    energy_table: pd.DataFrame,
    train_years: list[int],
    lambda_: float = DEFAULT_LAMBDA,
    latitude: float | None = None,
) -> dict:
    """Select a configuration using train_years only; report scores for all years.

    `energy_table` is one location's table from energy_model.py (see
    docs/data_contract.md): columns location, tilt, azimuth, year, kwh.
    `latitude` is used for the lat-tilt baseline; pass None to omit that baseline
    (e.g. when it isn't known yet).
    """
    _validate_lambda(lambda_)
    if latitude is not None and (
        isinstance(latitude, bool)
        or not isinstance(latitude, Real)
        or not math.isfinite(latitude)
        or not 0 <= latitude <= 90
    ):
        raise ValueError("latitude must be finite and between 0 and 90 for the northern baseline")
    if not energy_table.columns.is_unique:
        raise ValueError("energy_table must have unique column names")
    missing = REQUIRED_COLUMNS - set(energy_table.columns)
    if missing:
        raise ValueError(f"energy_table is missing required column(s): {sorted(missing)}")
    if energy_table.empty:
        raise ValueError("energy_table is empty")
    for col in ("tilt", "azimuth", "year", "kwh"):
        values = energy_table[col]
        if (
            not pd.api.types.is_numeric_dtype(values)
            or pd.api.types.is_bool_dtype(values)
            or pd.api.types.is_complex_dtype(values)
            or values.isna().any()
            or not np.isfinite(values).all()
        ):
            raise ValueError(f"{col} must contain finite numeric values")
    if not energy_table["tilt"].between(0, 90).all():
        raise ValueError("tilt must be between 0 and 90")
    if not ((energy_table["azimuth"] >= 0) & (energy_table["azimuth"] < 360)).all():
        raise ValueError("azimuth must be between 0 (inclusive) and 360 (exclusive)")
    if not (energy_table["year"] % 1 == 0).all():
        raise ValueError("year must contain integers")
    if (energy_table["kwh"] < 0).any():
        raise ValueError("kwh must be nonnegative")
    if not energy_table["location"].map(lambda v: isinstance(v, str) and bool(v.strip())).all():
        raise ValueError("location must contain nonempty names")

    locations = energy_table["location"].unique()
    if len(locations) != 1:
        raise ValueError(
            f"recommend_configuration expects a single location's table, got {list(locations)}"
        )

    if not train_years:
        raise ValueError("train_years must be non-empty")
    if any(isinstance(y, bool) or not isinstance(y, Integral) for y in train_years):
        raise ValueError("train_years must contain integers")
    if len(set(train_years)) != len(train_years):
        raise ValueError("train_years must not contain duplicates")
    available_years = set(energy_table["year"].unique())
    train_years_set = set(train_years)
    missing_train_years = train_years_set - available_years
    if missing_train_years:
        raise ValueError(f"train_years not present in energy_table: {sorted(missing_train_years)}")

    held_out_years = sorted(available_years - train_years_set)
    if held_out_years and min(held_out_years) <= max(train_years_set):
        raise ValueError("Held-out years must be later than all training years")
    if energy_table.duplicated(["tilt", "azimuth", "year"]).any():
        raise ValueError("Duplicate configuration-year rows are not allowed")
    counts = energy_table.groupby(["tilt", "azimuth"]).size()
    if not counts.eq(len(available_years)).all():
        raise ValueError("Every configuration must contain the same complete set of years")
    energy_table = energy_table.sort_values(["year", "tilt", "azimuth"]).reset_index(drop=True)

    train_table = energy_table[energy_table["year"].isin(train_years_set)]
    tilt, azimuth, best_score = _best_configuration(train_table, lambda_)

    recommended_rows = energy_table[
        (energy_table["tilt"] == tilt) & (energy_table["azimuth"] == azimuth)
    ]
    per_year = {
        str(int(year)): float(kwh)
        for year, kwh in recommended_rows.set_index("year")["kwh"].items()
    }

    held_out_test_score = None
    if held_out_years:
        held_out_kwh = recommended_rows[recommended_rows["year"].isin(held_out_years)]["kwh"]
        held_out_test_score = score(held_out_kwh, lambda_)

    baselines = {"lat_tilt": None, "tmy_best": _tmy_best_baseline(train_table, lambda_)}
    if latitude is not None:
        baselines["lat_tilt"] = _lat_tilt_baseline(train_table, latitude, lambda_)

    return {
        "location": str(locations[0]),
        "recommended": {"tilt": tilt, "azimuth": azimuth},
        "objective": "mean_minus_lambda_std",
        "lambda": float(lambda_),
        "score": best_score,
        "baselines": baselines,
        "per_year": per_year,
        "held_out_test_score": held_out_test_score,
        "train_years": [int(y) for y in sorted(train_years_set)],
        "held_out_years": [int(y) for y in held_out_years],
    }
