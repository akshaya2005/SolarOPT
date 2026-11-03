# Data contract

Status: **proposed** — defaults below are strawman values to unblock the checkpoint.
Confirm or change them as a team before the data/model handoff locks in; update this
file (not a side channel) when anything changes, since both pipeline and frontend code
depend on it.

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
Pass `df` directly to pvlib modeling chains (e.g., `pvlib.modelchain.ModelChain.run_model(df)`), as column names strictly follow pvlib weather conventions.

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
