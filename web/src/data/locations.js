/**
 * Locations registry for SolarOPT.
 * Precomputed NSRDB weather data is provided in public/data/<file>.
 * Easily extensible for additional cities in future pipeline runs.
 */
export const LOCATIONS = [
  {
    id: 'miami_fl',
    name: 'Miami, FL',
    city: 'Miami',
    state: 'FL',
    file: 'miami_fl.json',
    coordinates: [25.7617, -80.1918],
    elevation: '17 m (NSRDB Grid)',
    years: '2018–2025 (8 yrs)',
    trainYears: '2018–2024 (7 yrs)',
    heldOutYears: '2025 (1 yr)',
    climate: 'Tropical Savanna (Köppen Aw)',
    isMultiYear: true,
    description: 'Multi-year historical dataset with 7 training years and 1 held-out test year for true out-of-sample evaluation.',
  },
  {
    id: 'denver_co',
    name: 'Denver, CO',
    city: 'Denver',
    state: 'CO',
    file: 'denver_co.json',
    coordinates: [39.7392, -104.9903],
    elevation: '1,797 m (NSRDB Grid; city ~1,609 m)',
    years: '2023 (1 yr)',
    trainYears: '2023 (1 yr)',
    heldOutYears: 'None',
    climate: 'Semi-Arid Continental (Köppen BSk)',
    isMultiYear: false,
    description: 'Single-year demonstration dataset (2023). Demonstrates energy modeling; multi-year variability cannot be established from one year.',
  },
];

export const DEFAULT_LOCATION_ID = 'miami_fl';

