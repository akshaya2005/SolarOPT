import React from 'react';

export function RiskSlider({ lambdaValue, onChangeLambda, isMultiYear }) {
  const PRESETS = [
    { label: 'Neutral (0.0)', value: 0.0, desc: 'Pure mean energy maximization' },
    { label: 'Default (0.5)', value: 0.5, desc: 'Balanced yield & stability' },
    { label: 'Averse (1.5)', value: 1.5, desc: 'Penalizes variability' },
    { label: 'Stability (3.0)', value: 3.0, desc: 'Prioritizes consistency' },
  ];

  return (
    <div className="sidebar-card risk-slider-card">
      <div className="card-header-compact">
        <div className="card-title-group">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="4" y1="21" x2="4" y2="14"></line>
            <line x1="4" y1="10" x2="4" y2="3"></line>
            <line x1="12" y1="21" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12" y2="3"></line>
            <line x1="20" y1="21" x2="20" y2="16"></line>
            <line x1="20" y1="12" x2="20" y2="3"></line>
            <line x1="1" y1="14" x2="7" y2="14"></line>
            <line x1="9" y1="8" x2="15" y2="8"></line>
            <line x1="17" y1="16" x2="23" y2="16"></line>
          </svg>
          <span className="card-title-compact">Risk Weight (λ)</span>
        </div>
        <span className="lambda-value-display">λ = {Number(lambdaValue).toFixed(2)}</span>
      </div>

      <div className="slider-container">
        <div className="slider-track-wrap">
          <input
            id="risk-slider"
            type="range"
            min="0"
            max="3"
            step="0.05"
            value={lambdaValue}
            onChange={(e) => onChangeLambda(parseFloat(e.target.value))}
            className="styled-range-slider"
          />
        </div>
        <div className="slider-ticks-row">
          <span><strong>0.0</strong> (Neutral)</span>
          <span><strong>1.0</strong></span>
          <span><strong>2.0</strong></span>
          <span><strong>3.0</strong> (Averse)</span>
        </div>
      </div>

      <div className="preset-buttons-row">
        {PRESETS.map((p) => {
          const isActive = Math.abs(lambdaValue - p.value) < 0.02;
          return (
            <button
              key={p.value}
              type="button"
              className={`preset-btn ${isActive ? 'preset-active' : ''}`}
              onClick={() => onChangeLambda(p.value)}
              title={p.desc}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      <div className="objective-formula-box">
        <code className="formula-code">
          Score = Mean − <strong>{Number(lambdaValue).toFixed(2)}</strong> × StdDev
        </code>
      </div>

      {!isMultiYear && (
        <div className="single-year-alert">
          <span>Single year: Std Dev = <strong>0.0 kWh</strong> (Score = Mean for all λ)</span>
        </div>
      )}
    </div>
  );
}
