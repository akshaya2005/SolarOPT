# SolarOPT

Finds the panel tilt/azimuth configuration that optimizes solar energy output
(and its robustness across years) for a given location, using NSRDB weather
data and the pvlib energy model.

## Setup

Use Python **3.12 or newer**. Direct Python dependencies are pinned to the versions
used for the checkpoint checks.

### Pipeline (Python)

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # fill in your NSRDB API key + email
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your NSRDB API key + email
```

#### Obtaining NSRDB API Credentials
1. Register for a free API key at [NREL / NLR Developer Network](https://developer.nlr.gov/signup/) or [NREL Developer Network](https://developer.nrel.gov/signup/).
2. Copy `.env.example` to `.env` in the repository root:
   ```env
   NSRDB_API_KEY=your_actual_api_key
   NSRDB_EMAIL=your_registered_email@example.com
   ```
3. Credentials are automatically loaded via `python-dotenv`. API keys are never logged, printed, or committed.

### Dashboard (web)

The web dashboard is scaffolded using Vite + React. Core visualization dependencies
(`three`, `@react-three/fiber`, `leaflet`, `plotly.js`) are installed in `web/package.json`.
Interactive UI components are currently in development by the frontend team.

```bash
cd web
npm install
npm run dev
```

## Running the Data Pipeline

### Checkpoint handoff: ready-to-use visualization data

Real modeled samples are included in `web/public/data/miami_fl.json` (2018–2025)
and `web/public/data/denver_co.json` (2023). Frontend developers can load these files
immediately without a Python environment or NSRDB credentials. See
[the frontend handoff guide](docs/frontend_handoff.md) for fields and JavaScript examples.

To run all stages from coordinates with the default system:

```bash
python -m pipeline.run --name "Miami, FL" --lat 25.7617 --lon -80.1918 \
  --years 2018 2019 2020 2021 2022 2023 2024 2025 \
  --train-years 2018 2019 2020 2021 2022 2023 2024
```

This fetches/caches weather, preprocesses it, models the 361 configurations, selects
on the training years, and writes `data/processed/energy_miami_fl.parquet` plus
`web/public/data/miami_fl.json`. All other requested years are held out and must be
later than the training years. For a single-year demo, pass that year as both
`--years` and `--train-years`; held-out results are then `null`.

Use `--system-config path/to/system.json` to provide overrides such as
`{"capacity_kw": 5}`. Use `--lambda 0.5` to set the robustness weight and
`--output-dir` to choose where the dashboard bundle is written. To rebuild a bundle
from a saved energy table without downloading or recomputing weather:

```bash
python -m pipeline.run --energy-table data/processed/energy_miami_fl.parquet \
  --train-years 2018 2019 2020 2021 2022 2023 2024
```

The checkpoint pipeline is an offline/precomputed workflow. Name/address geocoding,
automatic year discovery, a hosted request API, background jobs, and deployment are
not implemented. Run Python with credentials on the data side; share only the derived
JSON with the frontend.

### Ingestion & Preprocessing (Implemented)

```bash
# Step 1: Download Denver weather data (cached in data/raw/ using standardized naming)
python -m pipeline.fetch_nsrdb --lat 39.62 --lon -104.61 --year 2023

# Step 2: Clean, validate, and preprocess downloaded data into standardized Parquet
python -m pipeline.preprocess --input data/raw/nsrdb_39.6200_-104.6100_2023.csv
```

Raw NSRDB pulls are not committed — they're cached locally in `data/raw/` via
`fetch_nsrdb.py`, or shared through a team drive if a full rebuild is too slow.
If a valid raw file is already in `data/raw/`, `fetch_nsrdb` reuses it automatically
without making a network request.

### Energy Estimation (Implemented)

Start from a location and explicit historical years. The energy model fetches or
reuses raw weather, preprocesses it, and evaluates the full 361-orientation grid:

```bash
python -m pipeline.energy_model --name "Denver, CO" --lat 39.62 --lon -104.61 \
  --years 2022 2023 --capacity-kw 5
