export interface ArgoObservation {
  lat: number;
  lon: number;
  time?: string | null;
  temperature?: number | null;
  salinity?: number | null;
  pressure?: number | null;
  depth?: number | null;
  cycle?: number | string | null;
  [key: string]: unknown;
}

export interface ArgoFloat {
  id: string;
  platform_number?: string | number | null;
  observations: ArgoObservation[];
  [key: string]: unknown;
}

export interface GliderPoint {
  lat: number;
  lon: number;
  time?: string | null;
  depth?: number | null;
  temperature?: number | null;
  salinity?: number | null;
  [key: string]: unknown;
}

export interface GliderPlatform {
  id: string;
  points: GliderPoint[];
  [key: string]: unknown;
}

export interface ArgoStats {
  platform_count: number;
  observation_count: number;
  latest_time?: string | null;
  [key: string]: unknown;
}

const API_BASE = '/api/argo-glider';

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail?: unknown }).detail)
        : `Argo/Glider API error (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

function firstArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== 'object') return [];
  const record = value as Record<string, unknown>;
  for (const key of ['floats', 'platforms', 'data', 'trajectories', 'observations', 'gliders']) {
    if (Array.isArray(record[key])) return record[key] as unknown[];
  }
  return [];
}

function numberValue(value: unknown): number | null {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeObservation(value: unknown): ArgoObservation | null {
  if (!value || typeof value !== 'object') return null;
  const r = value as Record<string, unknown>;
  const lat = numberValue(r.lat ?? r.latitude);
  const lon = numberValue(r.lon ?? r.longitude);
  if (lat === null || lon === null) return null;
  return {
    ...r,
    lat,
    lon,
    time: r.time == null ? (r.datetime == null ? null : String(r.datetime)) : String(r.time),
    temperature: numberValue(r.temperature ?? r.temp ?? r.thetao),
    salinity: numberValue(r.salinity ?? r.psal ?? r.so),
    pressure: numberValue(r.pressure ?? r.pres),
    depth: numberValue(r.depth),
    cycle: (r.cycle ?? r.cycle_number ?? null) as number | string | null,
  };
}

function normalizeFloat(value: unknown, index: number): ArgoFloat | null {
  if (!value || typeof value !== 'object') return null;
  const r = value as Record<string, unknown>;
  const rawPoints = firstArray(r.observations ?? r.points ?? r.trajectory ?? value);
  const observations = rawPoints.map(normalizeObservation).filter(Boolean) as ArgoObservation[];
  const id = String(r.id ?? r.platform_number ?? r.platform ?? r.float_id ?? `float-${index}`);
  return { ...r, id, platform_number: (r.platform_number ?? id) as string | number, observations };
}

export async function getArgoFloats(signal?: AbortSignal): Promise<ArgoFloat[]> {
  const raw = await request<unknown>('/floats', signal);
  return firstArray(raw).map(normalizeFloat).filter(Boolean) as ArgoFloat[];
}

export async function getArgoStats(signal?: AbortSignal): Promise<ArgoStats> {
  const raw = await request<unknown>('/stats', signal);
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  return {
    ...r,
    platform_count: Number(r.platform_count ?? r.platforms ?? r.float_count ?? 0),
    observation_count: Number(r.observation_count ?? r.observations ?? 0),
    latest_time: r.latest_time == null ? null : String(r.latest_time),
  };
}

function normalizeGlider(value: unknown, index: number): GliderPlatform | null {
  if (!value || typeof value !== 'object') return null;
  const r = value as Record<string, unknown>;
  const rawPoints = firstArray(r.points ?? r.observations ?? r.trajectory ?? value);
  const points = rawPoints.map(normalizeObservation).filter(Boolean) as GliderPoint[];
  const id = String(r.id ?? r.glider_id ?? r.platform ?? `glider-${index}`);
  return { ...r, id, points };
}

export interface GliderLoadResult {
  gliders: GliderPlatform[];
  statuses: unknown[];
  discovery: unknown;
}

export async function getGliders(signal?: AbortSignal): Promise<GliderPlatform[]> {
  const raw = await request<unknown>('/gliders', signal);
  return firstArray(raw).map(normalizeGlider).filter(Boolean) as GliderPlatform[];
}

/**
 * Like getGliders(), but also surfaces the reader's per-file/per-connection
 * statuses and discovery info, so the UI can show a clear error when the
 * IFREMER FTP source itself failed (as opposed to legitimately having no
 * gliders to report).
 */
export async function getGliderLoadResult(signal?: AbortSignal): Promise<GliderLoadResult> {
  const raw = await request<unknown>('/gliders', signal);
  const record = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const gliders = firstArray(raw).map(normalizeGlider).filter(Boolean) as GliderPlatform[];
  const statuses = Array.isArray(record.statuses) ? record.statuses : [];
  return { gliders, statuses, discovery: record.discovery ?? null };
}

export async function getSources(signal?: AbortSignal): Promise<unknown> {
  return request('/sources', signal);
}

export async function getArgoGliderHealth(signal?: AbortSignal): Promise<unknown> {
  return request('/health', signal);
}
