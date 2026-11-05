import React from 'react';
import { LOCATIONS } from '../data/locations';

export function LocationSelector({ selectedLocationId, onSelectLocation }) {
  const activeLocation = LOCATIONS.find((loc) => loc.id === selectedLocationId) || LOCATIONS[0];

  return (
    <div className="sidebar-card location-selector-card">
      <div className="card-header-compact">
        <div className="card-title-group">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"></path>
            <circle cx="12" cy="10" r="3"></circle>
          </svg>
          <label htmlFor="location-select" className="card-title-compact">Location</label>
        </div>
        <span className="location-count-badge">{LOCATIONS.length} sites</span>
      </div>

      <div className="select-wrapper">
        <select
          id="location-select"
          className="custom-select"
          value={selectedLocationId}
          onChange={(e) => onSelectLocation(e.target.value)}
        >
          {LOCATIONS.map((loc) => (
            <option key={loc.id} value={loc.id}>
              {loc.name}
            </option>
          ))}
        </select>
        <div className="select-arrow">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </div>
      </div>

      <div className="location-info-callout">
        <div className="info-row">
          <span className="info-key">Climate:</span>
          <span className="info-val"><strong>{activeLocation.climate}</strong></span>
        </div>
        <div className="info-row">
          <span className="info-key">Grid Elevation:</span>
          <span className="info-val"><strong>{activeLocation.elevation}</strong></span>
        </div>
        <div className="info-row">
          <span className="info-key">Data Span:</span>
          <span className="info-val">
            <strong>{activeLocation.years}</strong>{' '}
            <span className={`status-tag ${activeLocation.isMultiYear ? 'tag-multi' : 'tag-single'}`}>
              {activeLocation.isMultiYear ? '7 Train + 1 Test' : '2023'}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}
