import * as THREE from "three";
import type { ProbeVariable } from "../types";

export const GLOBE_RADIUS = 1.0;
export const DEFAULT_SHELL_THICKNESS = 0.14; // 14% vertical exaggeration shell beneath surface

/**
 * Project (lat, lon, depth_m) to 3D Cartesian coordinates inside the Three.js globe:
 *   r(z) = R_globe - (z / z_max) * delta_r_shell
 *
 * @param latDeg Latitude in degrees (-90 to +90)
 * @param lonDeg Longitude in degrees (-180 to +180)
 * @param depthM Depth in meters (0 to maxDepthM)
 * @param maxDepthM Maximum profile depth (default 1000m)
 * @param globeRadius Radius of the outer globe sphere (default 1.0)
 * @param deltaRShell Shell depth penetration thickness (default 0.14)
 */
export function latLonDepthToVector3(
  latDeg: number,
  lonDeg: number,
  depthM: number,
  maxDepthM: number = 1000.0,
  globeRadius: number = GLOBE_RADIUS,
  deltaRShell: number = DEFAULT_SHELL_THICKNESS
): THREE.Vector3 {
  const clampedDepth = Math.max(0, Math.min(depthM, maxDepthM));
  const r = globeRadius - (clampedDepth / Math.max(1, maxDepthM)) * deltaRShell;

  const phi = (90 - latDeg) * (Math.PI / 180);
  const theta = (lonDeg + 180) * (Math.PI / 180);

  const x = -r * Math.sin(phi) * Math.cos(theta);
  const y = r * Math.cos(phi);
  const z = r * Math.sin(phi) * Math.sin(theta);

  return new THREE.Vector3(x, y, z);
}

/**
 * Standard (lat, lon) to Vector3 on the surface of a sphere of radius R.
 */
export function latLonToVector3(
  latDeg: number,
  lonDeg: number,
  radius: number = GLOBE_RADIUS
): THREE.Vector3 {
  return latLonDepthToVector3(latDeg, lonDeg, 0, 1000, radius, 0);
}

/**
 * Convert a 3D point in globe local space back to (lat, lon) in degrees.
 */
export function vector3ToLatLon(v: THREE.Vector3): { lat: number; lon: number } {
  const norm = v.clone().normalize();
  const phi = Math.acos(Math.max(-1, Math.min(1, norm.y)));
  const lat = 90 - phi * (180 / Math.PI);

  const theta = Math.atan2(norm.z, -norm.x);
  let lon = theta * (180 / Math.PI) - 180;

  while (lon < -180) lon += 360;
  while (lon > 180) lon -= 360;

  return { lat, lon };
}

// ─────────────────────────────────────────────────────────────────────────────
// Physical Colormaps for 3D Subsurface Column Profiling
// ─────────────────────────────────────────────────────────────────────────────

function interpolateStops(
  tNorm: number,
  stops: [number, number, number][]
): THREE.Color {
  const clamped = Math.max(0, Math.min(1, tNorm));
  const n = stops.length - 1;
  const scaled = clamped * n;
  const idx = Math.min(Math.floor(scaled), n - 1);
  const frac = scaled - idx;

  const [r1, g1, b1] = stops[idx];
  const [r2, g2, b2] = stops[idx + 1];

  return new THREE.Color(
    r1 + (r2 - r1) * frac,
    g1 + (g2 - g1) * frac,
    b1 + (b2 - b1) * frac
  );
}

// 1. Cool-to-Warm Colormap (2°C dark blue -> 30°C red)
const TEMP_STOPS: [number, number, number][] = [
  [0.12, 0.23, 0.54], // 2°C: deep navy blue (#1e3a8a)
  [0.02, 0.71, 0.83], // 10°C: cyan (#06b6d4)
  [0.06, 0.72, 0.51], // 18°C: sea emerald (#10b981)
  [0.96, 0.62, 0.04], // 24°C: warm amber (#f59e0b)
  [0.94, 0.27, 0.27], // 30°C: crimson red (#ef4444)
];

