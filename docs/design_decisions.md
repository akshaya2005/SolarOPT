# Design decisions

Status: **proposed** — answers Grader B's open questions with a concrete default so
the optimizer can be built now. Each item needs a team sign-off (or a deliberate
change) before the midterm checkpoint, since it determines what the optimizer
actually computes.

## Energy estimation

Implemented in `energy_model.py` using pvlib functions, with solar geometry reused
across the configuration grid for each year:

1. NREL SPA solar position at the actual NSRDB grid point, elevation and native UTC
   timestamps; extraterrestrial irradiance and relative airmass.
2. Perez-Driesse transposition of DNI/GHI/DHI onto the panel, including the measured
   hourly surface albedo for ground reflection.
3. Physical angle-of-incidence transmission loss on the direct component. Diffuse
   irradiance is retained without an additional IAM or spectral correction, matching
   pvlib ModelChain's standard direct/diffuse effective-irradiance treatment.
4. SAPM cell temperature from incident irradiance, ambient temperature and 10 m wind.
5. PVWatts DC power from effective irradiance, cell temperature, DC nameplate and
   temperature coefficient; a configurable aggregate DC derate.
6. PVWatts inverter conversion including part-load efficiency and AC clipping. Its
   DC input limit is AC nameplate / nominal efficiency, not the array's DC nameplate.
7. Rectangular hourly integration: `annual_kwh = sum(ac_w * 1 hour) / 1000`.
   Each hourly sample represents one hour, including the last; leap years retain
   all 8,784 hours. Native timestamps are preserved without a second midpoint shift.

The 1 kW reference system defaults and validation live in
`pipeline/system_config.py` and are documented in [data_contract.md](data_contract.md).
The energy model and CLI use this shared configuration, which can later be constructed
from webapp settings per request. These are transparent generic assumptions,
not inferred equipment specifications. Roof mounting should use an appropriate
SAPM thermal preset rather than assuming an open rack.

Below-horizon output is zero. Invalid daytime calculations raise an error rather
than being filled with zeros. Complete annual data, finite weather values, valid
coordinates, and consistent grid points are checked before annual aggregation.
The NSRDB irradiance already incorporates cloud effects; cloud classifications
and fill flags are not applied as additional irradiance discounts.

This is a fixed-system historical simulation, not measured generation or a future
weather forecast. There is no explicit building/terrain shading, row shading,
bifacial gain, snow accumulation, time-varying soiling, or aging model. The aggregate
loss factor is a user assumption, not a site-specific simulation of those effects.
Hourly sampling approximates energy and clipping within the hour.

Tests compare with a separately configured pvlib ModelChain and check analytical
STC conversion, annual/leap-year integration, clipping, and physical sensitivities.
ModelChain agreement is an implementation cross-check, not independent field validation.

Model references: [Perez-Driesse](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.perez_driesse.html),
[SAPM cell temperature](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.temperature.sapm_cell.html),
[PVWatts DC](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.pvsystem.pvwatts_dc.html),
[PVWatts inverter](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.inverter.pvwatts.html).

## Robustness objective

Proposal: `score = mean(kwh) - lambda * std(kwh)` across years, with `lambda`
exposed as a slider (default 0.5) so a user can trade average output against
bad-year risk live. Alternatives considered:

- P90 (10th-percentile year) — ties to Drobinski [7]; worth adding as a second,
  switchable objective rather than the only one, since it's a single-point estimate.
- Worst-year output — simplest, but ignores the rest of the distribution.
- Minimum regret — most complex to explain to a user-study participant.

**Confirmed**: mean − λ·std only, no P90 toggle. With the handful of years NSRDB
gives us per location, a 10th-percentile estimate over n≈5-10 samples is noisy and
dominated by a single bad year — not meaningfully different from worst-year. Implemented
in `optimize.py`'s `score()`.

## Baseline

Proposal: two baselines, always shown alongside the recommendation:

1. Fixed rule: tilt = latitude, azimuth = 180° (due south, northern hemisphere).
2. Best single configuration for a representative TMY (typical meteorological year).

**Implemented** in `optimize.py` as `baselines.lat_tilt` and `baselines.tmy_best`.
We don't have a real TMY dataset yet (a separate NSRDB product, built per-month
across years), so `tmy_best` uses a proxy: the train year whose mean kwh across all
configs is closest to the mean across train years, then the best single config for
that one year. Swap in real TMY data later if time allows; the output field names
won't need to change.

## Held-out years

Proposal: split each location's available years chronologically — earlier years for
selecting the configuration, later years held out for reporting the score. Record
both the train years and the held-out score in the optimizer output (see
`held_out_test_score` in [data_contract.md](data_contract.md)). Exact split point
depends on how many years NSRDB actually provides per location (check coverage
first).

**Implemented** in `optimize.py`: `recommend_configuration(energy_table, train_years,
...)` takes the split as an explicit argument rather than picking it itself — whoever
wires up the full pipeline decides the actual split point once real year coverage is
known, and passes it in.

The checkpoint runner now takes this split through `--train-years`, rejects earlier
held-out years, and exports both year lists. Browser bundles retain per-configuration
training and held-out statistics so baseline comparisons and the lambda slider can
use the same annual energy table. Missing/duplicate configuration-years are rejected
before scoring; see [frontend_handoff.md](frontend_handoff.md).

## Validation

- PVWatts comparison demonstrates **agreement** between calculators, not validation
  against real panels — describe it that way in the report.
- If time allows, pull measured output from NREL PVDAQ for at least one location to
  get an actual validation data point.

## User-study tasks

Draft tasks (3–4, per both graders' feedback) — refine with real task-completion and
time-to-answer metrics once the dashboard exists:

1. "Find the best configuration for Denver." — measure: time to locate, whether the
   final answer matches the optimizer's recommendation.
2. "Which location has the most year-to-year variability?" — measure: whether the
   user correctly identifies it from the per-year spread view.
3. "How would the recommendation change if you cared more about bad-year risk?" —
   measure: whether moving the λ slider produces the expected directional change in
   the user's mental model (ask them to predict, then show them).
4. "Compare the recommended configuration to the latitude-tilt baseline for your
   home city." — measure: whether the user can articulate the tradeoff in their own
   words.
