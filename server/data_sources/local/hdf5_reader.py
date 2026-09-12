"""
HDF5 Scientific Reader for YARA.
Navigates groups and datasets using h5py with multidimensional coordinate extraction.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple, Any
import numpy as np
import h5py

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
    PointQueryResponse,
    GridCellBounds
)
from .coordinate_utils import (
    normalize_grid_to_wgs84,
    find_nearest_cell,
    compute_cell_bounds,
)
from .variable_detection import is_coordinate_or_metadata_var, pick_default_variable

LAT_KEYS = ["lat", "latitude", "nav_lat", "lats"]
LON_KEYS = ["lon", "longitude", "nav_lon", "lons"]


class HDF5Reader(BaseScientificReader):
    """Reader for HDF5 scientific datasets."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        super().__init__(file_path, dataset_id)
        self._f: Optional[h5py.File] = None
        self._lat_path: Optional[str] = None
        self._lon_path: Optional[str] = None

    def _open(self) -> h5py.File:
        if self._f is None:
            self._f = h5py.File(str(self.file_path), "r")
        return self._f

    def _find_datasets(self, group: h5py.Group, prefix: str = "") -> Dict[str, h5py.Dataset]:
        results = {}
        for k in group.keys():
            item = group[k]
            path = f"{prefix}/{k}" if prefix else k
            if isinstance(item, h5py.Dataset):
                results[path] = item
            elif isinstance(item, h5py.Group):
                results.update(self._find_datasets(item, path))
        return results

    def inspect(self) -> DatasetInfo:
        f = self._open()
        datasets = self._find_datasets(f)

        # Locate coordinates
        for path, ds in datasets.items():
            name_lower = path.split("/")[-1].lower()
            if not self._lat_path and name_lower in LAT_KEYS:
                self._lat_path = path
            if not self._lon_path and name_lower in LON_KEYS:
                self._lon_path = path

        if not self._lat_path or not self._lon_path:
            # Look for 2D/1D datasets with lat/lon in name
            for path, ds in datasets.items():
                if "lat" in path.lower() and not self._lat_path:
                    self._lat_path = path
                if "lon" in path.lower() and not self._lon_path:
                    self._lon_path = path

        if not self._lat_path or not self._lon_path:
            raise ValueError(f"Could not automatically locate latitude/longitude arrays in HDF5: {self.file_path.name}")

        lat_arr = np.asarray(f[self._lat_path][()], dtype=np.float32).ravel()
        lon_arr = np.asarray(f[self._lon_path][()], dtype=np.float32).ravel()

        variables_info: Dict[str, VariableInfo] = {}
        for path, ds in datasets.items():
            if path in (self._lat_path, self._lon_path):
                continue
            if is_coordinate_or_metadata_var(path.split("/")[-1]):
                continue
            if ds.ndim < 2:
                continue

            var_name = path.replace("/", "_")
            shape = list(ds.shape)
            fill_val = ds.attrs.get("_FillValue") or ds.attrs.get("missing_value")

            variables_info[var_name] = VariableInfo(
                name=var_name,
                standard_name=str(ds.attrs.get("standard_name", "")),
                long_name=str(ds.attrs.get("long_name", path)),
                units=str(ds.attrs.get("units", "")),
                dimensions=[f"dim_{i}" for i in range(len(shape))],
                shape=shape,
                dtype=str(ds.dtype),
                var_type=VariableType.SCALAR_GRID,
                fill_value=float(fill_val) if fill_val is not None else None,
                aliases=[path.split("/")[-1]]
            )

        data_sample = np.zeros((len(lat_arr), len(lon_arr)), dtype=np.float32)
        _, _, _, extent = normalize_grid_to_wgs84(data_sample, lat_arr, lon_arr)
        default_var = pick_default_variable(variables_info)

        file_size = 0
        try:
            file_size = self.file_path.stat().st_size
        except Exception:
            pass

        self._dataset_info = DatasetInfo(
            id=self.dataset_id,
            name=self.file_path.name,
            format=DatasetFormat.HDF5,
            source_type="local",
            file_path=str(self.file_path.resolve()),
            file_size_bytes=file_size,
            dimensions={"lat": len(lat_arr), "lon": len(lon_arr)},
            coordinates={},
            variables=variables_info,
            default_variable=default_var,
            time_axis=TimeAxisInfo(timestamps=["static"], resolution="single", count=1),
            spatial_extent=extent,
            metadata={"num_datasets": len(datasets)}
        )
        return self._dataset_info

    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        if not self._dataset_info:
            self.inspect()

        f = self._open()
        target_var = var_name or self._dataset_info.default_variable
        # Resolve path
        ds_path = target_var.replace("_", "/")
        if ds_path not in f:
            # Search by name
            for k in self._dataset_info.variables.keys():
                if k == target_var:
                    ds_path = k.replace("_", "/")
                    break

        dset = f.get(ds_path)
        if dset is None:
            # Fallback search
            for p in f:
                if target_var in p:
                    dset = f[p]
                    break

        if dset is None:
            raise ValueError(f"HDF5 dataset '{target_var}' not found.")

        # Slice 2D
        raw_data = np.asarray(dset[()], dtype=np.float32)
        while raw_data.ndim > 2:
            raw_data = raw_data[0]

        lat_arr = np.asarray(f[self._lat_path][()], dtype=np.float32).ravel()
        lon_arr = np.asarray(f[self._lon_path][()], dtype=np.float32).ravel()

        norm_data, norm_lat, norm_lon, extent = normalize_grid_to_wgs84(
            raw_data, lat_arr, lon_arr
        )

        mask = np.isnan(norm_data)
        valid = norm_data[~mask]
        min_val = float(np.min(valid)) if len(valid) > 0 else 0.0
        max_val = float(np.max(valid)) if len(valid) > 0 else 1.0

        return SliceData(
            data=norm_data,
            lat_coords=norm_lat,
            lon_coords=norm_lon,
            extent=extent,
            variable_name=target_var,
            timestamp=None,
            time_index=0,
            units=None,
            min_val=min_val,
            max_val=max_val,
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
        south, north, west, east = compute_cell_bounds(y_idx, x_idx, frame.lat_coords, frame.lon_coords)

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
            time_index=time_index,
            cell_bounds=GridCellBounds(south=south, north=north, west=west, east=east)
        )

    def close(self):
        if self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None