export function getTemperatureColor(tempC: number): THREE.Color {
  const norm = (tempC - 2.0) / (30.0 - 2.0);
  return interpolateStops(norm, TEMP_STOPS);
}

// 2. Haline Colormap (32 PSU cyan -> 37 PSU deep purple)
const SAL_STOPS: [number, number, number][] = [
  [0.13, 0.83, 0.93], // 32 PSU: cyan (#22d3ee)
  [0.23, 0.51, 0.96], // 33.5 PSU: ocean blue (#3b82f6)
  [0.39, 0.40, 0.95], // 35 PSU: indigo (#6366f1)
  [0.58, 0.20, 0.92], // 37 PSU: deep royal purple (#9333ea)
];

export function getSalinityColor(salPsu: number): THREE.Color {
  const norm = (salPsu - 32.0) / (37.0 - 32.0);
  return interpolateStops(norm, SAL_STOPS);
}

// 3. Algae / Chlorophyll Colormap (0.01 mg/m³ dark oceanic blue -> 2.5 mg/m³ emerald green)
const CHL_STOPS: [number, number, number][] = [
  [0.06, 0.09, 0.16], // 0.01 mg/m³: deep oceanic dark blue (#0f172a)
  [0.05, 0.45, 0.56], // 0.2 mg/m³: deep teal (#0e7490)
  [0.06, 0.72, 0.51], // 0.8 mg/m³: rich emerald green (#10b981)
  [0.52, 0.80, 0.09], // 2.5 mg/m³: vibrant algae green (#84cc16)
];

export function getChlorophyllColor(chlMgM3: number): THREE.Color {
  // Use log-scaling for chlorophyll to enhance contrast across dynamic ranges (0.01 to 2.5 mg/m³)
  const logMin = Math.log10(0.01);
  const logMax = Math.log10(2.5);
  const clampedVal = Math.max(0.01, Math.min(2.5, chlMgM3));
  const norm = (Math.log10(clampedVal) - logMin) / (logMax - logMin);
  return interpolateStops(norm, CHL_STOPS);
}

/**
 * Retrieve dynamic 3D node color based on the selected probe variable.
 */
export function getProbeVariableColor(
  variable: ProbeVariable,
  value: number
): THREE.Color {
  switch (variable) {
    case "temperature":
      return getTemperatureColor(value);
    case "salinity":
      return getSalinityColor(value);
    case "chlorophyll":
      return getChlorophyllColor(value);
  }
}

/**
 * Returns formatted value and units for UI display.
 */
export function formatProbeValue(
  variable: ProbeVariable,
  value: number
): string {
  switch (variable) {
    case "temperature":
      return `${value.toFixed(2)} °C`;
    case "salinity":
      return `${value.toFixed(2)} PSU`;
    case "chlorophyll":
      return `${value.toFixed(3)} mg/m³`;
  }
}

/**
 * Normalized mapping of (lat, lon, depth) to Volume Box coordinates [-width/2, width/2]:
 */
export function geoToVolumeCoords(
  lat: number,
  lon: number,
  depth: number,
  bounds: { minLat: number; maxLat: number; minLon: number; maxLon: number; maxDepth: number },
  boxDims: { width: number; height: number; depth: number }
): THREE.Vector3 {
  const lonNorm = (lon - bounds.minLon) / Math.max(1e-6, bounds.maxLon - bounds.minLon);
  const latNorm = (lat - bounds.minLat) / Math.max(1e-6, bounds.maxLat - bounds.minLat);
  const depthNorm = Math.min(depth, bounds.maxDepth) / Math.max(1e-6, bounds.maxDepth);

  // Un-mirrored X axis goes from West (+width/2) to East (-width/2) in box space:
  const x = (0.5 - lonNorm) * boxDims.width;
  const y = (0.5 - depthNorm) * boxDims.height;
  const z = (latNorm - 0.5) * boxDims.depth;

  return new THREE.Vector3(x, y, z);
}

