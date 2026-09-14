"""
JSON / GeoJSON Scientific Reader for YARA.
Parses GeoJSON observations and structured JSON scientific time series.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import json
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


class JSONReader(BaseScientificReader):
    """Reader for GeoJSON and structured JSON scientific observation data."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        super().__init__(file_path, dataset_id)
        self._parsed_records: Optional[List[Dict]] = None

    def _load_records(self) -> List[Dict]:
        if self._parsed_records is None:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            records = []
            if isinstance(data, dict) and data.get("type") == "FeatureCollection":
                # GeoJSON
                features = data.get("features", [])
                for feat in features:
                    geom = feat.get("geometry", {})
                    props = feat.get("properties", {})
                    coords = geom.get("coordinates", [])
                    if geom.get("type") == "Point" and len(coords) >= 2:
                        rec = dict(props)
                        rec["lon"] = float(coords[0])
                        rec["lat"] = float(coords[1])
                        records.append(rec)
            elif isinstance(data, list):
                # List of observation dicts
                records = data
            elif isinstance(data, dict) and "observations" in data:
                records = data["observations"]

            if not records:
                raise ValueError(f"JSON dataset has no identifiable observations or Point features: {self.file_path.name}")

            self._parsed_records = records
        return self._parsed_records

    def inspect(self) -> DatasetInfo:
        records = self._load_records()
        df = pd.DataFrame(records)

        # Look for lat/lon columns
        cols_lower = {c.lower(): c for c in df.columns}
        lat_col = cols_lower.get("lat") or cols_lower.get("latitude") or cols_lower.get("y")
        lon_col = cols_lower.get("lon") or cols_lower.get("longitude") or cols_lower.get("x")
        time_col = cols_lower.get("time") or cols_lower.get("timestamp") or cols_lower.get("date")

        if not lat_col or not lon_col:
            raise ValueError(f"JSON records must contain latitude/longitude fields: {self.file_path.name}")

        lats = df[lat_col].astype(float).values
        lons = df[lon_col].astype(float).values

        extent = SpatialExtent(
            west=float(np.min(lons)),
            south=float(np.min(lats)),
            east=float(np.max(lons)),
            north=float(np.max(lats)),
            is_global=False
        )

        time_axis = TimeAxisInfo(timestamps=["single"], resolution="single", count=1)
        if time_col and time_col in df:
            unique_times = df[time_col].dropna().unique()
            time_axis = analyze_time_axis(unique_times, dim_name=time_col)

        variables_info = {}
        for col in df.columns:
            if col in (lat_col, lon_col, time_col):
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
            format=DatasetFormat.JSON,
            source_type="local",
            file_path=str(self.file_path.resolve()),
            file_size_bytes=file_size,
            dimensions={"records": len(df)},
            coordinates={},
            variables=variables_info,
            default_variable=list(variables_info.keys())[0] if variables_info else None,
            time_axis=time_axis,
            spatial_extent=extent,
            metadata={"num_features": len(records)}
        )
        return self._dataset_info

    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        if not self._dataset_info:
            self.inspect()

        records = self._load_records()
        df = pd.DataFrame(records)

        cols_lower = {c.lower(): c for c in df.columns}
        lat_col = cols_lower.get("lat") or cols_lower.get("latitude")
        lon_col = cols_lower.get("lon") or cols_lower.get("longitude")
        time_col = cols_lower.get("time") or cols_lower.get("timestamp")

        target_var = var_name or self._dataset_info.default_variable
        if not target_var or target_var not in df.columns:
            raise ValueError(f"Variable '{target_var}' not found in JSON data.")

        lats = df[lat_col].values.astype(np.float32)
        lons = df[lon_col].values.astype(np.float32)
        vals = df[target_var].values.astype(np.float32)

        # Interpolate onto a 2D raster grid for Cesium single-tile rendering
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
            timestamp=None,
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
