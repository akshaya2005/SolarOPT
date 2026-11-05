import React, { useState } from 'react';

export function ConfigurationDetail({ metadata, schemaVersion }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!metadata) return null;

  const { system, weather_sources, requested_location, models, pvlib_version } = metadata;
  const weatherYears = weather_sources ? Object.keys(weather_sources) : [];

  const formatCoord = (lat, lon) => {
    if (lat === undefined || lon === undefined) return '—';
    const latStr = lat >= 0 ? `${lat}° N` : `${Math.abs(lat)}° S`;
    const lonStr = lon >= 0 ? `${lon}° E` : `${Math.abs(lon)}° W`;
    return `${latStr}, ${lonStr}`;
  };

  const firstSource = weatherYears.length > 0 ? weather_sources[weatherYears[0]] : null;

  return (
    <div className="dashboard-card metadata-collapsible-card">
      <button
        type="button"
        className="metadata-toggle-btn"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <div className="toggle-left">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 16v-4"></path>
            <path d="M12 8h.01"></path>
          </svg>
          <span className="toggle-title">System Configuration & Data Provenance (Schema v{schemaVersion})</span>
        </div>
        <div className="toggle-right">
          <span className="toggle-status">{isOpen ? 'Hide Specs' : 'View Specs & Models'}</span>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
          >
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </div>
      </button>

      {isOpen && (
        <div className="metadata-content-grid">
          {/* PV System Specification */}
          <div className="meta-sub-card">
            <h4 className="meta-sub-title">Reference Photovoltaic System</h4>
            <div className="meta-kv-list">
              <div className="meta-kv">
                <span className="meta-k">DC Array Capacity:</span>
                <span className="meta-v">{system?.capacity_kw} kW DC STC</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">DC / AC Sizing Ratio:</span>
                <span className="meta-v">{system?.dc_ac_ratio}</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Inverter Efficiency:</span>
                <span className="meta-v">{(system?.inverter_efficiency * 100).toFixed(1)}%</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Aggregate DC Losses:</span>
                <span className="meta-v">{system?.losses_percent}%</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Temp Coefficient (γ):</span>
                <span className="meta-v">{(system?.gamma_pdc * 100).toFixed(2)}% / °C</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Thermal Mount Model:</span>
                <span className="meta-v">{system?.temperature_model}</span>
              </div>
            </div>
          </div>

          {/* Model Chain Specification */}
          <div className="meta-sub-card">
            <h4 className="meta-sub-title">Simulation Pipeline (pvlib {pvlib_version})</h4>
            <div className="meta-kv-list">
              <div className="meta-kv">
                <span className="meta-k">Transposition Model:</span>
                <span className="meta-v">{models?.transposition}</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Cell Temperature:</span>
                <span className="meta-v">{models?.temperature} (SAPM)</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">DC Yield Model:</span>
                <span className="meta-v">{models?.dc} (PVWatts)</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Inverter Clipping:</span>
                <span className="meta-v">{models?.inverter} (PVWatts)</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">AOI Reflection Model:</span>
                <span className="meta-v">{models?.aoi}</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Spectral Mismatch:</span>
                <span className="meta-v">{models?.spectral}</span>
              </div>
            </div>
          </div>

          {/* NSRDB Weather Grid Point */}
          <div className="meta-sub-card">
            <h4 className="meta-sub-title">NREL NSRDB Weather Grid Provenance</h4>
            <div className="meta-kv-list">
              <div className="meta-kv">
                <span className="meta-k">Target Coordinates:</span>
                <span className="meta-v">{formatCoord(requested_location?.lat, requested_location?.lon)}</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Modeled Grid Point:</span>
                <span className="meta-v">{formatCoord(firstSource?.latitude, firstSource?.longitude)}</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Weather Archive Span:</span>
                <span className="meta-v">{weatherYears.length} Years ({weatherYears.join(', ')})</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">NSRDB Grid Elevation:</span>
                <span className="meta-v">{firstSource?.elevation ?? '—'} m</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">NSRDB Location ID:</span>
                <span className="meta-v">{firstSource?.location_id ?? '—'}</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Temporal Resolution:</span>
                <span className="meta-v">60-minute hourly UTC PSM v4</span>
              </div>
              <div className="meta-kv">
                <span className="meta-k">Energy Output Metric:</span>
                <span className="meta-v">AC kWh after clipping and inverter losses</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

