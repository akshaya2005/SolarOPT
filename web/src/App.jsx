import React, { useState, useMemo } from 'react';
import { LOCATIONS, DEFAULT_LOCATION_ID } from './data/locations';
import { useSolarData } from './hooks/useSolarData';
import {
  selectOptimalConfiguration,
  findConfiguration,
  recalculateBaselines,
} from './utils/optimization';

import { Header } from './components/Header';
import { LocationSelector } from './components/LocationSelector';
import { LocationMap } from './components/LocationMap';
import { RiskSlider } from './components/RiskSlider';
import { SummaryCards } from './components/SummaryCards';
import { SolarHeatmap } from './components/SolarHeatmap';
import { YearlyEnergyChart } from './components/YearlyEnergyChart';
import { BaselineComparison } from './components/BaselineComparison';
import { ConfigurationDetail } from './components/ConfigurationDetail';
import { SunView3D } from './components/SunView3D';

import './styles/dashboard.css';

export default function App() {
  const [selectedLocationId, setSelectedLocationId] = useState(DEFAULT_LOCATION_ID);
  const [lambdaValue, setLambdaValue] = useState(0.5);
  const [manualSelection, setManualSelection] = useState(null);

  // Active location metadata from registry
  const activeLocation = useMemo(
    () => LOCATIONS.find((loc) => loc.id === selectedLocationId) || LOCATIONS[0],
    [selectedLocationId]
  );

  // Fetch precomputed data bundle from Vite public directory
  const { data, loading, error } = useSolarData(activeLocation.file);

  // Reset manual configuration inspection when switching locations
  const handleLocationChange = (newLocationId) => {
    setSelectedLocationId(newLocationId);
    setManualSelection(null);
  };

  // Compute optimal configuration based on current lambda using training statistics only
  const optimalConfig = useMemo(() => {
    if (!data || !data.configurations) return null;
    return selectOptimalConfiguration(data.configurations, lambdaValue);
  }, [data, lambdaValue]);

  // Determine currently selected configuration (either manually inspected cell or optimal)
  const selectedConfig = useMemo(() => {
    if (!data || !data.configurations) return null;
    if (manualSelection) {
      const found = findConfiguration(
        data.configurations,
        manualSelection.tilt,
        manualSelection.azimuth
      );
      if (found) return found;
    }
    return optimalConfig;
  }, [data, manualSelection, optimalConfig]);

  // Recalculate baseline comparisons for the active lambda
  const baselinesData = useMemo(() => {
    if (!data) return null;
    return recalculateBaselines(data, lambdaValue);
  }, [data, lambdaValue]);

  // Reset manual exploration back to the optimal configuration
  const handleResetToOptimal = () => {
    setManualSelection(null);
  };

  // Handle cell selection from the heatmap
  const handleSelectHeatmapCell = ({ tilt, azimuth }) => {
    setManualSelection({ tilt, azimuth });
  };

  return (
    <div className="dashboard-root">
      <Header />

      {loading && (
        <div className="dashboard-loading-overlay">
          <div className="solar-spinner"></div>
          <p>Loading NREL NSRDB solar model estimates for {activeLocation.name}...</p>
        </div>
      )}

      {error && (
        <div className="dashboard-error-state">
          <h3 className="error-title">Unable to Load Solar Model Data</h3>
          <p>{error}</p>
          <button
            type="button"
            className="popup-select-btn"
            style={{ width: 'auto', padding: '8px 16px', marginTop: '12px' }}
            onClick={() => handleLocationChange(selectedLocationId)}
          >
            Retry Loading
          </button>
        </div>
      )}

      {!loading && !error && data && (
        <main className="dashboard-main-container">
          {/* Left Sidebar */}
          <aside className="dashboard-sidebar">
            <LocationSelector
              selectedLocationId={selectedLocationId}
              onSelectLocation={handleLocationChange}
            />

            <LocationMap
              selectedLocationId={selectedLocationId}
              onSelectLocation={handleLocationChange}
            />

            <RiskSlider
              lambdaValue={lambdaValue}
              onChangeLambda={setLambdaValue}
              isMultiYear={activeLocation.isMultiYear}
            />
          </aside>

          {/* Main Analytics Content */}
          <section className="dashboard-content">
            {/* Top Metric Cards */}
            <SummaryCards
              optimalConfig={optimalConfig}
              selectedConfig={selectedConfig}
              lambdaValue={lambdaValue}
              isMultiYear={activeLocation.isMultiYear}
              onResetToOptimal={handleResetToOptimal}
            />

            {/* Interactive Energy Optimization Heatmap */}
            <SolarHeatmap
              configurations={data.configurations}
              optimalConfig={optimalConfig}
              selectedConfig={selectedConfig}
              lambdaValue={lambdaValue}
              isMultiYear={activeLocation.isMultiYear}
              onSelectConfig={handleSelectHeatmapCell}
            />

            {/* 3D Sunlight View, linked to the selected heatmap configuration */}
            {selectedConfig && (
              <SunView3D
                locationName={activeLocation.name}
                latitude={activeLocation.coordinates[0]}
                longitude={activeLocation.coordinates[1]}
                tilt={selectedConfig.tilt}
                azimuth={selectedConfig.azimuth}
              />
            )}

            {/* Dual Chart Row: Yearly Series & Baseline Benchmarks */}
            <div className="dual-chart-row">
              <YearlyEnergyChart
                selectedConfig={selectedConfig}
                trainYears={data.recommendation?.train_years}
                heldOutYears={data.recommendation?.held_out_years}
                isMultiYear={activeLocation.isMultiYear}
              />

              <BaselineComparison
                baselinesData={baselinesData}
                lambdaValue={lambdaValue}
                isMultiYear={activeLocation.isMultiYear}
              />
            </div>

            {/* System Configuration & Provenance */}
            <ConfigurationDetail
              metadata={data.metadata}
              schemaVersion={data.schema_version}
            />
          </section>
        </main>
      )}
    </div>
  );
}
