# Frontend checkpoint handoff

The data pipeline supports precomputed location results for the checkpoint. The
dashboard can start from these real NSRDB-based files in this repository:

| File under `web/public/data` | Weather years | Selection years | Held out |
|---|---|---|---|
| `miami_fl.json` | 2018–2025 | 2018–2024 | 2025 |
| `denver_co.json` | 2023 | 2023 | None; single-year demonstration |

Both evaluate 361 configurations: tilt 0–90° by 5°, azimuth 90–270° by 10°.
Both use the default 1 kW DC system. These are model estimates, not measured
generation. All system assumptions and NSRDB grid-point metadata are in each file.
Miami includes multiple NSRDB source revisions; those revisions are recorded per
year. Observed spread can reflect source revisions as well as weather differences.

## Load a bundle in Vite/React

Files in `public` are served from the app's base URL. No API key or Python process
is needed to read these samples. Frontend installation/build work remains owned by
the dashboard team; this handoff does not implement the visualizations.

```js
const response = await fetch(`${import.meta.env.BASE_URL}data/miami_fl.json`);
if (!response.ok) throw new Error(`Could not load solar data: ${response.status}`);
const data = await response.json();
if (data.schema_version !== "1.0") throw new Error("Unsupported solar data schema");

const { tilt, azimuth } = data.recommendation.recommended;
const selected = data.configurations.find(
  c => c.tilt === tilt && c.azimuth === azimuth
);

// Headline estimate, in annual AC kWh for metadata.system.capacity_kw of DC panels:
const meanAnnualKwh = selected.training.mean_kwh;
const annualSeries = Object.entries(selected.per_year).map(([year, kwh]) => ({
  year: Number(year), kwh
}));
const heatmap = data.configurations.map(c => ({
  tilt: c.tilt, azimuth: c.azimuth, kwh: c.training.mean_kwh
}));
```

## Lambda slider and baseline comparisons

Changing lambda does not require another weather download or energy simulation.
Rank configurations using **training statistics only**:

```js
function selectConfiguration(data, lambda) {
  if (!Number.isFinite(lambda) || lambda < 0) throw new Error("Invalid lambda");
  const score = c => c.training.mean_kwh - lambda * c.training.std_kwh;
  return data.configurations.reduce((best, c) => score(c) > score(best) ? c : best);
}
```

The file order matches Python's tie-breaking (smaller tilt, then azimuth). After
reranking, update the annual series and held-out panel from the newly selected
configuration. Stored `score` values and `recommendation` reflect the exported
lambda, so recompute scores for the slider value. The latitude and representative-
year baseline configurations remain fixed; look up their corresponding entries in
`configurations` to display training/held-out means and recomputed scores.

Keep the labels distinct:

- `training.mean_kwh`: historical average modeled production, suitable for the
  energy headline. `training.std_kwh` is year-to-year spread, not a confidence interval.
- `training.score`: ranking objective `mean - lambda * std`, not expected energy.
- `held_out`: evaluation on later years; `null` means no held-out evaluation.
- `baselines.tmy_best`: best configuration for a representative historical year,
  a proxy rather than a true stitched TMY product.
- Azimuth: clockwise from north; 180° is south, 170° is 10° east of south.
- Tilt: degrees from horizontal.

Changing capacity, mounting, inverter parameters, or losses requires regenerating
the bundle for that system. Do not label the default 1 kW output as an entire home's
generation. Annual files support heatmaps, location comparisons, baseline comparisons,
and variability plots. They do not contain hourly power curves or a 3D sun trajectory.

## Generate or refresh results

From the repository root, after installing `requirements.txt` with Python 3.12+:

```bash
python -m pipeline.run --name "Miami, FL" --lat 25.7617 --lon -80.1918 \
  --years 2018 2019 2020 2021 2022 2023 2024 2025 \
  --train-years 2018 2019 2020 2021 2022 2023 2024
```

Use `--system-config system.json` for a JSON object such as `{"capacity_kw": 5}`.
Defaults and validation live in `pipeline/system_config.py`. `--output-dir` changes
the JSON destination; `--processed-dir` changes the generated Parquet destination.
The same location filename is replaced on reruns, so use separate output directories
when keeping multiple systems or risk-weight variants.

For already-generated energy tables, export without credentials or model execution:

```bash
python -m pipeline.run --energy-table data/processed/energy_miami_fl.parquet \
  --train-years 2018 2019 2020 2021 2022 2023 2024
```

Raw weather and Parquet files are gitignored. Include the derived JSON and this
contract in the team handoff/PR so a fresh checkout has usable examples.

## Readiness boundary

This supports a checkpoint demonstration and frontend development against a stable
schema. It is not yet a deployed, user-facing production service. Remaining work
includes geocoding/year discovery, API/job handling, retry/backoff and concurrent
cache access, full frontend integration, and comparison with measured PV output.
Site-specific shading, snow, and equipment aging are not explicitly simulated.
