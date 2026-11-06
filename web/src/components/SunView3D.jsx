import React, { useEffect, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import * as THREE from 'three';

// Scene units: 1 unit ~ 1 meter. Axes: +x = east, +y = up, -z = north (+z = south)
const SUN_DISTANCE = 5;
const PANEL_WIDTH = 2.0;
const PANEL_DEPTH = 1.2;
const PANEL_HEIGHT = 0.9; // height of the panel center above the ground
const DEMO_YEAR = 2025;

const toRad = (deg) => (deg * Math.PI) / 180;
const toDeg = (rad) => (rad * 180) / Math.PI;

// Approximate local standard time from longitude (Miami -80 -> UTC-5, Denver -105 -> UTC-7)
// Daylight saving time is ignored, so labels say "standard time"
function utcOffsetHours(lon) {
  return Math.round(lon / 15);
}

// Day of year (1-365) -> Date at the given local minutes after midnight
function makeDate(dayOfYear, minutes, lon) {
  const utcMs =
    Date.UTC(DEMO_YEAR, 0, dayOfYear, 0, 0) + (minutes - utcOffsetHours(lon) * 60) * 60 * 1000;
  return new Date(utcMs);
}

// Sun position (altitude, and azimuth measured from south, positive toward west), using the
// standard astronomical approximation from the SunCalc library (accurate to well under 1 degree)
function getSunPosition(date, lat, lon) {
  const rad = Math.PI / 180;
  const days = date.valueOf() / 86400000 - 0.5 + 2440588 - 2451545; // days since J2000
  const M = rad * (357.5291 + 0.98560028 * days); // solar mean anomaly
  const C = rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  const L = M + C + rad * 102.9372 + Math.PI; // ecliptic longitude
  const e = rad * 23.4397; // obliquity of the Earth
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  const ra = Math.atan2(Math.sin(L) * Math.cos(e), Math.cos(L));
  const phi = rad * lat;
  const H = rad * (280.16 + 360.9856235 * days) + rad * lon - ra; // hour angle
  return {
    azimuth: Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi)),
    altitude: Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H)),
  };
}

// Unit vector pointing from the panel toward the sun, plus altitude in degrees
function sunVector(date, lat, lon) {
  const pos = getSunPosition(date, lat, lon);
  // SunCalc azimuth is measured from south, positive toward west. Convert to compass
  // azimuth (clockwise from north, 180 = south) to match the rest of SolarOPT
  const compassAz = pos.azimuth + Math.PI;
  const alt = pos.altitude;
  const v = new THREE.Vector3(
    Math.sin(compassAz) * Math.cos(alt), // east
    Math.sin(alt), // up
    -Math.cos(compassAz) * Math.cos(alt) // north is -z
  );
  return { vector: v, altitudeDeg: toDeg(alt), azimuthDeg: (toDeg(compassAz) + 360) % 360 };
}

// Unit vector perpendicular to the panel face, from SolarOPT's tilt/azimuth convention
function panelNormal(tiltDeg, azimuthDeg) {
  const t = toRad(tiltDeg);
  const a = toRad(azimuthDeg);
  return new THREE.Vector3(Math.sin(a) * Math.sin(t), Math.cos(t), -Math.cos(a) * Math.sin(t));
}

function formatTime(minutes) {
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  const suffix = h < 12 ? 'am' : 'pm';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
}

