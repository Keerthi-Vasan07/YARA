"""
Zarr Reader.

Reads Zarr datasets and normalizes them to the common data model.
Supports both Zarr v2 and v3 formats.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

try:
    import zarr
    HAS_ZARR = True
except ImportError:
    HAS_ZARR = False

from .base_reader import BaseReader
from .common_model import Dataset, Variable, CoordinateModel
from .coordinate_utils import normalize_longitude, extract_1d_coordinates, extract_2d_coordinates
from .time_utils import parse_cf_time
from .variable_detection import detect_scientific_variables

logger = logging.getLogger(__name__)


class ZarrReader(BaseReader):
    """
    Reader for Zarr datasets.
    
    Supports:
    - Zarr v2 (.zgroup at root)
    - Zarr v3 (zarr.json at root)
    - Chunked lazy loading
    - Multidimensional arrays
    """
    
    def __init__(self, path: str, storage_options: Optional[Dict[str, Any]] = None):
        """
        Initialize the Zarr reader.
        
        Args:
            path: Path to the Zarr dataset (directory or URL)
            storage_options: Optional storage configuration
        """
        if not HAS_ZARR:
            raise ImportError("zarr package is required for ZarrReader")
        
        super().__init__(path)
        self._storage_options = storage_options or {}
        self._root: Optional[zarr.Group] = None
        self._ds_cache: Optional[Any] = None  # xarray dataset cache
    
    def _open(self) -> zarr.Group:
        """Open the Zarr dataset if not already open."""
        if self._root is None:
            try:
                # Try opening as directory first
                if os.path.isdir(self.path):
                    self._root = zarr.open(self.path, mode='r', **self._storage_options)
                else:
                    # Try as URL or cloud storage
                    self._root = zarr.open(self.path, mode='r', **self._storage_options)
                
                logger.info(f"[Zarr] Opened: {self.path}")
            except Exception as e:
                logger.error(f"[Zarr] Failed to open {self.path}: {e}")
                raise
        return self._root
    
    def _to_xarray(self):
        """Convert to xarray Dataset for easier processing."""
        if self._ds_cache is None:
            try:
                import xarray as xr
                self._ds_cache = xr.open_zarr(self.path, **self._storage_options)
            except Exception as e:
                logger.warning(f"[Zarr] Could not open with xarray: {e}")
                self._ds_cache = None
        return self._ds_cache
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the Zarr dataset."""
        root = self._open()
        
        arrays = {}
        for name in root.array_keys():
            arr = root[name]
            arrays[name] = {
                'shape': arr.shape,
                'dtype': str(arr.dtype),
                'chunks': arr.chunks,
            }
        
        return {
            'format': 'zarr',
            'path': self.path,
            'arrays': arrays,
            'attributes': dict(root.attrs),
        }
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get full metadata."""
        root = self._open()
        
        arrays_info = []
        for name in root.array_keys():
            arr = root[name]
            arr_meta = {
                'name': name,
                'shape': list(arr.shape),
                'dtype': str(arr.dtype),
                'chunks': list(arr.chunks) if arr.chunks else None,
                'dimensions': [],  # Will be filled from xarray if available
                'units': arr.attrs.get('units'),
                'standard_name': arr.attrs.get('standard_name'),
                'long_name': arr.attrs.get('long_name'),
            }
            
            # Compute min/max for small arrays
            if arr.size < 1e6:
                try:
                    data = arr[:]
                    valid_data = data[~np.isnan(data)]
                    if len(valid_data) > 0:
                        arr_meta['min'] = float(np.min(valid_data))
                        arr_meta['max'] = float(np.max(valid_data))
                except Exception:
                    pass
            
            arrays_info.append(arr_meta)
        
        return {
            'format': 'zarr',
            'path': self.path,
            'source': 'local',
            'arrays': arrays_info,
            'global_attributes': dict(root.attrs),
        }
    
    def get_variables(self) -> List[Variable]:
        """Get list of variables."""
        ds = self._to_xarray()
        
        if ds is not None:
            return detect_scientific_variables(ds)
        
        # Fallback: create variables from zarr arrays
        root = self._open()
        variables = []
        
        for name in root.array_keys():
            arr = root[name]
            
            # Skip if looks like a coordinate
            if name.lower() in ['lat', 'lon', 'latitude', 'longitude', 'time', 'depth']:
                continue
            
            variable = Variable(
                name=name,
                standard_name=arr.attrs.get('standard_name'),
                long_name=arr.attrs.get('long_name'),
                units=arr.attrs.get('units'),
                dimensions=[],  # Unknown without xarray
                dtype=str(arr.dtype),
            )
            variables.append(variable)
        
        return variables
    
    def get_dimensions(self) -> Dict[str, int]:
        """Get dimensions."""
        ds = self._to_xarray()
        
        if ds is not None:
            return dict(ds.dims)
        
        # Fallback: estimate from arrays
        root = self._open()
        dims = {}
        
        for name in root.array_keys():
            arr = root[name]
            for i, size in enumerate(arr.shape):
                dim_name = f'dim_{i}'
                if dim_name not in dims:
                    dims[dim_name] = size
        
        return dims
    
    def get_coordinates(self) -> CoordinateModel:
        """Extract coordinates."""
        ds = self._to_xarray()
        
        if ds is not None:
            # Use xarray-based extraction
            lat_1d, lon_1d = extract_1d_coordinates(ds)
            
            latitude = lat_1d
            longitude = lon_1d
            lat_name = None
            lon_name = None
            
            if latitude is not None:
                for name in ['lat', 'latitude', 'y']:
                    if name in ds.coords:
                        lat_name = name
                        break
            
            if longitude is not None:
                for name in ['lon', 'longitude', 'x']:
                    if name in ds.coords:
                        lon_name = name
                        break
            
            # Extract time
            time_var = None
            time_name = None
            time_units = None
            
            for name in ['time', 't', 'datetime']:
                if name in ds.coords:
                    time_var = ds[name].values
                    time_name = name
                    time_units = ds[name].attrs.get('units', '')
                    break
            
            # Extract depth
            depth_var = None
            depth_name = None
            
            for name in ['depth', 'lev', 'level', 'z']:
                if name in ds.coords:
                    depth_var = ds[name].values
                    depth_name = name
                    break
            
            # Compute extents
            lat_min = float(np.min(latitude)) if latitude is not None else None
            lat_max = float(np.max(latitude)) if latitude is not None else None
            
            if longitude is not None:
                longitude = normalize_longitude(longitude)
                lon_min = float(np.min(longitude))
                lon_max = float(np.max(longitude))
            else:
                lon_min = None
                lon_max = None
            
            # Parse time
            time_parsed = None
            time_min = None
            time_max = None
            
            if time_var is not None:
                time_parsed, time_min, time_max = parse_cf_time(time_var, time_units)
            
            return CoordinateModel(
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
        
        # Fallback: no coordinates found
        return CoordinateModel()
    
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
        root = self._open()
        
        if variable_name not in root:
            raise ValueError(f"Variable {variable_name} not found")
        
        arr = root[variable_name]
        
        if time_index is not None and arr.ndim >= 3:
            # Assume first dimension is time
            data = arr[time_index, ...]
        else:
            data = arr[:]
        
        return data.astype(np.float32)
    
    def read_subset(
        self,
        variable_name: str,
        lat_slice: Optional[slice] = None,
        lon_slice: Optional[slice] = None,
        time_index: Optional[int] = None,
        depth_index: Optional[int] = None,
    ) -> np.ndarray:
        """Read a subset of data."""
        root = self._open()
        
        if variable_name not in root:
            raise ValueError(f"Variable {variable_name} not found")
        
        arr = root[variable_name]
        
        # Build indexer
        indexer = [slice(None)] * arr.ndim
        
        if time_index is not None and arr.ndim >= 3:
            indexer[0] = time_index
        
        if depth_index is not None and arr.ndim >= 4:
            indexer[1] = depth_index
        
        if lat_slice is not None:
            # Find latitude dimension (usually second-to-last for 4D)
            if arr.ndim >= 2:
                indexer[-2] = lat_slice
        
        if lon_slice is not None:
            # Find longitude dimension (usually last for 4D)
            if arr.ndim >= 2:
                indexer[-1] = lon_slice
        
        data = arr[tuple(indexer)]
        return data.astype(np.float32)
    
    def close(self) -> None:
        """Close the dataset."""
        if self._ds_cache is not None:
            try:
                self._ds_cache.close()
            except Exception:
                pass
            self._ds_cache = None
        
        self._root = None
        logger.info(f"[Zarr] Closed: {self.path}")
