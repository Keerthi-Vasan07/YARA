// ── Ocean variable identifiers ───────────────────────────────────────────────
// GLORYS/Copernicus variables
export type GlorysVariable = "thetao" | "so" | "mlotst" | "ohc_0_700m" | "chl" | "composite";
// OPeNDAP-sourced derived variables
export type OpendapVariable = "temperature" | "salinity" | "current_speed" | "sound_speed" | "density";
// Combined union used across the app
export type OceanVariable = GlorysVariable | OpendapVariable;

// Render mode for multi-color volume shader
export type VolumeRenderMode = "temperature" | "salinity" | "chlorophyll" | "composite";

/** Returns true if the variable is served from the new OPeNDAP endpoint. */
export function isOpendapVariable(v: OceanVariable): v is OpendapVariable {
  return ["temperature", "salinity", "current_speed", "sound_speed", "density"].includes(v);
}

// ── Per-variable display metadata (mirrors VARIABLE_META in glorys_service.py) ──
export interface VariableMeta {
  variable: OceanVariable;
  unit: string;
  label: string;
  default_range: [number, number];
  is_2d: boolean;
  climate_only: boolean; // true for so, mlotst, ohc_0_700m (Dec 2004 only)
}

export const VARIABLE_CATALOGUE: VariableMeta[] = [
  // ── GLORYS / Copernicus variables ─────────────────────────────────────────
  {
    variable:      "thetao",
    unit:          "°C",
    label:         "Potential Temperature",
    default_range: [-2, 35],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "so",
    unit:          "PSU",
    label:         "Salinity",
    default_range: [30, 40],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "chl",
    unit:          "mg/m³",
    label:         "Chlorophyll-a",
    default_range: [0, 2],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "composite",
    unit:          "Multi",
    label:         "3D Multi-Variable Composite",
    default_range: [0, 1],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "mlotst",
    unit:          "m",
    label:         "Mixed Layer Thickness",
    default_range: [0, 200],
    is_2d:         true,
    climate_only:  true,
  },
  {
    variable:      "ohc_0_700m",
    unit:          "J/m\u00b2",
    label:         "Ocean Heat Content (0\u2013700m)",
    default_range: [0, 4e9],
    is_2d:         true,
    climate_only:  true,
  },
  // ── OPeNDAP-sourced derived variables ─────────────────────────────────────
  {
    variable:      "temperature",
    unit:          "°C",
    label:         "Potential Temperature (OPeNDAP)",
    default_range: [-2, 35],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "salinity",
    unit:          "PSU",
    label:         "Practical Salinity (OPeNDAP)",
    default_range: [30, 40],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "current_speed",
    unit:          "m/s",
    label:         "Current Speed |u,v|",
    default_range: [0, 1.5],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "sound_speed",
    unit:          "m/s",
    label:         "Sound Speed (Mackenzie 1981)",
    default_range: [1450, 1550],
    is_2d:         false,
    climate_only:  false,
  },
  {
    variable:      "density",
    unit:          "kg/m\u00b3",
    label:         "Density Anomaly (\u03c3\u03b8)",
    default_range: [21, 30],
    is_2d:         false,
    climate_only:  false,
  },
];

// ── API response types ────────────────────────────────────────────────────────

export interface TimeRangeResponse {
  dataset: string;
  product: string;
  variable: string;
  start: string; // YYYY-MM-DD
  end: string;   // YYYY-MM-DD
  resolution: string;
  mode: "remote" | "local";
  climate_only?: boolean;
}

export interface DateMetadata {
  date: string;
  dataset: string;
  variable: string;
  units: string;
  label?: string;
  is_2d?: boolean;
  default_range?: [number, number];
  longitude: { min: number; max: number; count: number };
  latitude: { min: number; max: number; count: number };
  depth: { min: number; max: number; count: number; values: number[] };
  mode: string;
}

export interface VolumeParams {
  date: string;
  variable?: OceanVariable;
  lonMin?: number;
  lonMax?: number;
  latMin?: number;
  latMax?: number;
  depthMin?: number;
  depthMax?: number;
  lod?: number; // 0=Coarse, 1=Balanced, 2=Fine
  stride_lat?: number;
  stride_lon?: number;
  stride_depth?: number;
  downsample_stride?: number; // for OPeNDAP subsurface endpoint
}

