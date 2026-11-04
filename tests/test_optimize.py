"""Tests for pipeline/optimize.py."""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.optimize import recommend_configuration, score


def _make_table(location: str, rows: list[tuple[float, float, int, float]]) -> pd.DataFrame:
    """Build an energy table from (tilt, azimuth, year, kwh) rows."""
    return pd.DataFrame(
        [
            {"location": location, "tilt": tilt, "azimuth": azimuth, "year": year, "kwh": kwh}
            for tilt, azimuth, year, kwh in rows
        ]
    )


def test_score_steady_config_beats_swingy_config_with_same_mean():
    """At lambda=0.5, a steady config should outscore a swingy one with equal mean output."""
    steady = pd.Series([1000.0, 1000.0, 1000.0])
    swingy = pd.Series([1300.0, 1000.0, 700.0])

    assert steady.mean() == swingy.mean()
    assert score(steady, lambda_=0.5) > score(swingy, lambda_=0.5)
    assert score(steady, lambda_=0.5) == pytest.approx(1000.0)


def test_score_single_year_equals_mean_not_nan():
    """A single-year series has no variability to penalize, so score == mean."""
    assert score(pd.Series([1234.5]), lambda_=0.5) == pytest.approx(1234.5)


def test_lambda_zero_ignores_variability():
    """lambda=0 should pick the highest-mean config even if it's less consistent."""
    high_mean_swingy = pd.Series([1300.0, 1100.0, 1000.0])
    low_mean_steady = pd.Series([1100.0, 1100.0, 1100.0])

    assert score(high_mean_swingy, lambda_=0.0) > score(low_mean_steady, lambda_=0.0)


def test_recommend_configuration_picks_steadier_config_at_default_lambda():
    """Config B has a higher raw mean but swings a lot; A should win at lambda=0.5."""
    table = _make_table(
        "Denver, CO",
        [
            (20.0, 180.0, 2018, 1000.0),
            (20.0, 180.0, 2019, 1000.0),
            (20.0, 180.0, 2020, 1000.0),
            (40.0, 180.0, 2018, 1300.0),
            (40.0, 180.0, 2019, 1000.0),
            (40.0, 180.0, 2020, 700.0),
        ],
    )

    result = recommend_configuration(table, train_years=[2018, 2019, 2020], lambda_=0.5)

    assert result["recommended"] == {"tilt": 20.0, "azimuth": 180.0}
    assert result["score"] == pytest.approx(1000.0)
    assert result["objective"] == "mean_minus_lambda_std"
    assert result["lambda"] == 0.5
    assert result["location"] == "Denver, CO"


def test_recommend_configuration_per_year_covers_all_years_not_just_train():
    """per_year should report the recommended config's output across every year in the table."""
    table = _make_table(
        "Denver, CO",
        [
            (20.0, 180.0, 2018, 900.0),
            (20.0, 180.0, 2019, 1100.0),
            (20.0, 180.0, 2020, 1200.0),  # held-out
            (40.0, 180.0, 2018, 500.0),
            (40.0, 180.0, 2019, 500.0),
            (40.0, 180.0, 2020, 500.0),
        ],
    )

    result = recommend_configuration(table, train_years=[2018, 2019], lambda_=0.5)

    assert result["per_year"] == {"2018": 900.0, "2019": 1100.0, "2020": 1200.0}
    assert result["held_out_test_score"] == pytest.approx(1200.0)


def test_recommend_configuration_no_held_out_years_is_none():
    """When train_years covers every year in the table, there's nothing to hold out."""
    table = _make_table(
        "Denver, CO",
        [
            (20.0, 180.0, 2018, 900.0),
            (20.0, 180.0, 2019, 1100.0),
        ],
    )

    result = recommend_configuration(table, train_years=[2018, 2019])

    assert result["held_out_test_score"] is None
    assert result["per_year"] == {"2018": 900.0, "2019": 1100.0}


def test_recommend_configuration_lat_tilt_baseline_snaps_to_grid():
    """The lat-tilt baseline should snap latitude to the nearest tilt actually in the grid."""
    table = _make_table(
        "Denver, CO",
        [
            (30.0, 170.0, 2018, 800.0),
            (40.0, 180.0, 2018, 900.0),
            (30.0, 170.0, 2019, 800.0),
            (40.0, 180.0, 2019, 900.0),
        ],
    )

    result = recommend_configuration(table, train_years=[2018, 2019], latitude=39.7)

    assert result["baselines"]["lat_tilt"] == {
        "tilt": 40.0,
        "azimuth": 180.0,
        "score": pytest.approx(900.0),
    }


