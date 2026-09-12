/**
 * Color mapping utilities for SST visualization.
 * Uses a thermal colormap similar to cmocean.cm.thermal
 */

// SST range in Celsius
const SST_MIN = -2;
const SST_MAX = 20;

// Thermal colormap stops (approximating cmocean.thermal)
const THERMAL_COLORS: [number, number, number][] = [
  [10, 17, 40],      // -2°C - very cold (dark blue)
  [26, 45, 90],      // 0°C
  [30, 80, 128],     // 3°C
  [45, 138, 138],    // 6°C
  [77, 184, 112],    // 9°C
  [143, 209, 79],    // 12°C
  [212, 225, 87],    // 15°C
  [255, 202, 40],    // 17°C
  [255, 152, 0],     // 18°C
  [244, 67, 54],     // 19°C
  [183, 28, 28],     // 20°C - warm (dark red)
];

/**
 * Interpolate between two colors.
 */
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/**
 * Get RGBA color for a given SST value.
 * @param sst Temperature in Celsius
 * @param alpha Opacity (0-1)
 * @returns Cesium.Color compatible RGBA values (0-1 range)
 */
export function getSSTColor(sst: number, alpha: number = 1.0): { red: number; green: number; blue: number; alpha: number } {
  // Normalize to 0-1 range
  const t = Math.max(0, Math.min(1, (sst - SST_MIN) / (SST_MAX - SST_MIN)));
  
  // Find the two colors to interpolate between
  const numColors = THERMAL_COLORS.length;
  const scaledT = t * (numColors - 1);
  const lowerIdx = Math.floor(scaledT);
  const upperIdx = Math.min(lowerIdx + 1, numColors - 1);
  const localT = scaledT - lowerIdx;
  
  const lowerColor = THERMAL_COLORS[lowerIdx];
  const upperColor = THERMAL_COLORS[upperIdx];
  
  return {
    red: lerp(lowerColor[0], upperColor[0], localT) / 255,
    green: lerp(lowerColor[1], upperColor[1], localT) / 255,
    blue: lerp(lowerColor[2], upperColor[2], localT) / 255,
    alpha,
  };
}

/**
 * Generate a canvas-based color legend.
 */
export function createLegendGradient(): string {
  const stops = THERMAL_COLORS.map((color, i) => {
    const percent = (i / (THERMAL_COLORS.length - 1)) * 100;
    return `rgb(${color[0]}, ${color[1]}, ${color[2]}) ${percent}%`;
  });
  return `linear-gradient(to right, ${stops.join(', ')})`;
}

export { SST_MIN, SST_MAX };
