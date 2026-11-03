# Data contract

Status: **proposed** — defaults below are strawman values to unblock the checkpoint.
Confirm or change them as a team before the data/model handoff locks in; update this
file (not a side channel) when anything changes, since both pipeline and frontend code
depend on it.

## Location grid

- Checkpoint (11/1–11/6): 5–10 cities spanning distinct climates, e.g. Phoenix AZ,
  Seattle WA, Miami FL, Denver CO, Minneapolis MN, Honolulu HI.
- Post-checkpoint: a lat/lon grid (resolution TBD based on NSRDB coverage and runtime
  budget).
- Each location: `{name, lat, lon}`.

## Configuration grid

- Tilt: 0–90° in 5° steps (19 values).
- Azimuth: 90–270° in 10° steps (19 values).
- Total: 361 configurations per location-year — small enough to brute-force every one,
  matching the proposal.

## Years

- Pull whatever years the current NSRDB dataset covers for the chosen locations —
  check this directly (coverage varies by collection/location) rather than assuming a
  fixed range.
- Record the actual year list used per location in the output table; don't assume all
  locations share the same years.

## Model output (energy_model.py -> optimize.py / dashboard)

One table per location, long format:

| column   | type  | notes                        |
|----------|-------|-------------------------------|
| location | str   | matches location grid `name` |
| tilt     | float | degrees                      |
| azimuth  | float | degrees                      |
| year     | int   |                               |
| kwh      | float | annual energy output         |

Stored as `data/processed/energy_<location>.parquet` (small enough to commit once
real). This one table is the single source read by both the optimizer and the
frontend heatmaps — don't fork a second format for either consumer.

## Optimizer output (optimize.py -> frontend)

JSON, one object per location:

```json
{
  "location": "Denver, CO",
  "recommended": { "tilt": 35, "azimuth": 180 },
  "objective": "mean_minus_lambda_std",
  "lambda": 0.5,
  "score": 1234.5,
  "baseline": { "tilt": 39.7, "azimuth": 180, "score": 1180.2 },
  "per_year": { "2018": 1200.1, "2019": 1260.3, "2020": 1245.0 },
  "held_out_test_score": 1228.7
}
```

Exact field names/values here depend on the decisions in
[design_decisions.md](design_decisions.md) — update this schema in lockstep with that
doc.
