import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  calculateScore,
  selectOptimalConfiguration,
  findConfiguration,
  recalculateBaselines,
  formatKwh,
  formatDegrees,
  getAzimuthCardinalLabel,
} from './optimization.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const miamiPath = path.resolve(__dirname, '../../public/data/miami_fl.json');
const denverPath = path.resolve(__dirname, '../../public/data/denver_co.json');

const miamiData = JSON.parse(fs.readFileSync(miamiPath, 'utf-8'));
const denverData = JSON.parse(fs.readFileSync(denverPath, 'utf-8'));

test('calculateScore computes mean - lambda * std correctly', () => {
  assert.equal(calculateScore(1000, 50, 0), 1000);
  assert.equal(calculateScore(1000, 50, 0.5), 975);
  assert.equal(calculateScore(1000, 50, 1.0), 950);
  assert.equal(calculateScore(1000, 50, 2.0), 900);
  assert.throws(() => calculateScore(1000, 50, -0.1), /lambda must be a finite nonnegative number/);
  assert.throws(() => calculateScore(1000, 50, NaN), /lambda must be a finite nonnegative number/);
});

test('Miami dataset has 361 configurations and matches exported baseline at lambda = 0.5', () => {
  assert.equal(miamiData.configurations.length, 361);
  const optimal = selectOptimalConfiguration(miamiData.configurations, 0.5);

  assert.equal(optimal.tilt, miamiData.recommendation.recommended.tilt);
  assert.equal(optimal.azimuth, miamiData.recommendation.recommended.azimuth);
  assert.ok(Math.abs(optimal.computedScore - miamiData.recommendation.score) < 1e-6);
  assert.equal(optimal.tilt, 25.0);
  assert.equal(optimal.azimuth, 170.0);
});

test('Denver dataset has 361 configurations and matches exported baseline at lambda = 0.5', () => {
  assert.equal(denverData.configurations.length, 361);
  const optimal = selectOptimalConfiguration(denverData.configurations, 0.5);

  assert.equal(optimal.tilt, denverData.recommendation.recommended.tilt);
  assert.equal(optimal.azimuth, denverData.recommendation.recommended.azimuth);
  assert.ok(Math.abs(optimal.computedScore - denverData.recommendation.score) < 1e-6);
  assert.equal(optimal.tilt, 35.0);
  assert.equal(optimal.azimuth, 180.0);
});

test('Optimization tie-breaking selects smaller tilt, then smaller azimuth', () => {
  const configs = [
    { tilt: 30, azimuth: 180, training: { mean_kwh: 1000, std_kwh: 10 } },
    { tilt: 25, azimuth: 180, training: { mean_kwh: 1000, std_kwh: 10 } }, // Smaller tilt
    { tilt: 25, azimuth: 190, training: { mean_kwh: 1000, std_kwh: 10 } },
  ];
  // Sort them by tilt, then azimuth as in the data pipeline
  configs.sort((a, b) => a.tilt - b.tilt || a.azimuth - b.azimuth);

  const best = selectOptimalConfiguration(configs, 0.5);
  assert.equal(best.tilt, 25);
  assert.equal(best.azimuth, 180);
});

test('Held-out evaluation statistics are never modified or used for optimization', () => {
  // Pass configuration array where held_out has high values, training has lower
  const configs = [
    { tilt: 10, azimuth: 180, training: { mean_kwh: 1000, std_kwh: 10 }, held_out: { mean_kwh: 2000, std_kwh: 0 } },
    { tilt: 20, azimuth: 180, training: { mean_kwh: 1200, std_kwh: 10 }, held_out: { mean_kwh: 500, std_kwh: 0 } },
  ];

  const best = selectOptimalConfiguration(configs, 0.0);
  // Must pick tilt 20 because training mean is 1200 > 1000, even though held_out for tilt 10 is 2000!
  assert.equal(best.tilt, 20);
});

test('findConfiguration correctly locates configurations', () => {
  const found = findConfiguration(miamiData.configurations, 25.0, 170.0);
  assert.ok(found);
  assert.equal(found.tilt, 25.0);
  assert.equal(found.azimuth, 170.0);

  const missing = findConfiguration(miamiData.configurations, 99.0, 99.0);
  assert.equal(missing, null);
});

test('recalculateBaselines computes scores for both baselines and optimal', () => {
  const baselines = recalculateBaselines(miamiData, 0.5);
  assert.ok(baselines.optimal);
  assert.ok(baselines.latTilt);
  assert.ok(baselines.tmyProxy);

  assert.equal(baselines.optimal.tilt, 25.0);
  assert.equal(baselines.optimal.azimuth, 170.0);
  assert.equal(baselines.latTilt.tilt, 25.0);
  assert.equal(baselines.latTilt.azimuth, 180.0);
  assert.equal(baselines.tmyProxy.representativeYear, 2018);
  assert.ok(Math.abs(baselines.latTilt.score - miamiData.recommendation.baselines.lat_tilt.score) < 1e-6);
});

test('Formatting helpers produce expected strings', () => {
  assert.equal(formatKwh(1514.444), '1,514.4');
  assert.equal(formatKwh(null), '—');
  assert.equal(formatDegrees(25.0), '25°');
  assert.equal(formatDegrees(null), '—');

  assert.equal(getAzimuthCardinalLabel(180), 'Due South (180°)');
  assert.equal(getAzimuthCardinalLabel(90), 'East (90°)');
  assert.equal(getAzimuthCardinalLabel(270), 'West (270°)');
  assert.equal(getAzimuthCardinalLabel(170), '10° East of South (170°)');
  assert.equal(getAzimuthCardinalLabel(190), '10° West of South (190°)');
});
