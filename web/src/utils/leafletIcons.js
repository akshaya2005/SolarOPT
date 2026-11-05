import L from 'leaflet';

/**
 * Creates custom SVG-based Leaflet DivIcons for SolarOPT city markers.
 * This completely avoids broken image path issues in bundled Vite applications
 * and gives a modern, branded look with active state highlighting.
 */
export function createCityMarkerIcon(isSelected, cityName) {
  const bgFill = isSelected ? '#d97706' : '#2563eb';
  const pulseRing = isSelected
    ? '<span class="map-marker-pulse"></span>'
    : '';

  const html = `
    <div class="map-marker-container ${isSelected ? 'is-selected' : ''}">
      ${pulseRing}
      <div class="map-marker-pin" style="background-color: ${bgFill};">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
      </div>
      <div class="map-marker-label ${isSelected ? 'label-active' : ''}">${cityName}</div>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'custom-solar-marker',
    iconSize: [36, 48],
    iconAnchor: [18, 28],
    popupAnchor: [0, -28],
  });
}

