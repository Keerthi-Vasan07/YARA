import { AnalysisOptions, GradientStop } from '../types/dataset';

export const defaultStops = (): GradientStop[] => [
  { position: 0, color: '#0000ff' }, { position: 1, color: '#ff0000' },
];
export const defaultAnalysis = (): AnalysisOptions => ({
  mode: 'none', exact_temperature: 30, tolerance: 0.1,
  range_min: 30, range_max: 35, flat_color: '#ff4500', stops: null,
});
export const gradientCss = (stops: GradientStop[]) =>
  `linear-gradient(90deg, ${[...stops].sort((a, b) => a.position - b.position)
    .map(s => `${s.color} ${s.position * 100}%`).join(', ')})`;

export function interpolateColor(stops: GradientStop[], position: number): string {
  const sorted = [...stops].sort((a, b) => a.position - b.position);
  const right = sorted.find(s => s.position >= position) ?? sorted[sorted.length - 1];
  const left = [...sorted].reverse().find(s => s.position <= position) ?? sorted[0];
  const ratio = right.position === left.position ? 0 : (position - left.position) / (right.position - left.position);
  return '#' + [1, 3, 5].map(i => Math.round(parseInt(left.color.slice(i, i + 2), 16) * (1 - ratio)
    + parseInt(right.color.slice(i, i + 2), 16) * ratio).toString(16).padStart(2, '0')).join('');
}

export function analysisError(value: AnalysisOptions): string | null {
  if (![value.exact_temperature, value.tolerance, value.range_min, value.range_max].every(Number.isFinite)) return 'Enter finite numeric values.';
  if (value.tolerance < 0) return 'Tolerance must be non-negative.';
  if (value.range_min > value.range_max) return 'Range minimum must be less than or equal to maximum.';
  return null;
}

export function analysisUnits(units?: string): string {
  const key = (units ?? '').toLowerCase().replace(/[ _]/g, '');
  return ['k', 'kelvin', 'degreekelvin', 'degreeskelvin', 'f', '°f', 'degf', 'degreefahrenheit', 'degreesfahrenheit'].includes(key) ? '°C' : (units || 'dataset units');
}