function formatDay(dayOfYear) {
  const d = new Date(Date.UTC(DEMO_YEAR, 0, dayOfYear));
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function Panel({ tilt, azimuth }) {
  // Tilt about the x axis first (tips the face toward south), then turn about y to face
  // the requested azimuth. Euler order 'YXZ' applies X before Y
  const rotation = useMemo(
    () => new THREE.Euler(toRad(tilt), Math.PI - toRad(azimuth), 0, 'YXZ'),
    [tilt, azimuth]
  );
  return (
    <group position={[0, PANEL_HEIGHT, 0]} rotation={rotation}>
      {/* Panel body (dark frame) */}
      <mesh castShadow receiveShadow>
        <boxGeometry args={[PANEL_WIDTH, 0.05, PANEL_DEPTH]} />
        <meshStandardMaterial color="#1e293b" />
      </mesh>
      {/* Blue cell surface on the sun-facing side */}
      <mesh position={[0, 0.026, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[PANEL_WIDTH * 0.94, PANEL_DEPTH * 0.9]} />
        <meshStandardMaterial color="#2563eb" metalness={0.3} roughness={0.35} />
      </mesh>
    </group>
  );
}

function Post() {
  return (
    <mesh position={[0, PANEL_HEIGHT / 2, 0]} castShadow>
      <cylinderGeometry args={[0.04, 0.04, PANEL_HEIGHT, 12]} />
      <meshStandardMaterial color="#64748b" />
    </mesh>
  );
}

function Arrow({ direction, color, length }) {
  const helper = useMemo(() => {
    const h = new THREE.ArrowHelper(
      direction.clone().normalize(),
      new THREE.Vector3(0, PANEL_HEIGHT, 0),
      length,
      color,
      0.25,
      0.14
    );
    return h;
  }, [direction, color, length]);
  return <primitive object={helper} />;
}

// Flat text label drawn onto a small canvas texture, so it stays inside the 3D scene
function makeLabelTexture(text) {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  ctx.beginPath();
  ctx.arc(32, 32, 28, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#334155';
  ctx.font = 'bold 34px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 32, 34);
  return new THREE.CanvasTexture(canvas);
}

function CompassLabels() {
  const r = 5.6;
  const labels = useMemo(
    () => [
      ['N', [0, 0.35, -r]],
      ['S', [0, 0.35, r]],
      ['E', [r, 0.35, 0]],
      ['W', [-r, 0.35, 0]],
    ].map(([text, pos]) => ({ text, pos, texture: makeLabelTexture(text) })),
    []
  );
  return labels.map(({ text, pos, texture }) => (
    <sprite key={text} position={pos} scale={[0.85, 0.85, 1]}>
      <spriteMaterial map={texture} depthTest={false} />
    </sprite>
  ));
}

function Scene({ lat, lon, tilt, azimuth, dayOfYear, minutes }) {
  const sun = useMemo(
    () => sunVector(makeDate(dayOfYear, minutes, lon), lat, lon),
    [lat, lon, dayOfYear, minutes]
  );
  const normal = useMemo(() => panelNormal(tilt, azimuth), [tilt, azimuth]);

  // Sun's arc across the sky for the selected day (daytime points only)
  const pathPoints = useMemo(() => {
    const points = [];
    for (let m = 0; m <= 24 * 60; m += 10) {
      const s = sunVector(makeDate(dayOfYear, m, lon), lat, lon);
      if (s.altitudeDeg > -1) {
        points.push(s.vector.clone().multiplyScalar(SUN_DISTANCE).add(new THREE.Vector3(0, PANEL_HEIGHT, 0)));
      }
    }
    return points;
  }, [lat, lon, dayOfYear]);

  const sunUp = sun.altitudeDeg > 0;
  const sunPosition = sun.vector.clone().multiplyScalar(SUN_DISTANCE).add(new THREE.Vector3(0, PANEL_HEIGHT, 0));

  return (
    <>
      <color attach="background" args={[sunUp ? '#e0f2fe' : '#1e293b']} />
      <ambientLight intensity={sunUp ? 0.45 : 0.15} />
      <hemisphereLight args={['#ffffff', '#94a3b8', sunUp ? 0.35 : 0.05]} />
      {sunUp && (
        <directionalLight
          position={sunPosition.toArray()}
          intensity={2.2}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
          shadow-camera-left={-6}
          shadow-camera-right={6}
          shadow-camera-top={6}
          shadow-camera-bottom={-6}
          shadow-camera-near={0.5}
          shadow-camera-far={30}
          shadow-bias={-0.0005}
        />
      )}

      {/* Ground */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[6, 64]} />
        <meshStandardMaterial color="#d9e3d0" />
      </mesh>
      <gridHelper args={[12, 12, '#94a3b8', '#cbd5e1']} position={[0, 0.005, 0]} />
      <CompassLabels />

      <Post />
      <Panel tilt={tilt} azimuth={azimuth} />

      {/* Sun path and sun */}
      {pathPoints.length > 1 && (
        <Line points={pathPoints} color="#f59e0b" lineWidth={2} dashed dashSize={0.3} gapSize={0.2} />
      )}
      {sunUp && (
        <mesh position={sunPosition.toArray()}>
          <sphereGeometry args={[0.45, 32, 32]} />
          <meshBasicMaterial color="#fbbf24" />
        </mesh>
      )}

      {/* Panel normal (purple) and direction to the sun (orange) */}
      <Arrow direction={normal} color="#7c3aed" length={1.8} />
      {sunUp && <Arrow direction={sun.vector} color="#d97706" length={2.6} />}
    </>
  );
}

/**
 * 3D sunlight view: a panel at the selected tilt/azimuth, the sun's path for the chosen
 * day, the sun at the chosen time, shadows, and the incidence angle between the panel's
 * facing direction and the sun. Sun position is computed from lat/lon/time only
 * (not including clouds or weather)
 */
export function SunView3D({ locationName, latitude, longitude, tilt, azimuth }) {
  const [dayOfYear, setDayOfYear] = useState(172); // ~June 21
  const [minutes, setMinutes] = useState(11 * 60);
  const [playing, setPlaying] = useState(false);

  // Play button: advance the clock 10 minutes every 80 ms, wrapping at midnight.
  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => setMinutes((m) => (m + 10) % (24 * 60)), 80);
    return () => clearInterval(id);
  }, [playing]);

  const sun = useMemo(
    () => sunVector(makeDate(dayOfYear, minutes, longitude), latitude, longitude),
    [latitude, longitude, dayOfYear, minutes]
  );
  const normal = useMemo(() => panelNormal(tilt, azimuth), [tilt, azimuth]);

  const sunUp = sun.altitudeDeg > 0;
  const cosIncidence = normal.dot(sun.vector);
  const incidenceDeg = toDeg(Math.acos(Math.min(1, Math.max(-1, cosIncidence))));
  // Share of full-strength direct sunlight the panel catches (cosine of the incidence angle)
  const directShare = sunUp ? Math.max(0, cosIncidence) : 0;

  let status;
  if (!sunUp) status = 'Sun is below the horizon';
  else if (cosIncidence <= 0) status = 'Sun is behind the panel (no direct light)';
  else status = `Panel catches ${Math.round(directShare * 100)}% of full-strength direct sun`;

  return (
    <div className="dashboard-card sun-view-card">
      <div className="card-header-compact">
        <div>
          <h3 className="card-title-main">3D Sunlight View</h3>
          <p className="card-subtitle-main">
            {locationName} · panel at {tilt}° tilt facing {azimuth}° · drag to rotate, scroll to zoom
          </p>
        </div>
      </div>

      <div style={{ height: 380, borderRadius: 8, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        <Canvas shadows camera={{ position: [9, 6, 11], fov: 45 }}>
          <Scene
            lat={latitude}
            lon={longitude}
            tilt={tilt}
            azimuth={azimuth}
            dayOfYear={dayOfYear}
            minutes={minutes}
          />
          <OrbitControls target={[0, 2, 0]} maxPolarAngle={Math.PI / 2 - 0.05} minDistance={4} maxDistance={25} />
        </Canvas>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 12, alignItems: 'center' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '1 1 220px' }}>
          <span style={{ minWidth: 34 }}>Date</span>
          <input
            type="range"
            min={1}
            max={365}
            step={1}
            value={dayOfYear}
            onChange={(e) => setDayOfYear(Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ minWidth: 52, fontWeight: 600 }}>{formatDay(dayOfYear)}</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '1 1 220px' }}>
          <span style={{ minWidth: 34 }}>Time</span>
          <input
            type="range"
            min={0}
            max={24 * 60 - 10}
            step={10}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ minWidth: 64, fontWeight: 600 }}>{formatTime(minutes)}</span>
        </label>
        <button type="button" className="preset-btn" onClick={() => setPlaying((p) => !p)}>
          {playing ? 'Pause' : 'Play day'}
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginTop: 10, fontSize: 13, color: '#475569' }}>
        <span>
          Sun height: <strong>{sunUp ? `${Math.round(sun.altitudeDeg)}°` : 'below horizon'}</strong>
        </span>
        <span>
          Incidence angle: <strong>{sunUp ? `${Math.round(incidenceDeg)}°` : '—'}</strong>
        </span>
        <span>{status}</span>
      </div>
      <p style={{ fontSize: 12, color: '#64748b', margin: '8px 0 0' }}>
        Purple arrow: direction the panel faces. Orange arrow: direction to the sun. A smaller angle
        between them means more direct sunlight. Times are local standard time; clouds are not shown.
      </p>
    </div>
  );
}
