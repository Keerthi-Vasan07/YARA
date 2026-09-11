"""
NetCDF Reader.

Reads NetCDF (.nc, .netcdf, .nc4) files and normalizes them to the common data model.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import numpy as np
import xarray as xr

from .base_reader import BaseReader
from .common_model import Dataset, Variable, CoordinateModel
from .coordinate_utils import normalize_longitude, extract_1d_coordinates, extract_2d_coordinates
from .time_utils import extract_time_axis, parse_cf_time
from .variable_detection import detect_scientific_variables, get_variable_metadata

logger = logging.getLogger(__name__)


class NetCDFReader(BaseReader):
    """
    Reader for NetCDF files using xarray.
    
    Supports:
    - NetCDF-3 (classic)
    - NetCDF-4 (HDF5-based)
    - CF-convention metadata
    - Lazy loading via chunks
    """
    
    def __init__(self, path: str, chunks: Optional[Dict[str, int]] = None):
        """
        Initialize the NetCDF reader.
        
        Args:
            path: Path to the NetCDF file
            chunks: Optional chunking configuration for lazy loading
        """
        super().__init__(path)
        self._chunks = chunks
        self._ds: Optional[xr.Dataset] = None
    
    def _open(self) -> xr.Dataset:
        """Open the NetCDF file if not already open."""
        if self._ds is None:
            try:
                self._ds = xr.open_dataset(self.path, chunks=self._chunks)
                logger.info(f"[NetCDF] Opened: {self.path}")
            except Exception as e:
                logger.error(f"[NetCDF] Failed to open {self.path}: {e}")
                raise
        return self._ds
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the dataset."""
        ds = self._open()
        
        return {
            'format': 'netcdf',
            'path': self.path,
            'dimensions': dict(ds.dims),
            'variables': list(ds.data_vars.keys()),
            'coordinates': list(ds.coords.keys()),
            'attributes': dict(ds.attrs),
        }
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get full metadata."""
        ds = self._open()
        
        variables = []
        for var_name in ds.data_vars:
            var = ds[var_name]
            var_meta = {
                'name': var_name,
                'standard_name': var.attrs.get('standard_name'),
                'long_name': var.attrs.get('long_name'),
                'units': var.attrs.get('units'),
                'dimensions': list(var.dims),
                'dtype': str(var.dtype),
            }
            
            # Compute min/max if small enough
            if var.size < 1e6:
                try:
                    data = var.values
                    valid_data = data[~np.isnan(data)]
                    if len(valid_data) > 0:
                        var_meta['min'] = float(np.min(valid_data))
                        var_meta['max'] = float(np.max(valid_data))
                except Exception:
                    pass
            
            variables.append(var_meta)
        
        coords_info = {}
        for coord_name in ds.coords:
            coord = ds[coord_name]
            coords_info[coord_name] = {
                'size': len(coord) if coord.ndim == 1 else list(coord.shape),
                'dtype': str(coord.dtype),
            }
        
        return {
            'format': 'netcdf',
            'path': self.path,
            'source': 'local',
            'dimensions': dict(ds.dims),
            'coordinates': coords_info,
            'variables': variables,
            'global_attributes': dict(ds.attrs),
        }
    
    def get_variables(self) -> List[Variable]:
        """Get list of variables."""
        ds = self._open()
        return detect_scientific_variables(ds)
    
    def get_dimensions(self) -> Dict[str, int]:
        """Get dimensions."""
        ds = self._open()
        return dict(ds.dims)
    
    def get_coordinates(self) -> CoordinateModel:
        """Extract coordinates from the dataset."""
        ds = self._open()
        
        # Try to find latitude and longitude
        lat_1d, lon_1d, lat_2d, lon_2d = extract_1d_coordinates(ds), extract_2d_coordinates(ds)
        
        # Prefer 1D coordinates if available
        if lat_1d is not None and lon_1d is not None:
            latitude = lat_1d
            longitude = lon_1d
            lat_name = self._find_coord_name(ds, ['lat', 'latitude', 'y'])
            lon_name = self._find_coord_name(ds, ['lon', 'longitude', 'x'])
        elif lat_2d is not None and lon_2d is not None:
            # Use flattened 2D coordinates (take first time/depth slice)
            if lat_2d.ndim == 2:
                latitude = lat_2d[0, :] if lat_2d.shape[0] > 1 else lat_2d.flatten()
                longitude = lon_2d[0, :] if lon_2d.shape[0] > 1 else lon_2d.flatten()
            else:
                latitude = lat_2d.flatten()
                longitude = lon_2d.flatten()
            lat_name = 'lat_2d'
            lon_name = 'lon_2d'
        else:
            latitude = None
            longitude = None
            lat_name = None
            lon_name = None
        
        # Extract time
        time_var = None
        time_name = self._find_coord_name(ds, ['time', 't', 'datetime'])
        if time_name and time_name in ds.coords:
            time_var = ds[time_name].values
            time_units = ds[time_name].attrs.get('units', '')
        else:
            time_units = None
        
        # Extract depth if present
        depth_var = None
        depth_name = self._find_coord_name(ds, ['depth', 'lev', 'level', 'z'])
        if depth_name and depth_name in ds.coords:
            depth_var = ds[depth_name].values
        
        # Compute extents
        lat_min = float(np.min(latitude)) if latitude is not None else None
        lat_max = float(np.max(latitude)) if latitude is not None else None
        lon_min = float(np.min(longitude)) if longitude is not None else None
        lon_max = float(np.max(longitude)) if longitude is not None else None
        
        # Normalize longitude to -180 to 180
        if longitude is not None:
            longitude = normalize_longitude(longitude)
            if lon_min is not None and lon_max is not None:
                if lon_max > 180:
                    lon_min = -180
                    lon_max = 180
        
        # Parse time
        time_parsed = None
        time_min = None
        time_max = None
        if time_var is not None:
            time_parsed, time_min, time_max = parse_cf_time(time_var, time_units)
        
        coords = CoordinateModel(
            latitude=latitude,
            longitude=longitude,
            time=time_parsed,
            depth=depth_var,
            lat_name=lat_name,
            lon_name=lon_name,
            time_name=time_name,
            depth_name=depth_name,
            time_units=time_units,
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
            time_min=time_min,
            time_max=time_max,
        )
        
        return coords
    
    def _find_coord_name(self, ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
        """Find a coordinate by name or standard_name."""
        for name in candidates:
            if name in ds.coords:
                return name
        
        # Try standard_name attribute
        for coord_name in ds.coords:
            std_name = ds.coords[coord_name].attrs.get('standard_name', '')
            if std_name in candidates:
                return coord_name
        
        return None
    
    def get_time_axis(self) -> List[str]:
        """Get time axis as ISO strings."""
        coords = self.get_coordinates()
        
        if coords.time is None:
            return []
        
        if isinstance(coords.time[0], datetime):
            return [t.isoformat() for t in coords.time]
        else:
            return [str(t) for t in coords.time]
    
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """Read data for a variable."""
        ds = self._open()
        
        if variable_name not in ds.data_vars:
            raise ValueError(f"Variable {variable_name} not found")
        
        var = ds[variable_name]
        
        # Determine dimensions
        dims = var.dims
        
        if time_index is not None and 'time' in dims:
            # Select specific time
            time_dim = 'time'
            time_coord = ds[time_dim]
            if time_index < len(time_coord):
                var = var.isel({time_dim: time_index})
        
        # Load and convert to numpy
        data = var.values.astype(np.float32)
        
        # Handle fill values
        fill_value = var.attrs.get('_FillValue')
        missing_value = var.attrs.get('missing_value')
        
        if fill_value is not None:
            data = np.where(data == fill_value, np.nan, data)
        if missing_value is not None:
            data = np.where(data == missing_value, np.nan, data)
        
        return data
    
    def read_subset(
        self,
        variable_name: str,
        lat_slice: Optional[slice] = None,
        lon_slice: Optional[slice] = None,
        time_index: Optional[int] = None,
        depth_index: Optional[int] = None,
    ) -> np.ndarray:
        """Read a subset of data."""
        ds = self._open()
        
        if variable_name not in ds.data_vars:
            raise ValueError(f"Variable {variable_name} not found")
        
        var = ds[variable_name]
        selection = {}
        
        if time_index is not None and 'time' in var.dims:
            selection['time'] = time_index
        
        if depth_index is not None:
            for dim in ['depth', 'lev', 'level', 'z']:
                if dim in var.dims:
                    selection[dim] = depth_index
                    break
        
        if lat_slice is not None:
            for dim in ['lat', 'latitude', 'y']:
                if dim in var.dims:
                    selection[dim] = lat_slice
                    break
        
        if lon_slice is not None:
            for dim in ['lon', 'longitude', 'x']:
                if dim in var.dims:
                    selection[dim] = lon_slice
                    break
        
        if selection:
            var = var.isel(selection)
        
        data = var.values.astype(np.float32)
        
        # Handle fill values
        fill_value = var.attrs.get('_FillValue')
        if fill_value is not None:
            data = np.where(data == fill_value, np.nan, data)
        
        return data
    
    def close(self) -> None:
        """Close the dataset."""
        if self._ds is not None:
            self._ds.close()
            self._ds = None
            logger.info(f"[NetCDF] Closed: {self.path}")
