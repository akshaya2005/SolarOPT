import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { LOCATIONS } from '../data/locations';
import { createCityMarkerIcon } from '../utils/leafletIcons';

export function LocationMap({ selectedLocationId, onSelectLocation }) {
  const containerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersRef = useRef({});

  // Initialize Leaflet map with clean lifecycle cleanup
  useEffect(() => {
    if (!containerRef.current || mapInstanceRef.current) return;

    const map = L.map(containerRef.current, {
      center: [34.0, -92.5],
      zoom: 3.8,
      scrollWheelZoom: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 12,
    }).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Synchronize markers and camera position when selected location changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    const selectedLocation = LOCATIONS.find((loc) => loc.id === selectedLocationId) || LOCATIONS[0];

    // Smoothly pan camera to selected location
    if (selectedLocation?.coordinates) {
      map.flyTo(selectedLocation.coordinates, 5, { duration: 1.2 });
    }

    // Clean up previous markers
    Object.values(markersRef.current).forEach((marker) => marker.remove());
    markersRef.current = {};

    // Render city markers with active styling
    LOCATIONS.forEach((loc) => {
      const isSelected = loc.id === selectedLocationId;
      const marker = L.marker(loc.coordinates, {
        icon: createCityMarkerIcon(isSelected, loc.city),
      }).addTo(map);

      // Create interactive popup element
      const popupDiv = document.createElement('div');
      popupDiv.className = 'map-popup-card';
      popupDiv.innerHTML = `
        <h4 class="popup-city-title">${loc.name}</h4>
        <p class="popup-stat-line"><strong>Climate:</strong> ${loc.climate}</p>
        <p class="popup-stat-line"><strong>Grid Elevation:</strong> ${loc.elevation}</p>
        <p class="popup-stat-line"><strong>Coordinates:</strong> ${loc.coordinates[0]}° N, ${Math.abs(loc.coordinates[1])}° W</p>
        <p class="popup-stat-line"><strong>Data span:</strong> ${loc.years}</p>
        ${
          isSelected
            ? '<span class="popup-active-badge">✓ Currently Selected</span>'
            : `<button type="button" class="popup-select-btn">Switch to ${loc.city}</button>`
        }
      `;

      if (!isSelected) {
        const switchBtn = popupDiv.querySelector('.popup-select-btn');
        if (switchBtn) {
          switchBtn.onclick = () => {
            onSelectLocation(loc.id);
            map.closePopup();
          };
        }
      }

      marker.bindPopup(popupDiv);
      marker.on('click', () => onSelectLocation(loc.id));
      markersRef.current[loc.id] = marker;
    });
  }, [selectedLocationId, onSelectLocation]);

  return (
    <div className="sidebar-card location-map-card">
      <div className="card-header-compact">
        <div className="card-title-group">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"></polygon>
            <line x1="9" y1="3" x2="9" y2="18"></line>
            <line x1="15" y1="6" x2="15" y2="21"></line>
          </svg>
          <span className="card-title-compact">Geographic Sites</span>
        </div>
        <span className="map-hint-badge">Click marker to select</span>
      </div>

      <div className="map-frame">
        <div
          ref={containerRef}
          className="leaflet-map-element"
          style={{ width: '100%', height: '100%' }}
        />
      </div>
    </div>
  );
}
