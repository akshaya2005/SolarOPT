import React from 'react';
import { Plot } from './Plot';
import { formatDegrees, formatKwh, getAzimuthCardinalLabel } from '../utils/optimization';

export function YearlyEnergyChart({
  selectedConfig,
  trainYears,
  heldOutYears,
  isMultiYear,
}) {
  if (!selectedConfig || !selectedConfig.per_year) {
    return (
      <div className="dashboard-card yearly-chart-card empty-card">
        <p>No annual energy data available for configuration.</p>
      </div>
    );
  }

  const perYearEntries = Object.entries(selectedConfig.per_year)
    .map(([yr, kwh]) => ({
      year: parseInt(yr, 10),
      kwh,
      isHeldOut: heldOutYears ? heldOutYears.includes(parseInt(yr, 10)) : false,
    }))
    .sort((a, b) => a.year - b.year);

  const trainingMeanKwh = selectedConfig.training?.mean_kwh ?? 0;

  // Separate training and held-out bars for clean legends and visual distinction
  const trainData = perYearEntries.filter((d) => !d.isHeldOut);
  const heldOutData = perYearEntries.filter((d) => d.isHeldOut);

  const traces = [];

  // Training years trace
  if (trainData.length > 0) {
    traces.push({
      type: 'bar',
      name: 'Training Weather Years',
      x: trainData.map((d) => d.year.toString()),
      y: trainData.map((d) => d.kwh),
      marker: {
        color: '#f59e0b',
        line: { color: '#d97706', width: 1.5 },
      },
      customdata: trainData.map((d) => [
        d.kwh - trainingMeanKwh,
        ((d.kwh - trainingMeanKwh) / trainingMeanKwh) * 100,
      ]),
      hovertemplate:
        '<b>%{x} (Training Year)</b><br>' +
        '• Modeled AC Energy: <b>%{y:.1f} kWh</b><br>' +
        '• Delta from Training Mean: <b>%{customdata[0]:+.1f} kWh (%{customdata[1]:+.1f}%)</b><extra></extra>',
    });
  }

  // Held-out test years trace
  if (heldOutData.length > 0) {
    traces.push({
      type: 'bar',
      name: 'Held-Out Test Year (Evaluation)',
      x: heldOutData.map((d) => d.year.toString()),
      y: heldOutData.map((d) => d.kwh),
      marker: {
        color: '#0284c7',
        line: { color: '#0369a1', width: 2 },
        pattern: { shape: '/', fillmode: 'overlay', size: 6, solidity: 0.3 },
      },
      customdata: heldOutData.map((d) => [
        d.kwh - trainingMeanKwh,
        ((d.kwh - trainingMeanKwh) / trainingMeanKwh) * 100,
      ]),
      hovertemplate:
        '<b>%{x} (HELD-OUT EVALUATION)</b><br>' +
        '• Modeled AC Energy: <b>%{y:.1f} kWh</b><br>' +
        '• Delta from Training Mean: <b>%{customdata[0]:+.1f} kWh (%{customdata[1]:+.1f}%)</b><extra></extra>',
    });
  }

  // Horizontal dashed line for training mean
  const allYears = perYearEntries.map((d) => d.year.toString());
  const shapes = [];
  const annotations = [];

  if (trainData.length > 1) {
    shapes.push({
      type: 'line',
      x0: -0.5,
      x1: allYears.length - 0.5,
      y0: trainingMeanKwh,
      y1: trainingMeanKwh,
      line: {
        color: '#dc2626',
        width: 2,
        dash: 'dash',
      },
    });

    annotations.push({
      x: allYears.length - 0.5,
      y: trainingMeanKwh,
      xref: 'x',
      yref: 'y',
      text: `Mean: ${formatKwh(trainingMeanKwh, 0)} kWh`,
      showarrow: false,
      xanchor: 'right',
      yanchor: 'bottom',
      yshift: 4,
      font: { size: 10, color: '#dc2626', family: 'system-ui, sans-serif' },
      bgcolor: 'rgba(255, 255, 255, 0.85)',
      bordercolor: '#fca5a5',
      borderwidth: 1,
    });
  }

  const yMax = Math.max(...perYearEntries.map((d) => d.kwh), 100);
  const yUpper = Math.ceil((yMax * 1.15) / 100) * 100;

  const layout = {
    autosize: true,
    showlegend: false,
    margin: { t: 15, r: 16, b: 40, l: 55 },
    xaxis: {
      title: { text: 'Weather Observation Year', font: { size: 11, color: '#334155' } },
      type: 'category',
      tickfont: { size: 11, color: '#475569' },
      gridcolor: '#f1f5f9',
    },
    yaxis: {
      title: { text: 'Annual AC Energy (kWh)', font: { size: 11, color: '#334155' } },
      range: [0, yUpper],
      rangemode: 'tozero',
      tickfont: { size: 11, color: '#475569' },
      gridcolor: '#e2e8f0',
    },
    shapes,
    annotations,
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
  };

  const config = {
    responsive: true,
    displayModeBar: false,
  };

  return (
    <div className="dashboard-card yearly-chart-card">
      <div className="card-header-compact">
        <div>
          <h3 className="card-title-main">Historical Annual Energy Series</h3>
          <p className="card-subtitle-main">
            Simulated AC kWh for {formatDegrees(selectedConfig.tilt)} tilt / {formatDegrees(selectedConfig.azimuth)} azimuth ({getAzimuthCardinalLabel(selectedConfig.azimuth)}).
          </p>
        </div>
      </div>

      {!isMultiYear ? (
        <div className="denver-single-year-banner">
          <span>ℹ️ <strong>Denver (2023):</strong> Single observation year • Multi-year spread cannot be established</span>
        </div>
      ) : (
        <div className="held-out-info-badge-row">
          <span className="badge-legend-item">
            <span className="legend-box train-box"></span> <strong>{trainYears && trainYears.length > 0 ? `${trainYears[0]}–${trainYears[trainYears.length - 1]}` : 'Training'}</strong>: Training ({trainYears?.length || 0} yrs)
          </span>
          <span className="badge-legend-item">
            <span className="legend-box test-box"></span> <strong>{heldOutYears && heldOutYears.length > 0 ? heldOutYears.join(', ') : 'None'}</strong>: Held-Out Test ({heldOutYears?.length || 0} yr)
          </span>
        </div>
      )}

      <div className="plot-container-wrap" style={{ height: '300px' }}>
        <Plot
          data={traces}
          layout={layout}
          config={config}
          useResizeHandler={true}
          style={{ width: '100%', height: '100%' }}
        />
      </div>
    </div>
  );
}