def test_recommend_configuration_lat_tilt_baseline_omitted_without_latitude():
    """No latitude provided means no lat-tilt baseline, not a crash."""
    table = _make_table(
        "Denver, CO",
        [
            (30.0, 170.0, 2018, 800.0),
            (40.0, 180.0, 2018, 900.0),
        ],
    )

    result = recommend_configuration(table, train_years=[2018])

    assert result["baselines"]["lat_tilt"] is None


def test_recommend_configuration_tmy_best_baseline_picks_representative_year():
    """tmy_best picks the train year closest to the mean across years, then its best config."""
    table = _make_table(
        "Denver, CO",
        [
            # 2018 is a low-irradiance year, 2019 is typical, 2020 is high -- 2019 is
            # the representative year by mean-kwh-across-configs.
            (20.0, 180.0, 2018, 500.0),
            (40.0, 180.0, 2018, 400.0),
            (20.0, 180.0, 2019, 700.0),
            (40.0, 180.0, 2019, 900.0),
            (20.0, 180.0, 2020, 1100.0),
            (40.0, 180.0, 2020, 1300.0),
        ],
    )

    result = recommend_configuration(table, train_years=[2018, 2019, 2020])

    assert result["baselines"]["tmy_best"]["representative_year"] == 2019
    assert result["baselines"]["tmy_best"]["tilt"] == 40.0
    assert result["baselines"]["tmy_best"]["azimuth"] == 180.0


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda df: df.drop(columns=["kwh"]), "missing required column"),
        (lambda df: df.iloc[0:0], "empty"),
    ],
)
def test_recommend_configuration_rejects_malformed_table(mutate, match):
    table = _make_table("Denver, CO", [(20.0, 180.0, 2018, 900.0)])
    with pytest.raises(ValueError, match=match):
        recommend_configuration(mutate(table), train_years=[2018])


def test_recommend_configuration_rejects_multiple_locations():
    table = pd.concat(
        [
            _make_table("Denver, CO", [(20.0, 180.0, 2018, 900.0)]),
            _make_table("Phoenix, AZ", [(20.0, 180.0, 2018, 900.0)]),
        ]
    )
    with pytest.raises(ValueError, match="single location"):
        recommend_configuration(table, train_years=[2018])


def test_recommend_configuration_rejects_empty_train_years():
    table = _make_table("Denver, CO", [(20.0, 180.0, 2018, 900.0)])
    with pytest.raises(ValueError, match="train_years must be non-empty"):
        recommend_configuration(table, train_years=[])


def test_recommend_configuration_rejects_train_years_not_in_table():
    table = _make_table("Denver, CO", [(20.0, 180.0, 2018, 900.0)])
    with pytest.raises(ValueError, match="not present in energy_table"):
        recommend_configuration(table, train_years=[2018, 2099])


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "0.5"])
def test_rejects_invalid_risk_weight(value):
    table = _make_table("Denver", [(20, 180, 2023, 1000)])
    with pytest.raises(ValueError, match="lambda"):
        recommend_configuration(table, [2023], lambda_=value)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda df: pd.concat([df, df.iloc[[0]]]), "Duplicate configuration-year"),
        (lambda df: df.iloc[:-1], "same complete set"),
        (lambda df: df.assign(kwh=float("nan")), "finite numeric"),
        (lambda df: df.assign(kwh=float("inf")), "finite numeric"),
        (lambda df: df.assign(kwh=-100), "nonnegative"),
        (lambda df: df.assign(year=2023.5), "integers"),
        (lambda df: df.assign(location=None), "nonempty names"),
    ],
)
def test_rejects_unbalanced_or_invalid_energy_table(mutate, match):
    table = _make_table(
        "Denver",
        [
            (20, 180, 2022, 1000),
            (20, 180, 2023, 1100),
            (30, 180, 2022, 1050),
            (30, 180, 2023, 1150),
        ],
    )
    with pytest.raises(ValueError, match=match):
        recommend_configuration(mutate(table), [2022])


def test_split_and_deterministic_sparse_baseline():
    table = _make_table(
        "Denver",
        [
            (30, 170, 2022, 1000),
            (30, 170, 2023, 1100),
            (40, 180, 2022, 1050),
            (40, 180, 2023, 1150),
        ],
    )
    with pytest.raises(ValueError, match="later"):
        recommend_configuration(table, [2023])
    with pytest.raises(ValueError, match="duplicates"):
        recommend_configuration(table, [2022, 2022])
    result = recommend_configuration(table, [2022], latitude=30)
    baseline = result["baselines"]["lat_tilt"]
    assert (baseline["tilt"], baseline["azimuth"]) == (30, 170)
    assert result == recommend_configuration(table.iloc[::-1], [2022], latitude=30)
    assert result["train_years"] == [2022]
    assert result["held_out_years"] == [2023]
