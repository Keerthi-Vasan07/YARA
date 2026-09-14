/**
 * API client for SST data backend.
 */

const API_BASE = '/api';

export interface TimeRange {
  total_months: number;
  start_date: string;
  end_date: string;
  available_dates: string[];
  years: Record<string, number[]>; // { "2020": [1,2,3,...12], "2021": [...] }
}

export async function fetchTimeRange(): Promise<TimeRange> {
  const response = await fetch(`${API_BASE}/time-range`);
  if (!response.ok) {
    throw new Error(`Failed to fetch time range: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchTimeRangeForVariable(variable: string): Promise<TimeRange & { variable: string }> {
  const response = await fetch(`${API_BASE}/time-range/${variable}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch time range for ${variable}: ${response.statusText}`);
  }
  return response.json();
}

export interface SSTPointQuery {
  date: string;
  lon: number;
  lat: number;
  sst: number | null;
  unit: string;
  message?: string;
  source?: string;
  dataset?: string;
}

export async function fetchSSTPoint(date: string, lon: number, lat: number): Promise<SSTPointQuery> {
  const response = await fetch(
    `${API_BASE}/sst/point?date=${encodeURIComponent(date)}&lon=${lon}&lat=${lat}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch SST point: ${response.statusText}`);
  }
  return response.json();
}

// Generic variable point query (for SIC, SLA, etc.)
export interface VariablePointQuery {
  date: string;
  variable: string;
  lon: number;
  lat: number;
  value: number | null;
  unit: string;
  name?: string;
  message?: string;
  source?: string;
  dataset?: string;
}

export async function fetchVariablePoint(
  variable: string,
  date: string,
  lon: number,
  lat: number
): Promise<VariablePointQuery> {
  const response = await fetch(
    `${API_BASE}/${variable}/point?date=${encodeURIComponent(date)}&lon=${lon}&lat=${lat}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch ${variable.toUpperCase()} point: ${response.statusText}`);
  }
  return response.json();
}

export interface TimeseriesPoint {
  date: string;
  value: number;
  anomaly?: number | null;
}

export interface MonthlyClimatology {
  month: number;
  mean: number | null;
  std?: number;
  p10?: number;
  p50?: number;
  p90?: number;
}

export interface SSTTimeseriesResponse {
  location: {
    lon: number;
    lat: number;
  };
  timeseries: TimeseriesPoint[];
  count: number;
  stats: {
    min: number;
    max: number;
    mean: number;
  } | null;
  climatology?: {
    mean: number | null;
    std: number | null;
  };
  percentiles?: {
    p10: number | null;
    p50: number | null;
    p90: number | null;
  };
  monthly_climatology?: MonthlyClimatology[];
  trend?: number | null;
}

// Extended Zarr timeseries response
export interface ZarrTimeseriesResponse {
  location: {
    lon: number;
    lat: number;
    requested?: { lon: number; lat: number };
  };
  climatology: {
    mean: number | null;
    std: number | null;
  };
  percentiles?: {
    p10: number | null;
    p50: number | null;
    p90: number | null;
  };
  monthly_climatology?: MonthlyClimatology[];
  trend?: number | null;
  timeseries: TimeseriesPoint[];
  count: number;
}

export async function fetchSSTTimeseries(lon: number, lat: number, limit: number = 24): Promise<SSTTimeseriesResponse> {
  const response = await fetch(
    `${API_BASE}/sst/timeseries?lon=${lon}&lat=${lat}&limit=${limit}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch SST timeseries: ${response.statusText}`);
  }
  return response.json();
}

// Fetch enhanced time series from Zarr store (includes climatology, percentiles, trends)
export async function fetchZarrTimeseries(variable: string, lon: number, lat: number): Promise<ZarrTimeseriesResponse> {
  const response = await fetch(
    `${API_BASE}/zarr/${variable}/timeseries?lon=${lon}&lat=${lat}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch ${variable} timeseries: ${response.statusText}`);
  }
  return response.json();
}

// Climatology endpoint response
export interface ClimatologyResponse {
  location: {
    lon: number;
    lat: number;
  };
  overall: {
    mean: number | null;
    std: number | null;
  };
  month?: number;
  monthly?: MonthlyClimatology[] | MonthlyClimatology;
}

export async function fetchClimatology(variable: string, lon: number, lat: number, month?: number): Promise<ClimatologyResponse> {
  const monthParam = month ? `&month=${month}` : '';
  const response = await fetch(
    `${API_BASE}/zarr/${variable}/climatology?lon=${lon}&lat=${lat}${monthParam}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch ${variable} climatology: ${response.statusText}`);
  }
  return response.json();
}

// Percentiles endpoint response  
export interface PercentilesResponse {
  location: {
    lon: number;
    lat: number;
  };
  percentiles?: {
    p10: number | null;
    p50: number | null;
    p90: number | null;
  };
  current?: {
    date: string;
    value: number;
    percentile_rank: number;
    monthly_percentiles?: {
      month: number;
      p10: number | null;
      p50: number | null;
      p90: number | null;
    };
  };
}

export async function fetchPercentiles(variable: string, lon: number, lat: number, date?: string): Promise<PercentilesResponse> {
  const dateParam = date ? `&date=${encodeURIComponent(date)}` : '';
  const response = await fetch(
    `${API_BASE}/zarr/${variable}/percentiles?lon=${lon}&lat=${lat}${dateParam}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch ${variable} percentiles: ${response.statusText}`);
  }
  return response.json();
}

// Layer info types
export interface LayerInfo {
  variable: string;
  title: string;
  source: string;
  created: string | null;
  global_stats: {
    min?: number;
    max?: number;
    mean?: number;
    std?: number;
    count?: number;
  };
  arrays: Record<string, {
    shape: number[];
    dtype: string;
    chunks: number[] | null;
    attrs?: Record<string, unknown>;
  }>;
  bounds: {
    lat: [number, number];
    lon: [number, number];
  };
  time_range: {
    start: string | null;
    end: string | null;
    count: number;
  };
}

export async function fetchLayerInfo(variable: string): Promise<LayerInfo> {
  const response = await fetch(`${API_BASE}/zarr/${variable}/info`);
  if (!response.ok) {
    throw new Error(`Failed to fetch layer info: ${response.statusText}`);
  }
  return response.json();
}

// Download URL helpers
export function getLayerDownloadUrl(date: string): string {
  return `${API_BASE}/sst/image/${date}.png`;
}

export function getLayerGeoTIFFUrl(date: string): string {
  // Returns path to pre-computed COG file
  return `/server/products/sst/${date}.tif`;
}
