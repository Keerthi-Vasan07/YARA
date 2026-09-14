/**
 * Scientific Dataset and Ingestion Types for YARA.
 */

export type DatasetFormat = 
  | 'netcdf'
  | 'zarr'
  | 'geotiff'
  | 'hdf5'
  | 'csv'
  | 'text_ascii'
  | 'json'
  | 'grib'
  | 'bufr'
  | 'unknown';

export type TemporalResolution = 
  | 'hourly'
  | 'sub_hourly'
  | '3_hourly'
  | 'daily'
  | 'monthly'
  | 'irregular'
  | 'single';

export interface SpatialExtent {
  west: number;
  south: number;
  east: number;
  north: number;
  is_global: boolean;
}

export interface CoordinateInfo {
  name: string;
  axis: string;
  dim_name: string;
  size: number;
  min_val?: number;
  max_val?: number;
  step?: number;
  units?: string;
  is_regular: boolean;
  is_ascending: boolean;
}

export interface TimeAxisInfo {
  dim_name?: string;
  timestamps: string[];
  resolution: TemporalResolution;
  step_seconds?: number;
  start_time?: string;
  end_time?: string;
  count: number;
}

export interface VariableInfo {
  name: string;
  standard_name?: string;
  long_name?: string;
  units?: string;
  dimensions: string[];
  shape: number[];
  dtype: string;
  var_type: string;
  min_val?: number;
  max_val?: number;
  fill_value?: number;
  has_time: boolean;
  has_depth: boolean;
  aliases: string[];
}

export interface DatasetInfo {
  id: string;
  name: string;
  format: DatasetFormat;
  source_type: string;
  file_path: string;
  file_size_bytes: number;
  dimensions: Record<string, number>;
  coordinates: Record<string, CoordinateInfo>;
  variables: Record<string, VariableInfo>;
  default_variable?: string;
  time_axis: TimeAxisInfo;
  spatial_extent: SpatialExtent;
  metadata: Record<string, any>;
  created_at?: string;
}

export interface ActiveModeResponse {
  mode: 'online' | 'local';
  active_dataset_id?: string | null;
  dataset?: DatasetInfo | null;
}

export interface LocalPointQueryResponse {
  dataset_id: string;
  variable: string;
  units?: string;
  requested_lat: number;
  requested_lon: number;
  matched_lat: number;
  matched_lon: number;
  grid_index_y: number;
  grid_index_x: number;
  cell_bounds?: SpatialExtent | null;
  value?: number | null;
  is_valid: boolean;
  timestamp?: string | null;
  time_index?: number | null;
}

export interface GradientStop { position: number; color: string }
export interface AnalysisOptions {
  mode: 'none' | 'exact' | 'range';
  exact_temperature: number;
  tolerance: number;
  range_min: number;
  range_max: number;
  flat_color: string;
  stops: GradientStop[] | null;
}
export interface FrameStyle {
  analysis?: AnalysisOptions;
  colormap?: string;
  minVal?: number;
  maxVal?: number;
}
export interface FrameStats {
  variable: string;
  units: string | null;
  timestamp: string | null;
  time_index: number;
  matching_cells: number;
  valid_cells: number;
  total_cells: number;
  matching_percent: number;
  min: number | null;
  max: number | null;
  mean: number | null;
  message: string | null;
}
export interface DatasetGrid {
  kind: 'native' | 'reference';
  latitude_resolution: number | null;
  longitude_resolution: number | null;
  extent: SpatialExtent;
  latitudes: number[];
  longitudes: number[];
}

