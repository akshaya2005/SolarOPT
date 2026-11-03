# Design decisions

Status: **proposed** — answers Grader B's open questions with a concrete default so
the optimizer can be built now. Each item needs a team sign-off (or a deliberate
change) before the midterm checkpoint, since it determines what the optimizer
actually computes.

## Robustness objective

Proposal: `score = mean(kwh) - lambda * std(kwh)` across years, with `lambda`
exposed as a slider (default 0.5) so a user can trade average output against
bad-year risk live. Alternatives considered:

- P90 (10th-percentile year) — ties to Drobinski [7]; worth adding as a second,
  switchable objective rather than the only one, since it's a single-point estimate.
- Worst-year output — simplest, but ignores the rest of the distribution.
- Minimum regret — most complex to explain to a user-study participant.

Decision needed: keep mean − λ·std as primary, add P90 as a toggle? Confirm before
`optimize.py` is implemented.

## Baseline

Proposal: two baselines, always shown alongside the recommendation:

1. Fixed rule: tilt = latitude, azimuth = 180° (due south, northern hemisphere).
2. Best single configuration for a representative TMY (typical meteorological year).

## Held-out years

Proposal: split each location's available years chronologically — earlier years for
selecting the configuration, later years held out for reporting the score. Record
both the train years and the held-out score in the optimizer output (see
`held_out_test_score` in [data_contract.md](data_contract.md)). Exact split point
depends on how many years NSRDB actually provides per location (check coverage
first).

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
