# SolarOPT

Finds the panel tilt/azimuth configuration that optimizes solar energy output
(and its robustness across years) for a given location, using NSRDB weather
data and the pvlib energy model.

## Setup

### Pipeline (Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own NSRDB API key + email (per-key rate limits)
```

### Dashboard (web)

```bash
cd web
npm install
npm run dev
```

## Running the pipeline end to end

```bash
python -m pipeline.fetch_nsrdb      # pulls raw NSRDB data into data/raw/ (gitignored)
python -m pipeline.preprocess       # cleans raw pulls
python -m pipeline.energy_model     # builds data/processed/energy_<location>.parquet
python -m pipeline.optimize         # writes the recommendation JSON the dashboard reads
```

Raw NSRDB pulls are not committed — they're regenerated locally via
`fetch_nsrdb.py`, or shared through a team drive if a full rebuild is too slow.

## Repo layout

```
solaropt/
├── docs/                # data_contract.md, design_decisions.md, user-study plan
├── pipeline/
│   ├── fetch_nsrdb.py    # NSRDB pulls
│   ├── preprocess.py      # cleaning
│   ├── energy_model.py    # pvlib model: location x tilt x azimuth x year -> kWh
│   └── optimize.py        # robustness-aware configuration search
├── tests/                 # sample_data/ lets tests run without hitting the NSRDB API
├── data/                  # raw/ gitignored; processed/ holds small, committed outputs
├── web/                   # Vite + React dashboard (Three.js 3D view, Leaflet map, Plotly heatmaps)
└── .github/workflows/     # CI: pytest + ruff on the pipeline, build check on web
```

## Contracts and decisions

Before changing the energy table schema or optimizer output, read and update:

- [docs/data_contract.md](docs/data_contract.md) — location/config grid, table and
  JSON schemas every stage reads and writes.
- [docs/design_decisions.md](docs/design_decisions.md) — robustness objective,
  baseline, held-out-year split, validation approach, user-study tasks.

## Workflow

- `main` should stay deployable; work on feature branches, merge via PR with at
  least one reviewer. (Enable branch protection on `main` once this repo has a
  GitHub remote — Settings -> Branches.)
- One GitHub issue per timeline row, assigned to its owners.
- `pre-commit install` once, to run ruff/prettier automatically before each commit.