# writes data/processed/energy_denver_co.parquet
```

The output contains annual **AC kWh**, accounting for panel orientation, direct and
diffuse sunlight, ground reflection, cell temperature, incidence losses, aggregate
system losses, and inverter efficiency/clipping. The default is a 1 kW DC open-rack
reference system; use `--capacity-kw`, `--dc-ac-ratio`, `--losses-percent`, and
`--temperature-model` for the system being modeled. `--inverter-efficiency` and
`--gamma-pdc` also override the corresponding system settings. Run `--help` for grid and output
options. The physical assumptions and source metadata are saved with the table.

All system defaults and validation live in `pipeline/system_config.py`. Python callers
can import `SystemConfig` from that module and pass `system=SystemConfig(capacity_kw=5)`
to either modeling function. A future web API can construct the same model from user settings.

For already-preprocessed data, pass `weather_by_year={2023: df}` to
`compute_energy_table`; `simulate_configuration(df, tilt=35, azimuth=180)` returns
hourly irradiance, cell temperature, power and energy for one orientation.

The optimizer can consume this table directly:

```python
import pandas as pd
from pipeline.optimize import recommend_configuration

table = pd.read_parquet("data/processed/energy_denver_co.parquet")
result = recommend_configuration(table, train_years=[2022], latitude=39.62)
```

This two-year example illustrates the interface; use more historical years to
assess variability. Year availability discovery and location-name geocoding remain
separate integration work; `pipeline.run` now handles dashboard JSON export.

## Testing

Run the automated test suite locally:

```bash
pytest -v
```

- **Offline testing:** Unit tests run completely offline without hitting the NSRDB API,
  using synthetic SAM CSV fixtures generated dynamically in `tests/conftest.py`.
- **Real dataset test:** The full-year 2023 Denver dataset test (`test_load_and_clean_full_real_sample`)
  runs automatically whenever `995709_39.62_-104.61_2023.csv` or the pipeline's
  `nsrdb_39.6200_-104.6100_2023.csv` is present in `data/raw/`.
  If the file is absent on a fresh clone, the test is skipped gracefully without failing the suite.

## Repo layout

```
solaropt/
├── .env.example          # Template for NSRDB API credentials (copy to .env)
├── .gitignore            # Excludes .venv/, .env, data/raw/, and *.parquet
├── .pre-commit-config.yaml # Pre-commit hook configuration for Ruff
├── .github/workflows/    # CI: automated pytest and ruff checks on push/PR
├── docs/                 # data_contract.md, design_decisions.md, user-study plan
├── pipeline/
│   ├── fetch_nsrdb.py    # NSRDB API pulls & caching (implemented)
│   ├── preprocess.py     # Cleaning & validation -> Parquet (implemented)
│   ├── energy_model.py   # pvlib model: location x tilt x azimuth x year -> AC kWh
│   ├── system_config.py  # Shared PV system defaults, thermal presets, and validation
│   ├── run.py            # One-command pipeline and offline dashboard export
│   ├── export.py         # Versioned JSON derived from the energy table
│   └── optimize.py       # Robustness-aware configuration search (Python API)
├── tests/                # Offline unit tests & fixtures (conftest.py, test_fetch_nsrdb, test_preprocess)
├── data/                 # raw/ (gitignored); processed/ (holds small, committed outputs)
└── web/                  # Vite + React frontend (three, leaflet, and plotly dependencies scaffolded)
```

## Contracts and decisions

Before changing the energy table schema or optimizer output, read and update:

- [docs/data_contract.md](docs/data_contract.md) — location/config grid, weather schema, table and
  JSON schemas every stage reads and writes.
- [docs/design_decisions.md](docs/design_decisions.md) — robustness objective,
  baseline, held-out-year split, validation approach, user-study tasks.

## Workflow

- `main` should stay deployable; work on feature branches, merge via PR with at
  least one reviewer. (Enable branch protection on `main` once this repo has a
  GitHub remote — Settings -> Branches.)
- One GitHub issue per timeline row, assigned to its owners.
- Code quality checks:
  ```bash
  python -m ruff check .
  python -m ruff format --check .
  python -m pytest -v
  ```
- (Optional) Install pre-commit hooks to automate checks before each commit:
  ```bash
  pre-commit install
  ```
