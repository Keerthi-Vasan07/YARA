/** Backend-owned online dataset contract. No provider endpoint is exposed here. */
const API_BASE = '/api/online';

export interface OnlineVariable { id: string; source_name: string; name: string; units: string; type: 'scalar' | 'vector_component'; category: string; vector_group?: string | null; paired_component?: string | null; colormap?: string; vmin?: number | null; vmax?: number | null; log_scale?: boolean; }
export interface OnlineDataset { id: string; name: string; provider: string; source: string; description: string; variables: OnlineVariable[]; temporal_resolution: string; spatial_resolution: string; coverage: Record<string, number>; capabilities: Record<string, boolean>; }
export interface OnlineInspection { coordinates: Record<string, string>; dimensions: Record<string, number>; time_range: [string | null, string | null]; temporal_resolution: string; coverage: Record<string, number>; variables: OnlineVariable[]; }
export interface OnlineMetadata extends OnlineDataset { inspection: OnlineInspection; }
export interface OnlineTimes { dataset_id: string; start: string | null; end: string | null; temporal_resolution: string; timestamps: string[]; }
export interface OnlinePointQuery { dataset_id: string; variable: string; timestamp: string; units: string; requested_lat: number; requested_lon: number; matched_lat: number; matched_lon: number; value: number | null; variable_key?: string; display_name?: string; latitude?: number; longitude?: number; matched_date?: string; date_matched?: string; requested_date?: string; date_requested?: string; units_display?: string; grid?: { lat_min: number; lat_max: number; lon_min: number; lon_max: number }; message?: string | null; provider?: string; source?: string; }

async function json<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Online API error ${response.status}`); }
  return response.json() as Promise<T>;
}
export const fetchOnlineDatasets = () => json<{ datasets: OnlineDataset[] }>(`${API_BASE}/datasets`);
export const fetchOnlineMetadata = (id: string) => json<OnlineMetadata>(`${API_BASE}/datasets/${encodeURIComponent(id)}/metadata`);
export const fetchOnlineTimes = (id: string) => json<OnlineTimes>(`${API_BASE}/datasets/${encodeURIComponent(id)}/times`);

export interface OnlineFrameResponse { blobUrl: string; status: number; blobSize: number; blobType: string; matchedTime: string; matchedDate: string; datasetId: string; variable: string; bounds: { west: number; south: number; east: number; north: number }; width?: number; height?: number; }
export async function fetchOnlineFrame(datasetId: string, variable: string, time: string, options: { colormap?: string; vmin?: number; vmax?: number; maxPixels?: number } = {}, signal?: AbortSignal): Promise<OnlineFrameResponse> {
  const params = new URLSearchParams({ dataset_id: datasetId, variable, time, lat_min: '-90', lat_max: '90', lon_min: '-180', lon_max: '180', max_pixels: String(options.maxPixels ?? 1536), colormap: options.colormap ?? 'viridis' });
  if (Number.isFinite(options.vmin)) params.set('vmin', String(options.vmin));
  if (Number.isFinite(options.vmax)) params.set('vmax', String(options.vmax));
  const response = await fetch(`${API_BASE}/data?${params}`, { signal });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Frame request failed (${response.status})`); }
  const numberHeader = (name: string, fallback: number) => Number(response.headers.get(name) ?? fallback);
  const blob = await response.blob();
  const matchedTime = response.headers.get('X-Date-Matched') || response.headers.get('X-Time-Matched') || time;
  return {
    blobUrl: URL.createObjectURL(blob), status: response.status, blobSize: blob.size, blobType: blob.type, matchedTime, matchedDate: matchedTime,
    datasetId: response.headers.get('X-Dataset-Id') || datasetId, variable: response.headers.get('X-Variable') || variable,
    bounds: { west: numberHeader('X-Bounds-West', -180), south: numberHeader('X-Bounds-South', -90), east: numberHeader('X-Bounds-East', 180), north: numberHeader('X-Bounds-North', 90) },
    width: Number(response.headers.get('X-Raster-Width') || 0) || undefined, height: Number(response.headers.get('X-Raster-Height') || 0) || undefined,
  };
}
export function fetchOnlinePoint(datasetId: string, variable: string, time: string, lon: number, lat: number) {
  return json<OnlinePointQuery>(`${API_BASE}/point?${new URLSearchParams({ dataset_id: datasetId, variable, time, lon: String(lon), lat: String(lat) })}`);
}
