# Data contract

Status: **implemented checkpoint contract**. The browser bundle has schema version
`1.0`. Physical defaults remain configurable assumptions. Update this document and
the export version together when making a breaking change for frontend consumers.

## Weather data contract (fetch_nsrdb.py -> preprocess.py -> energy_model.py)

### Raw NSRDB Ingestion (`fetch_nsrdb.py`)
- **API Source**: NSRDB GOES CONUS PSM v4 API (`https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-conus-v4-0-0-download.csv`).
- **Coverage**: Continental United States (CONUS), years 2018+.
- **Storage**: `data/raw/` (gitignored, cached by coordinates, year, and interval).
- **Format**: Standard SAM CSV beginning with 2 metadata header rows, followed by observation column names on row 3, and hourly data rows.
- **Attributes Requested**: `ghi,dni,dhi,air_temperature,wind_speed,surface_albedo,cloud_type,fill_flag`.
- **Temporal Resolution**: 60-minute observations timestamped in UTC (typically at `HH:30`), with leap day included (8,760 records for non-leap years; 8,784 for leap years).

### Cleaned Weather Schema (`preprocess.py`)
Stored as a Parquet file or returned as an in-memory `pd.DataFrame`.

- **Index**: Timezone-aware UTC `pd.DatetimeIndex` named `timestamp`. Native `:30` minute offsets are preserved.
- **Columns**:

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `ghi` | `float64` | W/m² | Global horizontal irradiance |
| `dni` | `float64` | W/m² | Direct normal irradiance |
| `dhi` | `float64` | W/m² | Diffuse horizontal irradiance |
| `temp_air` | `float64` | °C | Ambient air temperature |
| `wind_speed` | `float64` | m/s | Wind speed at 10m |
| `surface_albedo` | `float64` | [0.0, 1.0] | Ground surface reflectivity |
| `cloud_type` | `int64` | code | Source cloud classification |
| `fill_flag` | `int64` | code | Source data quality/fill flag |

- **Metadata Attributes (`df.attrs`)**:
  Location and provenance metadata are stored in `df.attrs` and preserved across Parquet serialization:
  - `latitude` (`float`): Actual NSRDB grid point latitude.
  - `longitude` (`float`): Actual NSRDB grid point longitude.
  - `elevation` (`float`): Elevation in meters above sea level.
  - `source_version` (`str`): NSRDB model version (e.g. `4.0.1`).
  - `year` (`int`): Observation year.
  - `location_id` (`str`): NSRDB location identifier.

### Downstream Usage (`energy_model.py`)
Downstream consumers can load cleaned weather data directly via:
```python
import pandas as pd

df = pd.read_parquet("data/processed/<weather_file>.parquet")
lat = df.attrs["latitude"]
lon = df.attrs["longitude"]
elevation = df.attrs["elevation"]
```
NSRDB's API attribute is `surface_albedo`, returned as `Surface Albedo` in the raw
CSV. Preprocessing normalizes it to `surface_albedo`, which is used consistently
in the cleaned weather schema. `energy_model.py` adapts this source field to
pvlib's `albedo` argument when calling the irradiance model. This naming difference
comes from the two external interfaces. When using `ModelChain.run_model` directly,
rename the input column with `df.rename(columns={"surface_albedo": "albedo"})`.

Annual energy calculations additionally require a complete UTC calendar year,
including leap day, matching the requested year and metadata. A valid shorter
period from preprocessing is accepted only by `simulate_configuration` for hourly
diagnostics, never as an annual energy total.

## Location grid

- Checkpoint (11/1–11/6): 5–10 cities spanning distinct climates across the Continental US
  (CONUS, matching NSRDB PSM v4 coverage), e.g. Phoenix AZ, Seattle WA, Miami FL,
  Denver CO, Minneapolis MN, Atlanta GA. (Note: Non-CONUS locations such as Honolulu HI
  require separate regional NSRDB datasets and are excluded for this CONUS pipeline).
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
| kwh      | float | annual AC energy for the configured PV system, after losses and inverter clipping |

Stored as `data/processed/energy_<location>.parquet` (small enough to commit once
real). This one table is the single source read by both the optimizer and the
frontend heatmaps — don't fork a second format for either consumer.

**Implemented energy assumptions:** fixed, monofacial panels; 1 kW DC STC reference
capacity; DC/AC nameplate ratio 1.2; nominal inverter efficiency 0.96; temperature
coefficient -0.004/°C; aggregate DC losses 14%; SAPM open-rack glass/polymer thermal
parameters. Defaults, supported thermal presets, and validation are defined in
`pipeline/system_config.py` through `SystemConfig` and `DEFAULT_SYSTEM_CONFIG`.
Both the energy model and CLI reference these shared defaults. Output scales with capacity
when the other assumptions, including DC/AC ratio, are held fixed. A site-specific
system requires appropriate mounting, capacity, inverter, and loss inputs.

