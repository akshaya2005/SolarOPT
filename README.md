# SolarOPT

Finds the panel tilt/azimuth configuration that optimizes solar energy output
(and its robustness across years) for a given location, using NSRDB weather
data and the pvlib energy model.

## Setup

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

### Planned Integration (Downstream Modules in Development)

Once downstream energy modeling and optimization components are implemented by teammates,
the complete pipeline will run:

```bash
# Step 3: Compute energy production table across tilt x azimuth angles
python -m pipeline.energy_model     # builds data/processed/energy_<location>.parquet

# Step 4: Run robustness-aware configuration search
python -m pipeline.optimize         # writes the recommendation JSON the dashboard reads
```

## Testing

Run the automated test suite locally:

```bash
pytest -v
```

- **Offline testing:** Unit tests run completely offline without hitting the NSRDB API,
  using synthetic SAM CSV fixtures generated dynamically in `tests/conftest.py`.
- **Real dataset test:** The full-year 2023 Denver dataset test (`test_load_and_clean_full_real_sample`)
  runs automatically whenever `995709_39.62_-104.61_2023.csv` is present in `data/raw/`.
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
│   ├── energy_model.py   # pvlib model: location x tilt x azimuth x year -> kWh (in development)
│   └── optimize.py       # Robustness-aware configuration search (in development)
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
