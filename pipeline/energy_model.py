"""pvlib-based energy model: location x tilt x azimuth x year -> kWh.

Output schema (see docs/data_contract.md): one row per
(location, tilt, azimuth, year) with a kwh column.
"""

from collections.abc import Iterable

import pandas as pd


def compute_energy_table(
    location: dict,
    years: Iterable[int],
    tilts: Iterable[float],
    azimuths: Iterable[float],
) -> pd.DataFrame:
    """Run the pvlib model over the full config grid for one location."""
    raise NotImplementedError