For future web/API integration, construct a configuration per request with
`SystemConfig(**settings)` and pass it as `system=` to either modeling function.
Omitted fields use the shared defaults; instances are immutable. Use
`dataclasses.asdict(DEFAULT_SYSTEM_CONFIG)` to expose defaults to the frontend and
`dataclasses.asdict(system)` to serialize the selected settings. Web request handling
is not implemented yet.

`DataFrame.attrs` records `system` (the complete configuration), `energy_basis`
(`AC kWh`), `years`, `requested_location`, `weather_sources` (actual grid coordinates,
elevation, source version, location ID, record count and timestamp bounds per year),
`models`, and `pvlib_version`. These attributes survive Parquet serialization.
All years must refer to the same grid point and elevation.

`compute_energy_table(location, years, tilts, azimuths, *, system=None,
weather_by_year=None, raw_dir=None)` fetches and preprocesses once per year by
default. Supplying a complete `weather_by_year` mapping uses already-cleaned frames
without network access. The five table columns remain unchanged for the optimizer.

`simulate_configuration(weather, tilt, azimuth, *, system=None)` provides hourly
diagnostics: `poa_global` and `effective_irradiance` (W/m²), `temp_cell` (°C),
`dc_w` (after aggregate DC losses), `ac_w` (after inverter losses/clipping), and
`kwh` (AC energy over the represented one-hour interval). Tilt is measured from
horizontal; azimuth is clockwise from north, with south at 180°. Azimuth 360° is
normalized to 0°, and duplicate configurations are rejected.

Historical annual values are modeled outcomes under each year's weather. Their
mean can support an expected-production estimate; the optimizer's risk-adjusted
score is a separate quantity, not an energy forecast or confidence bound.

## Optimizer output (optimize.py -> frontend)

JSON, one object per location:

```json
{
  "location": "Denver, CO",
  "recommended": { "tilt": 35, "azimuth": 180 },
  "objective": "mean_minus_lambda_std",
  "lambda": 0.5,
  "score": 1234.5,
  "baselines": {
    "lat_tilt": { "tilt": 40, "azimuth": 180, "score": 1180.2 },
    "tmy_best": { "tilt": 35, "azimuth": 170, "score": 1205.0, "representative_year": 2019 }
  },
  "per_year": { "2018": 1200.1, "2019": 1260.3, "2020": 1245.0 },
  "held_out_test_score": 1245.0,
  "train_years": [2018, 2019],
  "held_out_years": [2020]
}
```

`baselines.lat_tilt` is `null` if latitude wasn't supplied. `tilt`/`azimuth` in both
`recommended` and `baselines` refer to pairs actually present in the configuration
grid. The latitude baseline chooses the pair minimizing squared angular distance
to `(latitude, 180)`, breaking ties by smaller tilt then azimuth. On a full grid this
is equivalent to independently snapping both angles; sparse grids cannot produce
nonexistent baseline pairs. `tmy_best.representative_year` is a proxy for a true TMY
(the train year whose mean kwh across all configs is closest to the mean across
train years) — see [design_decisions.md](design_decisions.md) for why.

Exact field names/values here depend on the decisions in
[design_decisions.md](design_decisions.md) — update this schema in lockstep with that
doc.

The optimizer requires one finite nonnegative kWh value per configuration-year and
the same year set for all configurations. Duplicates, missing years, invalid angles,
negative/nonfinite lambda, and nonchronological splits are rejected. Population
standard deviation (`ddof=0`) is used; a single-year spread is zero, not evidence
of long-term stability. Recommendation and baseline scores use training years only.

## Browser bundle (`pipeline.run` -> `web/public/data/<location>.json`)

`pipeline/export.py` derives this JSON from the canonical energy table; it does not
run a second energy model or maintain a separate set of results.

| Field | Meaning |
|---|---|
| `schema_version` | String `"1.0"` |
| `metadata` | Energy-table attributes: `system`, `energy_basis`, `years`, `requested_location`, `weather_sources`, `models`, `pvlib_version` |
| `recommendation` | Optimizer output above, including explicit training/held-out years |
| `configurations` | One object per modeled tilt/azimuth pair, sorted by tilt then azimuth |

Each configuration contains `tilt`, `azimuth`, `per_year` (year-string -> AC kWh),
`training`, and `held_out`. Each statistics object contains `count`, `mean_kwh`,
`std_kwh`, `min_kwh`, `max_kwh`, and `score`; `held_out` is `null` if no years are
held out. There are no NaN/Infinity values in the JSON. A single file is replaced
atomically after validation, so readers do not see a partially written bundle.

Use training statistics for heatmaps/ranking and held-out statistics for evaluation.
The historical minimum and maximum are observed model outcomes, not confidence
bounds. Parameter changes require a new simulation except for reranking with lambda.
See [frontend_handoff.md](frontend_handoff.md) for concrete usage and limitations.
