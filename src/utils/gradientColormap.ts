/**
 * Gradient colormap engine for the live color-bar / gradient-editor preview.
 * Keep in sync with server/pipeline/gradient_colormap.py (the backend reimplements
 * the same normalize+interpolate logic in Python for PNG rendering, since the two
 * cannot share code across the language boundary).
 */
import type { GradientStop } from '../types/dataset';

export const DEFAULT_GRADIENT_STOPS: GradientStop[] = [
  { position: 0.0, color: '#0a1929' },
  { position: 0.5, color: '#00acc1' },
  { position: 1.0, color: '#f44336' },
];

export function sortAndValidateStops(stops: GradientStop[]): GradientStop[] {
  if (!stops || stops.length < 2) {
    return DEFAULT_GRADIENT_STOPS.map((s) => ({ ...s }));
  }
  const cleaned = stops.map((s) => ({
    position: Math.min(1, Math.max(0, s.position)),
    color: s.color,
  }));
  cleaned.sort((a, b) => a.position - b.position);
  return cleaned;
}

export function normalizeValue(value: number, min: number, max: number): number {
  const vMax = max <= min ? min + 1 : max;
  return Math.min(1, Math.max(0, (value - min) / (vMax - min)));
}

function parseColor(color: string): [number, number, number, number] {
  const el = document.createElement('div');
  el.style.color = color;
  document.body.appendChild(el);
  const computed = getComputedStyle(el).color;
  document.body.removeChild(el);
  const match = computed.match(/rgba?\(([^)]+)\)/);
  if (!match) return [0, 0, 0, 1];
  const parts = match[1].split(',').map((p) => parseFloat(p.trim()));
  return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0, parts[3] ?? 1];
}

/** Interpolates a color at normalized position t (0..1) across the given gradient stops. */
export function interpolateGradient(stops: GradientStop[], t: number): string {
  const sorted = sortAndValidateStops(stops);
  const clamped = Math.min(1, Math.max(0, t));

  if (clamped <= sorted[0].position) return sorted[0].color;
  if (clamped >= sorted[sorted.length - 1].position) return sorted[sorted.length - 1].color;

  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i];
    const b = sorted[i + 1];
    if (clamped >= a.position && clamped <= b.position) {
      const span = b.position - a.position || 1;
      const localT = (clamped - a.position) / span;
      const [r1, g1, b1, a1] = parseColor(a.color);
      const [r2, g2, b2, a2] = parseColor(b.color);
      const r = Math.round(r1 + (r2 - r1) * localT);
      const g = Math.round(g1 + (g2 - g1) * localT);
      const bch = Math.round(b1 + (b2 - b1) * localT);
      const al = a1 + (a2 - a1) * localT;
      return `rgba(${r}, ${g}, ${bch}, ${al.toFixed(3)})`;
    }
  }
  return sorted[sorted.length - 1].color;
}

/** CSS linear-gradient string for rendering the color bar / editor bar background. */
export function gradientCssString(stops: GradientStop[]): string {
  const sorted = sortAndValidateStops(stops);
  const parts = sorted.map((s) => `${s.color} ${(s.position * 100).toFixed(2)}%`);
  return `linear-gradient(90deg, ${parts.join(', ')})`;
}

export function reverseStops(stops: GradientStop[]): GradientStop[] {
  const sorted = sortAndValidateStops(stops);
  return sorted
    .map((s) => ({ position: 1 - s.position, color: s.color }))
    .sort((a, b) => a.position - b.position);
}
