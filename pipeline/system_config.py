"""PV system defaults and validation shared by the pipeline and future web API.

Construct SystemConfig(**settings) from a mapping of user-selected settings;
omitted fields use the defaults below. dataclasses.asdict(config) produces a
JSON-serializable mapping for API responses and stored model provenance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

TEMPERATURE_MODELS = TEMPERATURE_MODEL_PARAMETERS["sapm"]


@dataclass(frozen=True)
class SystemConfig:
    """Generic monofacial system assumptions; capacity is the DC STC rating.

    dc_ac_ratio = DC nameplate / AC nameplate. Losses are a single aggregate
    DC derate, separate from modeled temperature, incidence and inverter losses.
    SAPM uses wind speed at 10 m, matching the weather data contract.
    Instances are immutable so one request cannot change another's settings.
    """

    capacity_kw: float = 1.0
    dc_ac_ratio: float = 1.2
    inverter_efficiency: float = 0.96
    gamma_pdc: float = -0.004
    losses_percent: float = 14.0
    temperature_model: str = "open_rack_glass_polymer"

    def __post_init__(self) -> None:
        for name in (
            "capacity_kw",
            "dc_ac_ratio",
            "inverter_efficiency",
            "gamma_pdc",
            "losses_percent",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        for name in ("capacity_kw", "dc_ac_ratio", "inverter_efficiency"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.inverter_efficiency > 1:
            raise ValueError("inverter_efficiency must be <= 1")
        if not math.isfinite(self.gamma_pdc) or not -0.02 <= self.gamma_pdc <= 0:
            raise ValueError("gamma_pdc must be between -0.02 and 0 per degree C")
        if not math.isfinite(self.losses_percent) or not 0 <= self.losses_percent < 100:
            raise ValueError("losses_percent must be between 0 (inclusive) and 100 (exclusive)")
        if (
            not isinstance(self.temperature_model, str)
            or self.temperature_model not in TEMPERATURE_MODELS
        ):
            raise ValueError(f"temperature_model must be one of {list(TEMPERATURE_MODELS)}")


DEFAULT_SYSTEM_CONFIG = SystemConfig()
