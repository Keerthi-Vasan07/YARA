"""
First-Class Zarr Scientific Reader for YARA.
Supports local Zarr arrays and datasets with chunked lazy loading.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import numpy as np
import xarray as xr
import zarr

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
from .time_utils import analyze_time_axis
from .variable_detection import (
    is_coordinate_or_metadata_var,
    match_variable_aliases,
    pick_default_variable
)

LAT_NAMES = ["lat", "latitude", "lats", "y", "nav_lat", "lat_rho"]
LON_NAMES = ["lon", "longitude", "lons", "x", "nav_lon", "lon_rho"]
TIME_NAMES = ["time", "times", "t", "datetime", "date"]
DEPTH_NAMES = ["zlev", "depth", "level", "z", "deptht", "lev"]


class ZarrReader(BaseScientificReader):
    """Reader for Zarr datasets using xarray and lazy chunked access."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        super().__init__(file_path, dataset_id)
        self._ds: Optional[xr.Dataset] = None
        self._lat_name: Optional[str] = None
        self._lon_name: Optional[str] = None
        self._time_name: Optional[str] = None
        self._depth_name: Optional[str] = None

    def _open_dataset(self) -> xr.Dataset:
        if self._ds is None:
            # Open with consolidated=False/True fallback
            try:
                self._ds = xr.open_zarr(str(self.file_path), consolidated=True)
            except Exception:
                self._ds = xr.open_zarr(str(self.file_path), consolidated=False)
        return self._ds

    def _detect_coord_names(self, ds: xr.Dataset):
        coords = list(ds.coords.keys()) + list(ds.sizes.keys())
        coords_lower = {c.lower(): c for c in coords}

        for candidate in LAT_NAMES:
            if candidate in coords_lower:
                self._lat_name = coords_lower[candidate]
                break

        for candidate in LON_NAMES:
            if candidate in coords_lower:
                self._lon_name = coords_lower[candidate]
                break

        for candidate in TIME_NAMES:
            if candidate in coords_lower:
                self._time_name = coords_lower[candidate]
                break

        for candidate in DEPTH_NAMES:
            if candidate in coords_lower:
                self._depth_name = coords_lower[candidate]
                break

    def inspect(self) -> DatasetInfo:
        ds = self._open_dataset()
        self._detect_coord_names(ds)

        if not self._lat_name or not self._lon_name:
            raise ValueError(f"Zarr dataset missing identifiable latitude/longitude coordinates: {self.file_path.name}")

        lat_arr = np.asarray(ds[self._lat_name].values)
        lon_arr = np.asarray(ds[self._lon_name].values)

        coordinates_info: Dict[str, CoordinateInfo] = {
            self._lat_name: CoordinateInfo(
                name=self._lat_name,
                axis="Y",
                dim_name=str(ds[self._lat_name].dims[0]) if ds[self._lat_name].dims else self._lat_name,
                size=int(lat_arr.size),
                min_val=float(np.nanmin(lat_arr)),
                max_val=float(np.nanmax(lat_arr)),
                units=str(ds[self._lat_name].attrs.get("units", "degrees_north")),
                is_ascending=bool(lat_arr[-1] > lat_arr[0]) if lat_arr.size > 1 else True
            ),
            self._lon_name: CoordinateInfo(
                name=self._lon_name,
                axis="X",
                dim_name=str(ds[self._lon_name].dims[0]) if ds[self._lon_name].dims else self._lon_name,
                size=int(lon_arr.size),
                min_val=float(np.nanmin(lon_arr)),
                max_val=float(np.nanmax(lon_arr)),
                units=str(ds[self._lon_name].attrs.get("units", "degrees_east")),
                is_ascending=bool(lon_arr[-1] > lon_arr[0]) if lon_arr.size > 1 else True
            )
        }

        # Time axis
        if self._time_name and self._time_name in ds:
            time_values = ds[self._time_name].values
            time_axis = analyze_time_axis(time_values, dim_name=self._time_name)
        else:
            time_axis = TimeAxisInfo(
                dim_name=None,
                timestamps=["single_step"],
                resolution="single",
                count=1
            )

        # Variables discovery
        variables_info: Dict[str, VariableInfo] = {}
        for var_name, da in ds.data_vars.items():
            if is_coordinate_or_metadata_var(var_name, da.attrs):
                continue

            dims = [str(d) for d in da.dims]
            std_name = da.attrs.get("standard_name")
            long_name = da.attrs.get("long_name")
            units = da.attrs.get("units")
            fill_val = da.attrs.get("_FillValue") or da.attrs.get("missing_value")

            has_lat = any(d in self._lat_name or self._lat_name in d for d in dims)
            has_lon = any(d in self._lon_name or self._lon_name in d for d in dims)
            var_type = VariableType.SCALAR_GRID if (has_lat and has_lon) else VariableType.UNKNOWN

            aliases = match_variable_aliases(var_name, std_name)

            try:
                sample_slice = da
                for d in dims:
                    if d == self._time_name:
                        sample_slice = sample_slice.isel({d: 0})
                    elif d == self._depth_name:
                        sample_slice = sample_slice.isel({d: 0})
                sample_vals = sample_slice.values
                valid_mask = np.isfinite(sample_vals)
                if fill_val is not None:
                    valid_mask = valid_mask & (sample_vals != fill_val)
                valid_vals = sample_vals[valid_mask]
                min_val = float(np.min(valid_vals)) if len(valid_vals) > 0 else 0.0
                max_val = float(np.max(valid_vals)) if len(valid_vals) > 0 else 1.0
            except Exception:
                min_val, max_val = 0.0, 35.0

            variables_info[var_name] = VariableInfo(
                name=var_name,
                standard_name=str(std_name) if std_name else None,
                long_name=str(long_name) if long_name else None,
                units=str(units) if units else None,
                dimensions=dims,
                shape=[int(s) for s in da.shape],
                dtype=str(da.dtype),
                var_type=var_type,
                min_val=min_val,
                max_val=max_val,
                fill_value=float(fill_val) if fill_val is not None else None,
                has_time=(self._time_name in dims),
                has_depth=(self._depth_name in dims if self._depth_name else False),
                aliases=aliases
            )

        data_sample = np.zeros((len(lat_arr), len(lon_arr)), dtype=np.float32)
        _, _, _, extent = normalize_grid_to_wgs84(data_sample, lat_arr, lon_arr)
        default_var = pick_default_variable(variables_info)

        # Calculate physical storage size for Zarr directory/files
        file_size = 0
        try:
            if self.file_path.is_dir():
                file_size = sum(f.stat().st_size for f in self.file_path.rglob('*') if f.is_file())
            elif self.file_path.is_file():
                file_size = self.file_path.stat().st_size
        except Exception:
            file_size = 0

        self._dataset_info = DatasetInfo(
            id=self.dataset_id,
            name=self.file_path.name,
            format=DatasetFormat.ZARR,
            source_type="local",
            file_path=str(self.file_path.resolve()),
            file_size_bytes=file_size,
            dimensions={str(k): int(v) for k, v in ds.sizes.items()},
            coordinates=coordinates_info,
            variables=variables_info,
            default_variable=default_var,
            time_axis=time_axis,
            spatial_extent=extent,
            metadata={str(k): str(v) for k, v in ds.attrs.items() if len(str(v)) < 1000}
        )

        return self._dataset_info

    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        if not self._dataset_info:
            self.inspect()

        ds = self._open_dataset()
        target_var = var_name or self._dataset_info.default_variable
        if not target_var or target_var not in ds.data_vars:
            raise ValueError(f"Variable '{target_var}' not found in Zarr dataset {self.file_path.name}")

        da = ds[target_var]
        indexer = {}
        if self._time_name and self._time_name in da.dims:
            max_t = da.sizes[self._time_name]
            idx = max(0, min(time_index, max_t - 1))
            indexer[self._time_name] = idx

        if self._depth_name and self._depth_name in da.dims:
            indexer[self._depth_name] = 0

        for d in da.dims:
            if d not in (self._lat_name, self._lon_name) and d not in indexer:
                indexer[d] = 0

        sliced = da.isel(indexer)
        raw_data = np.asarray(sliced.values, dtype=np.float32)
        raw_data = np.squeeze(raw_data)

        if raw_data.ndim != 2:
            raise ValueError(f"Expected 2D slice [lat, lon], got shape {raw_data.shape}")

        lat_arr = np.asarray(ds[self._lat_name].values)
        lon_arr = np.asarray(ds[self._lon_name].values)

        var_meta = self._dataset_info.variables.get(target_var)
        fill_val = var_meta.fill_value if var_meta else None
        if fill_val is not None:
            raw_data[raw_data == fill_val] = np.nan
        raw_data[~np.isfinite(raw_data)] = np.nan

        norm_data, norm_lat, norm_lon, extent = normalize_grid_to_wgs84(
            raw_data, lat_arr, lon_arr
        )

        mask = np.isnan(norm_data)
        valid_vals = norm_data[~mask]
        min_val = float(np.min(valid_vals)) if len(valid_vals) > 0 else 0.0
        max_val = float(np.max(valid_vals)) if len(valid_vals) > 0 else 1.0

        ts_str = None
        if self._dataset_info.time_axis.timestamps and 0 <= time_index < len(self._dataset_info.time_axis.timestamps):
            ts_str = self._dataset_info.time_axis.timestamps[time_index]

        return SliceData(
            data=norm_data,
            lat_coords=norm_lat,
            lon_coords=norm_lon,
            extent=extent,
            variable_name=target_var,
            timestamp=ts_str,
            time_index=time_index,
            units=var_meta.units if var_meta else None,
            min_val=min_val,
            max_val=max_val,
            fill_value=fill_val,
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

    def close(self):
        if self._ds is not None:
            try:
                self._ds.close()
            except Exception:
                pass
            self._ds = None
