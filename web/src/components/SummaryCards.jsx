import React from 'react';
import { formatKwh, formatDegrees, getAzimuthCardinalLabel, calculateScore } from '../utils/optimization';

export function SummaryCards({
  optimalConfig,
  selectedConfig,
  lambdaValue,
  isMultiYear,
  onResetToOptimal,
}) {
  if (!optimalConfig) return null;

  const isCustomSelected =
    selectedConfig &&
    (Math.abs(selectedConfig.tilt - optimalConfig.tilt) > 0.01 ||
      Math.abs(selectedConfig.azimuth - optimalConfig.azimuth) > 0.01);

  const meanAnnualKwh = optimalConfig.training?.mean_kwh;
  const stdKwh = optimalConfig.training?.std_kwh;
  const score = optimalConfig.computedScore ?? calculateScore(meanAnnualKwh, stdKwh, lambdaValue);
  const cvPercent = meanAnnualKwh && stdKwh ? ((stdKwh / meanAnnualKwh) * 100).toFixed(1) : '0.0';

  // Selected config stats (if manually clicked a different configuration)
  const selMean = selectedConfig?.training?.mean_kwh;
  const selStd = selectedConfig?.training?.std_kwh;
  const selScore = selectedConfig ? calculateScore(selMean, selStd, lambdaValue) : null;
  const deltaMean = selMean !== undefined ? selMean - meanAnnualKwh : 0;
  const deltaScore = selScore !== null ? selScore - score : 0;

  return (
    <div className="summary-section">
      <div className="summary-cards-grid">
        {/* Card 1: Recommended Orientation */}
        <div className="summary-card highlight-card">
          <div className="card-top-row">
            <span className="card-eyebrow">Optimal Orientation</span>
            <span className="card-badge badge-optimal">Recommended</span>
          </div>
          <div className="card-metric-primary">
            {formatDegrees(optimalConfig.tilt)} · {formatDegrees(optimalConfig.azimuth)}
          </div>
          <div className="card-sub-metric">
            <strong>{getAzimuthCardinalLabel(optimalConfig.azimuth)}</strong>
          </div>
        </div>

        {/* Card 2: Expected / Modeled Annual Energy */}
        <div className="summary-card">
          <div className="card-top-row">
            <span className="card-eyebrow">
              {isMultiYear ? 'Average Annual Output' : 'Modeled Output (2023)'}
            </span>
            <span className="card-badge badge-energy">
              {isMultiYear ? '7-Yr Mean' : '2023'}
            </span>
          </div>
          <div className="card-metric-primary">
            {formatKwh(meanAnnualKwh)}{' '}
            <span className="metric-unit">{isMultiYear ? 'kWh/yr' : 'kWh'}</span>
          </div>
          <div className="card-sub-metric">
            <strong>1 kW DC Array</strong> • STC Monofacial
          </div>
        </div>

        {/* Card 3: Year-to-Year Spread / Variability */}
        <div className="summary-card">
          <div className="card-top-row">
            <span className="card-eyebrow">Year-to-Year Spread</span>
            <span className={`card-badge ${isMultiYear ? 'badge-variability' : 'badge-neutral'}`}>
              {isMultiYear ? 'Volatility' : 'Single Year'}
            </span>
          </div>
          <div className="card-metric-primary">
            {isMultiYear ? (
              <>
                ±{formatKwh(stdKwh, 1)}{' '}
                <span className="metric-unit">kWh</span>
              </>
            ) : (
              <span className="metric-na">0.0 kWh</span>
            )}
          </div>
          <div className="card-sub-metric">
            <strong>{isMultiYear ? `${cvPercent}% Coeff. of Variation` : 'No Inter-Annual Spread'}</strong>
          </div>
        </div>

        {/* Card 4: Risk-Adjusted Score */}
        <div className="summary-card">
          <div className="card-top-row">
            <span className="card-eyebrow">Risk Score (λ = {Number(lambdaValue).toFixed(2)})</span>
            <span className="card-badge badge-score">Objective</span>
          </div>
          <div className="card-metric-primary">
            {formatKwh(score, 1)}
          </div>
          <div className="card-sub-metric">
            <strong>Mean − {Number(lambdaValue).toFixed(2)} × StdDev</strong>
          </div>
        </div>
      </div>

      {/* Manual Selection Banner if user clicked a cell on the heatmap */}
      {isCustomSelected && (
        <div className="manual-selection-banner">
          <div className="selection-banner-left">
            <div className="selection-title">
              Inspecting: <strong>{formatDegrees(selectedConfig.tilt)} Tilt · {formatDegrees(selectedConfig.azimuth)} Azimuth</strong> ({getAzimuthCardinalLabel(selectedConfig.azimuth)})
            </div>
            <div className="selection-metrics-row">
              <span className="sel-item">
                Output: <strong>{formatKwh(selMean)} {isMultiYear ? 'kWh/yr' : 'kWh'}</strong>{' '}
                <span className={deltaMean >= 0 ? 'delta-pos' : 'delta-neg'}>
                  (<strong>{deltaMean >= 0 ? '+' : ''}{formatKwh(deltaMean, 1)}</strong>)
                </span>
              </span>
              <span className="sel-divider">•</span>
              {isMultiYear && (
                <>
                  <span className="sel-item">
                    Spread: <strong>±{formatKwh(selStd, 1)} kWh</strong>
                  </span>
                  <span className="sel-divider">•</span>
                </>
              )}
              <span className="sel-item">
                Score: <strong>{formatKwh(selScore, 1)}</strong>{' '}
                <span className={deltaScore >= 0 ? 'delta-pos' : 'delta-neg'}>
                  (<strong>{deltaScore >= 0 ? '+' : ''}{formatKwh(deltaScore, 1)}</strong>)
                </span>
              </span>
            </div>
          </div>
          <button
            type="button"
            className="reset-to-optimal-btn"
            onClick={onResetToOptimal}
          >
            Reset to Recommended
          </button>
        </div>
      )}
    </div>
  );
}
