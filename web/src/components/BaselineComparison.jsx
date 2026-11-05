import React from 'react';
import { formatDegrees, formatKwh, getAzimuthCardinalLabel } from '../utils/optimization';

export function BaselineComparison({ baselinesData, lambdaValue, isMultiYear }) {
  if (!baselinesData) return null;

  const { optimal, latTilt, tmyProxy } = baselinesData;

  const candidates = [
    {
      key: 'optimal',
      title: 'SolarOPT',
      badge: `Optimal · λ = ${lambdaValue.toFixed(2)}`,
      badgeClass: 'badge-optimal',
      tilt: optimal?.tilt,
      azimuth: optimal?.azimuth,
      meanKwh: optimal?.meanKwh,
      stdKwh: optimal?.stdKwh,
      score: optimal?.score,
      isOptimal: true,
    },
    {
      key: 'latTilt',
      title: 'Latitude-Tilt Rule',
      badge: 'Heuristic',
      badgeClass: 'badge-lat',
      tilt: latTilt?.tilt,
      azimuth: latTilt?.azimuth,
      meanKwh: latTilt?.meanKwh,
      stdKwh: latTilt?.stdKwh,
      score: latTilt?.score,
      isOptimal: false,
    },
    {
      key: 'tmyProxy',
      title: 'Representative Year',
      badge: isMultiYear ? `${tmyProxy?.representativeYear} Proxy` : '2023 Single Year',
      badgeClass: 'badge-tmy',
      tilt: tmyProxy?.tilt,
      azimuth: tmyProxy?.azimuth,
      meanKwh: tmyProxy?.meanKwh,
      stdKwh: tmyProxy?.stdKwh,
      score: tmyProxy?.score,
      isOptimal: false,
    },
  ];

  const optimalMean = optimal?.meanKwh || 1;
  const optimalScore = optimal?.score || 1;

  return (
    <div className="dashboard-card baseline-comparison-card">
      <div className="card-header-compact baseline-card-header">
        <div>
          <h3 className="card-title-main">Baseline Comparison</h3>
          <p className="card-subtitle-main">
            Optimizer recommendation vs standard heuristics.
          </p>
        </div>
        <div className="baseline-header-chip">
          <span className="chip-dot"></span>
          <span>Risk Parameter: <strong>λ = {lambdaValue.toFixed(2)}</strong></span>
        </div>
      </div>

      <div className="comparison-table-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th className="col-strategy">Strategy</th>
              <th className="col-orientation">Orientation</th>
              <th className="col-output">{isMultiYear ? 'Average Output' : '2023 Output'}</th>
              {isMultiYear && <th className="col-spread">Spread (Std)</th>}
              <th className="col-score">Risk Score</th>
              <th className="col-advantage">Advantage vs Optimal</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => {
              if (c.tilt === undefined) return null;
              const deltaKwh = c.meanKwh - optimalMean;
              const deltaScore = c.score - optimalScore;
              const percentDiff = ((deltaKwh / optimalMean) * 100).toFixed(2);

              return (
                <tr key={c.key} className={c.isOptimal ? 'row-optimal' : ''}>
                  <td>
                    <div className="strategy-name-cell">
                      <div className="strategy-title-row">
                        {c.isOptimal && <span className="optimal-star-icon">★</span>}
                        <strong className="strategy-title">{c.title}</strong>
                      </div>
                      <span className={`strategy-badge ${c.badgeClass}`}>{c.badge}</span>
                    </div>
                  </td>
                  <td>
                    <div className="orientation-cell">
                      <strong>{formatDegrees(c.tilt)} · {formatDegrees(c.azimuth)}</strong>
                      <span className="cardinal-sub">{getAzimuthCardinalLabel(c.azimuth)}</span>
                    </div>
                  </td>
                  <td>
                    <div className="metric-cell-val">
                      <strong>{formatKwh(c.meanKwh)}</strong> <span className="unit-sub">{isMultiYear ? 'kWh/yr' : 'kWh'}</span>
                    </div>
                  </td>
                  {isMultiYear && (
                    <td>
                      <div className="metric-cell-val">
                        <strong>±{formatKwh(c.stdKwh, 1)}</strong> <span className="unit-sub">kWh</span>
                      </div>
                    </td>
                  )}
                  <td>
                    <div className="metric-cell-val score-val">
                      <strong>{formatKwh(c.score, 1)}</strong>
                    </div>
                  </td>
                  <td>
                    {c.isOptimal ? (
                      <span className="delta-ref-dash">—</span>
                    ) : (
                      <div className="delta-cell">
                        <span className={deltaKwh >= 0 ? 'delta-pill-pos' : 'delta-pill-neg'}>
                          <strong>{deltaKwh >= 0 ? '+' : ''}{formatKwh(deltaKwh, 1)}</strong> kWh ({percentDiff}%)
                        </span>
                        <span className="score-delta-sub">
                          Δ Score: <strong>{deltaScore >= 0 ? '+' : ''}{formatKwh(deltaScore, 1)}</strong>
                        </span>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="baseline-clarification-footer">
        {isMultiYear ? (
          <>
            <strong>Representative Year ({tmyProxy?.representativeYear}):</strong> Training year whose average modeled generation across all 361 configurations is closest to multi-year mean (TMY proxy).
          </>
        ) : (
          <>
            <strong>Denver (2023):</strong> Representative-year baseline is identical to the single available year; provides no independent multi-year comparison.
          </>
        )}
      </p>
    </div>
  );
}
