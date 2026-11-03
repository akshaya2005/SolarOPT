"""Pick a recommended configuration from an energy table and score it.

Output schema (see docs/data_contract.md): recommended configuration,
scores, and per-year spread, as JSON the frontend loads directly.
"""

import pandas as pd


def recommend_configuration(energy_table: pd.DataFrame, train_years: list[int]) -> dict:
    """Select a configuration using train_years only; report scores for all years."""
    raise NotImplementedError
