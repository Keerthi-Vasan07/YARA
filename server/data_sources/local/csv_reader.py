"""
CSV Scientific Reader for YARA.
Parses tabular scientific observations, identifies lat/lon/time/data columns,
and generates raster grids for visualization.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import numpy as np
import pandas as pd
from scipy.interpolate import griddata

from .base_reader import BaseScientificReader
from .common_model import (
    DatasetFormat,
    DatasetInfo,
    VariableInfo,
    VariableType,
    CoordinateInfo,
    TimeAxisInfo,
    SpatialExtent,
    SliceData,
    PointQueryResponse
)
from .coordinate_utils import normalize_grid_to_wgs84, find_nearest_cell
from .time_utils import analyze_time_axis, to_iso_string

LAT_COLS = ["lat", "latitude", "y", "lats"]
LON_COLS = ["lon", "longitude", "x", "long", "lons"]
TIME_COLS = ["time", "timestamp", "datetime", "date"]


class CSVReader(BaseScientificReader):
    """Reader for scientific tabular CSV datasets."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        super().__init__(file_path, dataset_id)
        self._df: Optional[pd.DataFrame] = None
        self._lat_col: Optional[str] = None
        self._lon_col: Optional[str] = None
        self._time_col: Optional[str] = None

    def _read_df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = pd.read_csv(self.file_path)
            # Find coordinate columns
            cols_lower = {c.lower().strip(): c for c in self._df.columns}
            for candidate in LAT_COLS:
                if candidate in cols_lower:
                    self._lat_col = cols_lower[candidate]
                    break
            for candidate in LON_COLS:
                if candidate in cols_lower:
                    self._lon_col = cols_lower[candidate]
                    break
            for candidate in TIME_COLS:
                if candidate in cols_lower:
                    self._time_col = cols_lower[candidate]
                    break

            if not self._lat_col or not self._lon_col:
                raise ValueError(f"CSV missing recognizable latitude/longitude columns: {self.file_path.name}")
        return self._df

    def inspect(self) -> DatasetInfo:
        df = self._read_df()
        lats = df[self._lat_col].dropna().values.astype(float)
        lons = df[self._lon_col].dropna().values.astype(float)

        west = float(np.min(lons))
        east = float(np.max(lons))
        south = float(np.min(lats))
        north = float(np.max(lats))

        extent = SpatialExtent(
            west=west,
            south=south,
            east=east,
            north=north,
            is_global=(east - west >= 355.0 and north - south >= 160.0)
        )

        # Time axis
        if self._time_col:
            unique_times = df[self._time_col].dropna().unique()
            time_axis = analyze_time_axis(unique_times, dim_name=self._time_col)
        else:
            time_axis = TimeAxisInfo(timestamps=["single"], resolution="single", count=1)

        # Variables: all numeric columns except lat/lon/time
        variables_info: Dict[str, VariableInfo] = {}
        for col in df.columns:
            if col in (self._lat_col, self._lon_col, self._time_col):
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                vals = df[col].dropna().values
                min_v = float(np.min(vals)) if len(vals) > 0 else 0.0
                max_v = float(np.max(vals)) if len(vals) > 0 else 1.0
                variables_info[col] = VariableInfo(
                    name=col,
                    long_name=col,
                    dimensions=["points"],
                    shape=[len(df)],
                    dtype=str(df[col].dtype),
                    var_type=VariableType.POINT_OBSERVATION,
                    min_val=min_v,
                    max_val=max_v,
                    aliases=[col]
                )

        file_size = 0
        try:
            file_size = self.file_path.stat().st_size
        except Exception:
            pass

        self._dataset_info = DatasetInfo(
            id=self.dataset_id,
            name=self.file_path.name,
            format=DatasetFormat.CSV,
            source_type="local",
            file_path=str(self.file_path.resolve()),
            file_size_bytes=file_size,
            dimensions={"rows": len(df)},
            coordinates={},
            variables=variables_info,
            default_variable=list(variables_info.keys())[0] if variables_info else None,
            time_axis=time_axis,
            spatial_extent=extent,
            metadata={"num_rows": len(df)}
        )
        return self._dataset_info

    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        if not self._dataset_info:
            self.inspect()

        df = self._read_df()
        target_var = var_name or self._dataset_info.default_variable
        if not target_var or target_var not in df.columns:
            raise ValueError(f"Variable '{target_var}' not found in CSV.")

        # Filter by time if multiple
        sub_df = df
        ts_str = None
        if self._time_col and self._dataset_info.time_axis.timestamps and len(self._dataset_info.time_axis.timestamps) > time_index:
            ts_str = self._dataset_info.time_axis.timestamps[time_index]
            # Match ISO date or raw date
            sub_df = df[df[self._time_col].astype(str).str.contains(ts_str[:10])]
            if sub_df.empty:
                sub_df = df

        lats = sub_df[self._lat_col].values.astype(np.float32)
        lons = sub_df[self._lon_col].values.astype(np.float32)
        vals = sub_df[target_var].values.astype(np.float32)

        # Check if already a regular grid
        u_lat = np.unique(lats)
        u_lon = np.unique(lons)
        if len(u_lat) * len(u_lon) == len(sub_df) and len(u_lat) > 1 and len(u_lon) > 1:
            # Pivot into 2D grid
            pivoted = sub_df.pivot(index=self._lat_col, columns=self._lon_col, values=target_var)
            raw_grid = pivoted.values.astype(np.float32)
            grid_lats = pivoted.index.values.astype(np.float32)
            grid_lons = pivoted.columns.values.astype(np.float32)
        else:
            # Interpolate onto a reasonable resolution raster grid (e.g. 180x360 or based on extent)
            n_y, n_x = 180, 360
            grid_lats = np.linspace(self._dataset_info.spatial_extent.north, self._dataset_info.spatial_extent.south, n_y, dtype=np.float32)
            grid_lons = np.linspace(self._dataset_info.spatial_extent.west, self._dataset_info.spatial_extent.east, n_x, dtype=np.float32)
            gx, gy = np.meshgrid(grid_lons, grid_lats)
            points = np.column_stack((lons, lats))
            raw_grid = griddata(points, vals, (gx, gy), method="linear", fill_value=np.nan).astype(np.float32)

        norm_data, norm_lat, norm_lon, extent = normalize_grid_to_wgs84(
            raw_grid, grid_lats, grid_lons
        )

        mask = np.isnan(norm_data)
        valid = norm_data[~mask]
        min_v = float(np.min(valid)) if len(valid) > 0 else 0.0
        max_v = float(np.max(valid)) if len(valid) > 0 else 1.0

        return SliceData(
            data=norm_data,
            lat_coords=norm_lat,
            lon_coords=norm_lon,
            extent=extent,
            variable_name=target_var,
            timestamp=ts_str,
            time_index=time_index,
            units=None,
            min_val=min_v,
            max_val=max_v,
            mask=mask
        )

    def get_point_value(
        self,
        lat: float,
        lon: float,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> PointQueryResponse:
        frame = self.read_frame(var_name=var_name, time_index=time_index)
        y_idx, x_idx, m_lat, m_lon = find_nearest_cell(
            lat, lon, frame.lat_coords, frame.lon_coords
        )
        val = frame.data[y_idx, x_idx]
        is_valid = bool(np.isfinite(val) and not frame.mask[y_idx, x_idx])

        return PointQueryResponse(
            dataset_id=self.dataset_id,
            variable=frame.variable_name,
            units=frame.units,
            requested_lat=lat,
            requested_lon=lon,
            matched_lat=m_lat,
            matched_lon=m_lon,
            grid_index_y=y_idx,
            grid_index_x=x_idx,
            value=float(val) if is_valid else None,
            is_valid=is_valid,
            timestamp=frame.timestamp,
            time_index=time_index
        )
