import React from 'react';
import Plotly from 'plotly.js-dist-min';
import _createPlotlyComponent from 'react-plotly.js/factory';

// Handle CJS/ESM interop differences across Vite development and production bundles
const createPlotlyComponent =
  typeof _createPlotlyComponent === 'function'
    ? _createPlotlyComponent
    : typeof _createPlotlyComponent?.default === 'function'
    ? _createPlotlyComponent.default
    : _createPlotlyComponent?.default?.default;

const PlotlyLib =
  Plotly && typeof Plotly.newPlot === 'function'
    ? Plotly
    : Plotly?.default && typeof Plotly.default.newPlot === 'function'
    ? Plotly.default
    : Plotly;

let PlotComponent = null;
try {
  if (typeof createPlotlyComponent === 'function' && PlotlyLib) {
    PlotComponent = createPlotlyComponent(PlotlyLib);
  }
} catch (e) {
  console.error('Failed to initialize Plotly component:', e);
}

export function Plot(props) {
  if (!PlotComponent) {
    return (
      <div style={{ padding: '20px', color: '#b91c1c', background: '#fef2f2', borderRadius: '8px' }}>
        Plot visualization is initializing or encountered an error.
      </div>
    );
  }
  return <PlotComponent {...props} />;
}

export default Plot;

