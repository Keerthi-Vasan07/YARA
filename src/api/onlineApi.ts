/** Backend-owned online dataset contract. No provider endpoint is exposed here. */
const API_BASE = '/api/online';

export interface OnlineVariable { id: string; source_name: string; name: string; units: string; type: 'scalar' | 'vector_component'; category: string; vector_group?: string | null; paired_component?: string | null; colormap?: string; vmin?: number | null; vmax?: number | null; log_scale?: boolean; }
export interface OnlineDataset { id: string; name: string; provider: string; source: string; description: string; variables: OnlineVariable[]; temporal_resolution: string; spatial_resolution: string; coverage: Record<string, number>; capabilities: Record<string, boolean>; }
export interface OnlineInspection { coordinates: Record<string, string>; dimensions: Record<string, number>; time_range: [string | null, string | null]; temporal_resolution: string; coverage: Record<string, number>; variables: OnlineVariable[]; }
export interface OnlineMetadata extends OnlineDataset { inspection: OnlineInspection; }
export interface OnlineTimes { dataset_id: string; start: string | null; end: string | null; temporal_resolution: string; timestamps: string[]; }
export interface OnlinePointQuery {
  dataset_id: string;
  variable: string;
  timestamp?: string;
  units: string;
  requested_lat: number;
  requested_lon: number;
  matched_lat: number;
  matched_lon: number;
  value?: number | null;
  values?: (number | null)[];
  depth_values?: number[];
  variable_name?: string;
  variable_key?: string;
  display_name?: string;
  latitude?: number;
  longitude?: number;
  matched_date?: string;
  date_matched?: string;
  requested_date?: string;
  date_requested?: string;
  units_display?: string;
  grid?: { lat_min: number; lat_max: number; lon_min: number; lon_max: number };
  message?: string | null;
  provider?: string;
  source?: string;
}

async function json<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Online API error ${response.status}`); }
  return response.json() as Promise<T>;
}
export const fetchOnlineDatasets = async () => {
  const data = await json<any>(`${API_BASE}/datasets`);
  if (data && Array.isArray(data.datasets)) {
    return { datasets: data.datasets as OnlineDataset[] };
  }
  if (Array.isArray(data)) {
    return { datasets: data as OnlineDataset[] };
  }
  return { datasets: [] };
};
export const fetchOnlineMetadata = (id: string) => json<OnlineMetadata>(`${API_BASE}/datasets/${encodeURIComponent(id)}/metadata`);
export const fetchOnlineTimes = (id: string) => json<OnlineTimes>(`${API_BASE}/datasets/${encodeURIComponent(id)}/times`);

export interface OnlineFrameResponse { blobUrl: string; status: number; blobSize: number; blobType: string; matchedTime: string; matchedDate: string; datasetId: string; variable: string; bounds: { west: number; south: number; east: number; north: number }; width?: number; height?: number; }
export async function fetchOnlineFrame(datasetId: string, variable: string, time: string, options: { colormap?: string; vmin?: number; vmax?: number; maxPixels?: number } = {}, signal?: AbortSignal): Promise<OnlineFrameResponse> {
  const params = new URLSearchParams({ dataset_id: datasetId, variable, time, date: time, lat_min: '-80', lat_max: '90', lon_min: '-180', lon_max: '180', max_pixels: String(options.maxPixels ?? 1536), colormap: options.colormap ?? 'viridis' });
  if (Number.isFinite(options.vmin)) params.set('vmin', String(options.vmin));
  if (Number.isFinite(options.vmax)) params.set('vmax', String(options.vmax));
  console.log(`[ONLINE] requesting frame: variable=${variable} time=${time} colormap=${options.colormap}`);

  const controller = new AbortController();
  let timedOut = false;

  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 120000);

  const onCallerAbort = () => {
    controller.abort();
  };

  if (signal) {
    if (signal.aborted) {
      clearTimeout(timeoutId);
      controller.abort();
    } else {
      signal.addEventListener('abort', onCallerAbort, { once: true });
    }
  }

  try {
    const response = await fetch(`${API_BASE}/data?${params}`, { signal: controller.signal });
    console.log(`[ONLINE] response status: ${response.status}`);
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Frame request failed (${response.status})`); }
    const numberHeader = (name: string, fallback: number) => Number(response.headers.get(name) ?? fallback);
    const blob = await response.blob();
    console.log(`[ONLINE] PNG size: ${blob.size} bytes`);
    const matchedTime = response.headers.get('X-Date-Matched') || response.headers.get('X-Time-Matched') || time;
    const bounds = { west: numberHeader('X-Bounds-West', -180), south: numberHeader('X-Bounds-South', -80), east: numberHeader('X-Bounds-East', 180), north: numberHeader('X-Bounds-North', 90) };
    console.log(`[ONLINE] bounds: west=${bounds.west} south=${bounds.south} east=${bounds.east} north=${bounds.north}`);
    return {
      blobUrl: URL.createObjectURL(blob), status: response.status, blobSize: blob.size, blobType: blob.type, matchedTime, matchedDate: matchedTime,
      datasetId: response.headers.get('X-Dataset-Id') || datasetId, variable: response.headers.get('X-Variable') || variable,
      bounds,
      width: Number(response.headers.get('X-Raster-Width') || 0) || undefined, height: Number(response.headers.get('X-Raster-Height') || 0) || undefined,
    };
  } catch (err: any) {
    if (timedOut) {
      throw new Error('Ocean data request timed out after 120 seconds.');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
    if (signal) {
      signal.removeEventListener('abort', onCallerAbort);
    }
  }
}
export function fetchOnlinePoint(datasetId: string, variable: string, time: string, lon: number, lat: number, signal?: AbortSignal) {
  return json<OnlinePointQuery>(`${API_BASE}/point?${new URLSearchParams({ dataset_id: datasetId, variable, time, date: time, lon: String(lon), lat: String(lat) })}`, signal);
}
