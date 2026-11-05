/**
 * SolarOPT Optimization & Mathematical Utilities
 *
 * Implements risk-adjusted solar configuration scoring:
 * Score = Mean Annual Energy (training) - λ * Standard Deviation (training)
 *
 * Adheres strictly to docs/data_contract.md and docs/frontend_handoff.md:
 * - Only training statistics are used for configuration ranking.
 * - Held-out test years are strictly reserved for out-of-sample evaluation.
 * - Tie-breaking preserves smaller tilt, then smaller azimuth.
 */

/**
 * Calculate the risk-adjusted objective score for a solar configuration.
 *
 * @param {number} meanKwh - Mean annual AC energy in kWh (training years)
 * @param {number} stdKwh - Population standard deviation in kWh (training years)
 * @param {number} lambda - Risk-aversion penalty weight (>= 0)
 * @returns {number} The objective score
 */
export function calculateScore(meanKwh, stdKwh, lambda) {
  if (!Number.isFinite(lambda) || lambda < 0) {
    throw new Error('lambda must be a finite nonnegative number');
  }
  const std = Number.isFinite(stdKwh) ? stdKwh : 0;
  return meanKwh - lambda * std;
}

/**
 * Select the optimal configuration across all 361 candidates for a given lambda.
 * Preserves smaller tilt, then smaller azimuth for ties, matching the Python pipeline.
 *
 * @param {Array<Object>} configurations - Array of configuration objects
 * @param {number} lambda - Risk aversion parameter
 * @returns {Object} The optimal configuration with its computed score
 */
export function selectOptimalConfiguration(configurations, lambda) {
  if (!Array.isArray(configurations) || configurations.length === 0) {
    return null;
  }
  if (!Number.isFinite(lambda) || lambda < 0) {
    throw new Error('lambda must be a finite nonnegative number');
  }

  let best = configurations[0];
  let bestScore = calculateScore(best.training.mean_kwh, best.training.std_kwh, lambda);

  for (let i = 1; i < configurations.length; i++) {
    const config = configurations[i];
    const score = calculateScore(config.training.mean_kwh, config.training.std_kwh, lambda);

    // Strict inequality keeps the earlier configuration on ties,
    // which corresponds to smaller tilt, then smaller azimuth.
    if (score > bestScore) {
      best = config;
      bestScore = score;
    }
  }

  return {
    ...best,
    computedScore: bestScore,
  };
}

/**
 * Find a specific configuration by tilt and azimuth.
 *
 * @param {Array<Object>} configurations
 * @param {number} tilt
 * @param {number} azimuth
 * @returns {Object|null}
 */
export function findConfiguration(configurations, tilt, azimuth) {
  if (!Array.isArray(configurations)) return null;
  return configurations.find(
    (c) => Math.abs(c.tilt - tilt) < 0.01 && Math.abs(c.azimuth - azimuth) < 0.01
  ) || null;
}

/**
 * Recalculate baseline configuration statistics for the active lambda.
 *
 * @param {Object} solarData - Loaded JSON data bundle
 * @param {number} lambda - Current risk parameter
 * @returns {Object} Recalculated baselines
 */
export function recalculateBaselines(solarData, lambda) {
  if (!solarData || !solarData.recommendation || !solarData.recommendation.baselines) {
    return null;
  }

  const { baselines, recommended } = solarData.recommendation;
  const configs = solarData.configurations;

  // 1. Current optimizer recommendation at current lambda
  const currentOptimal = selectOptimalConfiguration(configs, lambda);

  // 2. Latitude tilt baseline: (snapped lat, 180° due south)
  let latTiltBaseline = null;
  if (baselines.lat_tilt) {
    const config = findConfiguration(configs, baselines.lat_tilt.tilt, baselines.lat_tilt.azimuth);
    if (config) {
      const score = calculateScore(config.training.mean_kwh, config.training.std_kwh, lambda);
      latTiltBaseline = {
        name: 'Latitude-Tilt Rule',
        description: 'Industry rule-of-thumb: tilt equals site latitude, panel faces due South (180°).',
        tilt: config.tilt,
        azimuth: config.azimuth,
        meanKwh: config.training.mean_kwh,
        stdKwh: config.training.std_kwh,
        score,
        heldOutMeanKwh: config.held_out ? config.held_out.mean_kwh : null,
        perYear: config.per_year,
      };
    }
  }

  // 3. Representative year baseline (proxy for TMY)
  let tmyBaseline = null;
  if (baselines.tmy_best) {
    const config = findConfiguration(configs, baselines.tmy_best.tilt, baselines.tmy_best.azimuth);
    if (config) {
      const score = calculateScore(config.training.mean_kwh, config.training.std_kwh, lambda);
      tmyBaseline = {
        name: 'Representative-Year Proxy',
        description: `Best single orientation for ${baselines.tmy_best.representative_year} (the training year whose average modeled generation across all configurations is nearest the training mean).`,
        representativeYear: baselines.tmy_best.representative_year,
        tilt: config.tilt,
        azimuth: config.azimuth,
        meanKwh: config.training.mean_kwh,
        stdKwh: config.training.std_kwh,
        score,
        heldOutMeanKwh: config.held_out ? config.held_out.mean_kwh : null,
        perYear: config.per_year,
      };
    }
  }

  return {
    optimal: {
      name: 'SolarOPT Optimal',
      description: `Risk-adjusted optimum (λ = ${lambda.toFixed(2)}) balancing production and multi-year consistency.`,
      tilt: currentOptimal.tilt,
      azimuth: currentOptimal.azimuth,
      meanKwh: currentOptimal.training.mean_kwh,
      stdKwh: currentOptimal.training.std_kwh,
      score: currentOptimal.computedScore,
      heldOutMeanKwh: currentOptimal.held_out ? currentOptimal.held_out.mean_kwh : null,
      perYear: currentOptimal.per_year,
    },
    defaultExportOptimal: recommended,
    latTilt: latTiltBaseline,
    tmyProxy: tmyBaseline,
  };
}

/**
 * Format kilowatt-hours with standard thousand separators.
 *
 * @param {number|null|undefined} val
 * @param {number} decimals
 * @returns {string}
 */
export function formatKwh(val, decimals = 1) {
  if (val === null || val === undefined || !Number.isFinite(val)) {
    return '—';
  }
  return val.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format angles in degrees.
 *
 * @param {number|null|undefined} deg
 * @returns {string}
 */
export function formatDegrees(deg) {
  if (deg === null || deg === undefined || !Number.isFinite(deg)) {
    return '—';
  }
  return `${Math.round(deg)}°`;
}

/**
 * Return cardinal direction label for azimuth.
 * Azimuth in pvlib: 0 = North, 90 = East, 180 = South, 270 = West.
 *
 * @param {number} azimuth
 * @returns {string}
 */
export function getAzimuthCardinalLabel(azimuth) {
  if (!Number.isFinite(azimuth)) return '';
  const rounded = Math.round(azimuth);
  if (rounded === 180) return 'Due South (180°)';
  if (rounded === 90) return 'East (90°)';
  if (rounded === 270) return 'West (270°)';
  if (rounded < 180) {
    return `${180 - rounded}° East of South (${rounded}°)`;
  }
  return `${rounded - 180}° West of South (${rounded}°)`;
}

