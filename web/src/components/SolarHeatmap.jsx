import React, { useMemo } from 'react';
import { Plot } from './Plot';
import {
  calculateScore,
  getAzimuthCardinalLabel,
  formatDegrees,
} from '../utils/optimization';

export function SolarHeatmap({
  configurations,
  optimalConfig,
  selectedConfig,
  lambdaValue,
  isMultiYear,
  onSelectConfig,
}) {
  // Extract tilts and azimuths and construct the 19x19 matrix
  const { tilts, azimuths, zMatrix, customdataMatrix } = useMemo(() => {
    if (!Array.isArray(configurations) || configurations.length === 0) {
      return { tilts: [], azimuths: [], zMatrix: [], customdataMatrix: [] };
    }

    // Unique sorted tilts and azimuths
    const uniqueTilts = Array.from(new Set(configurations.map((c) => c.tilt))).sort((a, b) => a - b);
    const uniqueAzimuths = Array.from(new Set(configurations.map((c) => c.azimuth))).sort((a, b) => a - b);

    // Build lookup map for fast grid construction
    const configMap = new Map();
    for (const c of configurations) {
      configMap.set(`${c.tilt}_${c.azimuth}`, c);
    }

    const z = [];
    const customdata = [];

    for (const tilt of uniqueTilts) {
      const zRow = [];
      const customRow = [];
      for (const az of uniqueAzimuths) {
        const item = configMap.get(`${tilt}_${az}`);
        if (item) {
          const mean = item.training.mean_kwh;
          const std = item.training.std_kwh;
          const score = calculateScore(mean, std, lambdaValue);
          const cardinal = getAzimuthCardinalLabel(az);

          zRow.push(mean);
          customRow.push([std, score, cardinal, lambdaValue, tilt, az]);
        } else {
          zRow.push(null);
          customRow.push([0, 0, '', lambdaValue, tilt, az]);
        }
      }
      z.push(zRow);
      customdata.push(customRow);
    }

    return {
      tilts: uniqueTilts,
      azimuths: uniqueAzimuths,
      zMatrix: z,
      customdataMatrix: customdata,
    };
  }, [configurations, lambdaValue]);

  if (tilts.length === 0 || azimuths.length === 0) {
    return <div className="heatmap-empty-state">No configuration data available.</div>;
  }

  // Heatmap trace
  const heatmapTrace = {
    type: 'heatmap',
    x: azimuths,
    y: tilts,
    z: zMatrix,
    customdata: customdataMatrix,
    colorscale: [
      [0.0, '#1e293b'],
      [0.15, '#1e3a8a'],
      [0.35, '#0284c7'],
      [0.55, '#f59e0b'],
      [0.75, '#ea580c'],
      [0.9, '#dc2626'],
      [1.0, '#fbbf24'],
    ],
    colorbar: {
      title: {
        text: 'Annual AC Energy<br>(kWh / kW DC)',
        side: 'right',
        font: { size: 12, color: '#334155', family: 'system-ui, sans-serif' },
      },
      ticksuffix: ' kWh',
      thickness: 16,
      len: 0.9,
      outlinewidth: 0,
      tickfont: { size: 11, color: '#475569' },
    },
    hovertemplate:
      '<b>%{y}° Tilt, %{x}° Azimuth</b><br>' +
      'Orientation: %{customdata[2]}<br>' +
      '• Mean Energy: <b>%{z:.1f} kWh/yr</b><br>' +
      `• Multi-Year Std Dev: <b>%{customdata[0]:.1f} kWh</b>${isMultiYear ? '' : ' (Single Year)'}<br>` +
      '• Risk Score (λ=%{customdata[3]:.2f}): <b>%{customdata[1]:.1f}</b>' +
      '<extra></extra>',
  };

  const traces = [heatmapTrace];

  // Overlay marker for the Recommended configuration
  if (optimalConfig) {
    traces.push({
      type: 'scatter',
      mode: 'markers+text',
      x: [optimalConfig.azimuth],
      y: [optimalConfig.tilt],
      name: 'Optimal (Recommended)',
      marker: {
        symbol: 'star',
        size: 20,
        color: '#fbbf24',
        line: { color: '#0f172a', width: 2 },
      },
      text: ['★ OPTIMAL'],
      textposition: 'top center',
      textfont: { size: 11, color: '#0f172a', family: 'system-ui, sans-serif' },
      hoverinfo: 'none',
      showlegend: false,
    });
  }

  // Overlay marker for Manual Selection (if different from optimal)
  const isDifferentFromOptimal =
    selectedConfig &&
    optimalConfig &&
    (Math.abs(selectedConfig.tilt - optimalConfig.tilt) > 0.01 ||
      Math.abs(selectedConfig.azimuth - optimalConfig.azimuth) > 0.01);

  if (isDifferentFromOptimal) {
    traces.push({
      type: 'scatter',
      mode: 'markers+text',
      x: [selectedConfig.azimuth],
      y: [selectedConfig.tilt],
      name: 'Active Selection',
      marker: {
        symbol: 'circle-open',
        size: 22,
        line: { color: '#38bdf8', width: 3.5 },
      },
      text: ['Active Selection'],
      textposition: 'bottom center',
      textfont: { size: 11, color: '#0369a1', family: 'system-ui, sans-serif' },
      hoverinfo: 'none',
      showlegend: false,
    });
  }

  const layout = {
    autosize: true,
    margin: { t: 36, r: 20, b: 65, l: 65 },
    xaxis: {
      title: {
        text: 'Panel Azimuth (Clockwise from North; 90° = East, 180° = South, 270° = West)',
        font: { size: 12, color: '#334155' },
      },
      tickmode: 'array',
      tickvals: azimuths,
      ticktext: azimuths.map((az) => (az === 180 ? '180° (S)' : az === 90 ? '90° (E)' : az === 270 ? '270° (W)' : `${az}°`)),
      tickfont: { size: 10, color: '#475569' },
      showgrid: true,
      gridcolor: '#e2e8f0',
      gridwidth: 0.5,
    },
    yaxis: {
      title: {
        text: 'Panel Tilt Angle (degrees from horizontal)',
        font: { size: 12, color: '#334155' },
      },
      tickmode: 'array',
      tickvals: tilts,
      ticktext: tilts.map((t) => (t === 0 ? '0° (Flat)' : t === 90 ? '90° (Vert)' : `${t}°`)),
      tickfont: { size: 10, color: '#475569' },
      showgrid: true,
      gridcolor: '#e2e8f0',
      gridwidth: 0.5,
    },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
  };

  const config = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  };

  const handlePlotClick = (event) => {
    if (event.points && event.points.length > 0) {
      const pt = event.points[0];
      // pt.x is azimuth, pt.y is tilt
      const clickedAzimuth = Number(pt.x);
      const clickedTilt = Number(pt.y);
      if (Number.isFinite(clickedAzimuth) && Number.isFinite(clickedTilt)) {
        onSelectConfig({ tilt: clickedTilt, azimuth: clickedAzimuth });
      }
    }
  };

  return (
    <div className="dashboard-card heatmap-card">
      <div className="card-header-with-actions">
        <div>
          <h3 className="card-title-main">Optimization Energy Surface Heatmap</h3>
          <p className="card-subtitle-main">
            Color encodes mean annual generation (AC kWh). Click any cell to inspect its multi-year breakdown.
          </p>
        </div>
        <div className="heatmap-legend-pills">
          <span className="legend-pill pill-opt">
            <span className="star-icon">★</span> Recommended ({formatDegrees(optimalConfig?.tilt)}, {formatDegrees(optimalConfig?.azimuth)})
          </span>
          {isDifferentFromOptimal && (
            <span className="legend-pill pill-custom">
              <span className="ring-icon">○</span> Active Selection ({formatDegrees(selectedConfig?.tilt)}, {formatDegrees(selectedConfig?.azimuth)})
            </span>
          )}
        </div>
      </div>

      <div className="plot-container-wrap">
        <Plot
          data={traces}
          layout={layout}
          config={config}
          onClick={handlePlotClick}
          useResizeHandler={true}
          style={{ width: '100%', height: '460px' }}
        />
      </div>
    </div>
  );
}
