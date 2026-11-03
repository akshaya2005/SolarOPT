"""Clean raw NSRDB pulls into the hourly series the energy model needs."""

from pathlib import Path

import pandas as pd


def load_and_clean(raw_path: Path) -> pd.DataFrame:
    """Load one raw NSRDB file and return a cleaned hourly DataFrame."""
    raise NotImplementedError
