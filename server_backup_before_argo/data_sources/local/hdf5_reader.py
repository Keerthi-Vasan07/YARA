"""HDF5 adapter: preserve native values, units, dimension scales and real time."""
from typing import Optional
import h5py
import numpy as np
from netCDF4 import num2date
from .base_reader import BaseScientificReader
from .common_model import DatasetFormat, DatasetInfo, VariableInfo, TimeAxisInfo, SliceData, PointQueryResponse
from .coordinate_utils import normalize_grid_to_wgs84, find_nearest_cell, cell_bounds
from .time_utils import analyze_time_axis
from .variable_detection import is_coordinate_or_metadata_var, pick_default_variable


def text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


class HDF5Reader(BaseScientificReader):
    def __init__(self, file_path, dataset_id=None):
        super().__init__(file_path, dataset_id)
        self._f = None
        self._paths = {}
        self._axes = {}
        self._time_axis = TimeAxisInfo(count=1)

    def _open(self):
        if self._f is None:
            self._f = h5py.File(str(self.file_path), "r")
        return self._f

    def _find_datasets(self, group):
        result = {}
        group.visititems(lambda name, obj: result.update({name: obj}) if isinstance(obj, h5py.Dataset) else None)
        return result

    def _axis(self, ds, path):
        if not path:
            return None
        basename = path.split("/")[-1].lower()
        for i, dim in enumerate(ds.dims):
            if dim.label.lower() == basename or any(scale.name.lstrip("/") == path for scale in dim.values()):
                return i
        return None

    def inspect(self):
        f = self._open()
        datasets = self._find_datasets(f)
        def locate(names, standard):
            return next((p for p, d in datasets.items() if p.split("/")[-1].lower() in names
                         or text(d.attrs.get("standard_name", "")).lower() == standard), None)
        self._lat_path = locate({"lat", "latitude", "nav_lat", "lats"}, "latitude")
        self._lon_path = locate({"lon", "longitude", "nav_lon", "lons"}, "longitude")
        self._time_path = locate({"time", "datetime", "times"}, "time")
        if not self._lat_path or not self._lon_path:
            raise ValueError("HDF5 file lacks identifiable latitude/longitude coordinates")
        lat, lon = np.asarray(f[self._lat_path][()]), np.asarray(f[self._lon_path][()])
        if lat.ndim != 1 or lon.ndim != 1:
            raise ValueError("HDF5 reader requires one-dimensional rectilinear coordinates")
        if self._time_path:
            time = f[self._time_path]
            values = np.atleast_1d(time[()])
            units = text(time.attrs.get("units", ""))
            if "since" in units:
                values = num2date(values, units, calendar=text(time.attrs.get("calendar", "standard")))
            elif values.dtype.kind in "SUO":
                values = [text(v) for v in values]
            else:
                # No epoch may be inferred from numeric values without metadata.
                values = []
            if len(values):
                self._time_axis = analyze_time_axis(values, self._time_path)
        variables = {}
        max_frames = 1
        for path, ds in datasets.items():
            if path in (self._lat_path, self._lon_path, self._time_path) or ds.ndim < 2:
                continue
            if is_coordinate_or_metadata_var(path.split("/")[-1]):
                continue
            y, x = self._axis(ds, self._lat_path), self._axis(ds, self._lon_path)
            if y is None or x is None:
                # Conventional unlabelled HDF grids use trailing [latitude, longitude].
                if ds.shape[-2:] == (len(lat), len(lon)):
                    y, x = ds.ndim - 2, ds.ndim - 1
                elif ds.shape[-2:] == (len(lon), len(lat)):
                    x, y = ds.ndim - 2, ds.ndim - 1
                else:
                    continue
            t = self._axis(ds, self._time_path)
            if t is None and self._time_path and ds.ndim > 2:
                candidates = [i for i, n in enumerate(ds.shape) if i not in (y, x) and n == f[self._time_path].size]
                if len(candidates) == 1:
                    t = candidates[0]
            name = path.replace("/", "_")
            if name in self._paths:
                raise ValueError("HDF5 variable names collide after group normalization")
            self._paths[name], self._axes[name] = path, (y, x, t)
            count = ds.shape[t] if t is not None else 1
            max_frames = max(max_frames, count)
            fill = ds.attrs.get("_FillValue", ds.attrs.get("missing_value"))
            variables[name] = VariableInfo(name=name, long_name=text(ds.attrs.get("long_name", path)),
                standard_name=text(ds.attrs.get("standard_name", "")), units=text(ds.attrs.get("units", "")),
                shape=list(ds.shape), dimensions=[ds.dims[i].label or f"dim_{i}" for i in range(ds.ndim)],
                dtype=str(ds.dtype), fill_value=float(fill) if fill is not None else None,
                has_time=t is not None, aliases=[path.split("/")[-1]])
        if not variables:
            raise ValueError("No rectilinear spatial variables found in HDF5 file")
        if not self._time_axis.timestamps:
            self._time_axis = TimeAxisInfo(count=max_frames, resolution="irregular" if max_frames > 1 else "single")
        _, _, _, extent = normalize_grid_to_wgs84(np.zeros((len(lat), len(lon))), lat, lon)
        self._dataset_info = DatasetInfo(id=self.dataset_id, name=self.file_path.name, format=DatasetFormat.HDF5,
            file_path=str(self.file_path.resolve()), file_size_bytes=self.file_path.stat().st_size,
            dimensions={"lat": len(lat), "lon": len(lon)}, variables=variables,
            default_variable=pick_default_variable(variables), time_axis=self._time_axis, spatial_extent=extent)
        return self._dataset_info

    def read_frame(self, var_name: Optional[str] = None, time_index: int = 0):
        if self._dataset_info is None:
            self.inspect()
        name = var_name or self._dataset_info.default_variable
        if name not in self._paths:
            raise ValueError(f"HDF5 variable '{name}' not found")
        f = self._open()
        ds = f[self._paths[name]]
        y, x, t = self._axes[name]
        if not 0 <= time_index < (ds.shape[t] if t is not None else 1):
            raise ValueError("Time index outside variable time axis")
        index = [slice(None) if i in (y, x) else (time_index if i == t else 0) for i in range(ds.ndim)]
        raw = np.array(ds[tuple(index)], dtype=float, copy=True)
        if x < y:
            raw = raw.T
        meta = self._dataset_info.variables[name]
        if meta.fill_value is not None:
            raw[raw == meta.fill_value] = np.nan
        raw = raw * float(ds.attrs.get("scale_factor", 1)) + float(ds.attrs.get("add_offset", 0))
        raw[~np.isfinite(raw)] = np.nan
        data, lat, lon, extent = normalize_grid_to_wgs84(raw, f[self._lat_path][()], f[self._lon_path][()])
        valid = data[np.isfinite(data)]
        stamps = self._time_axis.timestamps
        return SliceData(data=data, lat_coords=lat, lon_coords=lon, extent=extent, variable_name=name,
            timestamp=stamps[time_index] if time_index < len(stamps) else None, time_index=time_index,
            units=meta.units, min_val=float(valid.min()) if valid.size else 0,
            max_val=float(valid.max()) if valid.size else 1, mask=~np.isfinite(data))

    def get_point_value(self, lat, lon, var_name=None, time_index=0):
        frame = self.read_frame(var_name, time_index)
        y, x, mlat, mlon = find_nearest_cell(lat, lon, frame.lat_coords, frame.lon_coords)
        value = frame.data[y, x]
        valid = bool(np.isfinite(value) and not frame.mask[y, x])
        return PointQueryResponse(dataset_id=self.dataset_id, variable=frame.variable_name, units=frame.units,
            requested_lat=lat, requested_lon=lon, matched_lat=mlat, matched_lon=mlon,
            grid_index_y=y, grid_index_x=x, cell_bounds=cell_bounds(frame.lat_coords, frame.lon_coords, y, x),
            value=float(value) if valid else None, is_valid=valid, timestamp=frame.timestamp, time_index=time_index)

    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None