export interface VolumeMeta {
  dataset?: string;
  variable: string;
  units: string;
  label?: string;        // human-readable variable label (new)
  is_2d?: boolean;       // true for mlotst, ohc_0_700m (new)
  is_multi_channel?: boolean;
  channel_count?: number;
  channels?: string[];
  date?: string;
  time?: string;
  time_index?: number;
  mode?: string;
  lod?: number;
  strides?: { lat: number; lon: number; depth: number };
  shape: { depth: number; lat: number; lon: number };
  depth: number[];
  latitude: number[];
  longitude: number[];
  depth_min: number;
  depth_max: number;
  latitude_min: number;
  latitude_max: number;
  longitude_min: number;
  longitude_max: number;
  // Generic value range (works for all variables)
  value_min?: number;
  value_max?: number;
  // Backward-compat aliases for thetao (always equal to value_min/max)
  temperature_min: number;
  temperature_max: number;
  stride_lat?: number;
  stride_lon?: number;
  dtype?: string;
  byte_length: number;
  payload_hash?: string;  // SHA-256 fingerprint (first 16 hex chars) of raw float32 bytes
  nan_sentinel?: string;
  vertical_exaggeration_default?: number;
}

export interface VolumeData {
  meta: VolumeMeta;
  float32: Float32Array; // decoded, shape depth*lat*lon, row-major
}

export interface LayerSummary {
  sliceIndex: number;
  totalSlices: number;
  depthStartM: number;
  depthEndM: number;
  sliceDepthM: number;
  avgTemperature?: number | null;
  avgSalinity?: number | null;
  avgChlorophyll?: number | null;
  minTemperature?: number | null;
  maxTemperature?: number | null;
  validVoxelCount: number;
}

export interface ProbePoint {
  lon: number;
  lat: number;
  depth: number;
  localU: number; // [0,1] lon fraction
  localV: number; // [0,1] lat fraction
  localW: number; // [0,1] depth fraction (0=shallow, 1=deep)
  worldPos: { x: number; y: number; z: number };
  voxelValue?: number | null;
  temperature?: number | null;
  salinity?: number | null;
  chlorophyll?: number | null;
  layerSummary?: LayerSummary | null;
  featureName?: string;
  isFeaturePin?: boolean;
  is_land?: boolean;
  message?: string;
}


export interface ProfileResponse {
  date?: string;
  requested_latitude: number;
  requested_longitude: number;
  matched_latitude: number;
  matched_longitude: number;
  lat_index: number;
  lon_index: number;
  depth: number[];
  temperature: (number | null)[];
  variable?: string;
  mode?: string;
  is_2d?: boolean;
  message?: string; // set when profile is not applicable (2D variables)
}

export interface GlorysInfo {
  variable: string;
  long_name: string;
  units: string;
  dimensions: string[];
  shape: number[];
  depth: number[];
  n_depth: number;
  latitude_min: number;
  latitude_max: number;
  longitude_min: number;
  longitude_max: number;
  n_latitude: number;
  n_longitude: number;
  temperature_min: number;
  temperature_max: number;
  available_time: string[];
  n_time: number;
  mode: string;
}

export interface GlorysHealth {
  status: string;
  mode: string;
  dataset_id: string;
  product_id: string;
  variable: string;
  supported_variables?: string[];
  env_file_found: boolean;
  credentials_configured: boolean;
  copernicus_credentials_configured?: boolean;
  remote_configured: boolean;
  local_fixture_available: boolean;
  climate_fixture_available?: boolean;
  cache_entries: number;
}

// ── 3D Subsurface Column Profiling Types ─────────────────────────────────────
export type ProbeVariable = "temperature" | "salinity" | "chlorophyll";

export interface VerticalColumnPoint {
  depth_m: number;
  temperature: number;
  salinity: number;
  chlorophyll: number;
}

export interface VerticalColumnResponse {
  lat: number;
  lon: number;
  timestamp: string;
  source: string;
  max_depth_m: number;
  profile: VerticalColumnPoint[];
  is_land?: boolean;
  message?: string;
}

export interface PointProbeResponse {
  is_land: boolean;
  status: string;
  lat: number;
  lon: number;
  depth: number;
  temperature: number | null;
  salinity: number | null;
  chlorophyll: number | null;
  profile?: VerticalColumnPoint[];
  message?: string;
}

