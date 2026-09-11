"""
HDF5 Reader.

Reads HDF5 files with scientific data.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

try:
    import h5py
    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False

from .base_reader import BaseReader
from .common_model import Variable, CoordinateModel

logger = logging.getLogger(__name__)


class HDF5Reader(BaseReader):
    """
    Reader for HDF5 files (.h5, .hdf5).
    
    Requires h5py package.
    """
    
    def __init__(self, path: str):
        if not HAS_H5PY:
            raise ImportError("h5py package required for HDF5 support")
        
        super().__init__(path)
        self._file = None
        self._datasets = []
    
    def _open(self):
        """Open HDF5 file."""
        if self._file is None:
            try:
                self._file = h5py.File(self.path, 'r')
                logger.info(f"[HDF5] Opened: {self.path}")
            except Exception as e:
                logger.error(f"[HDF5] Failed to open {self.path}: {e}")
                raise
        return self._file
    
    def _list_datasets(self, group=None, prefix=''):
        """List all datasets in the file."""
        datasets = []
        container = group if group else self._file
        
        for key in container.keys():
            item = container[key]
            path = f"{prefix}/{key}" if prefix else key
            
            if isinstance(item, h5py.Dataset):
                datasets.append(path)
            elif isinstance(item, h5py.Group):
                datasets.extend(self._list_datasets(item, path))
        
        return datasets
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the file."""
        try:
            f = self._open()
            datasets = self._list_datasets(f)
            
            ds_info = {}
            for ds_path in datasets[:10]:  # Limit to first 10
                ds = f[ds_path]
                ds_info[ds_path] = {
                    'shape': list(ds.shape),
                    'dtype': str(ds.dtype),
                }
            
            return {
                'format': 'hdf5',
                'path': self.path,
                'datasets': ds_info,
                'total_datasets': len(datasets),
            }
        except Exception as e:
            return {'format': 'hdf5', 'path': self.path, 'error': str(e)}
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata."""
        return self.inspect()
    
    def get_variables(self) -> List[Variable]:
        """Get variables (datasets)."""
        try:
            f = self._open()
            datasets = self._list_datasets(f)
            
            variables = []
            for ds_path in datasets:
                ds = f[ds_path]
                
                # Skip if looks like coordinate
                name = ds_path.split('/')[-1].lower()
                if name in ['lat', 'lon', 'latitude', 'longitude', 'time']:
                    continue
                
                variables.append(Variable(
                    name=ds_path,
                    long_name=ds.attrs.get('long_name', ds_path),
                    units=ds.attrs.get('units', ''),
                    dimensions=[f'dim_{i}' for i in range(len(ds.shape))],
                ))
            
            return variables
        except Exception:
            return []
    
    def get_dimensions(self) -> Dict[str, int]:
        """Get dimensions."""
        try:
            f = self._open()
            datasets = self._list_datasets(f)
            
            dims = {}
            for ds_path in datasets[:1]:
                ds = f[ds_path]
                for i, size in enumerate(ds.shape):
                    dims[f'dim_{i}'] = size
                break
            
            return dims
        except Exception:
            return {}
    
    def get_coordinates(self) -> CoordinateModel:
        """Extract coordinates."""
        try:
            f = self._open()
            
            latitude = None
            longitude = None
            
            # Look for lat/lon datasets
            for name in ['lat', 'latitude', 'y']:
                if name in f:
                    latitude = f[name][:].astype(np.float64)
                    break
            
            for name in ['lon', 'longitude', 'x']:
                if name in f:
                    longitude = f[name][:].astype(np.float64)
                    break
            
            lat_min = float(np.min(latitude)) if latitude is not None else None
            lat_max = float(np.max(latitude)) if latitude is not None else None
            lon_min = float(np.min(longitude)) if longitude is not None else None
            lon_max = float(np.max(longitude)) if longitude is not None else None
            
            return CoordinateModel(
                latitude=latitude,
                longitude=longitude,
                lat_min=lat_min,
                lat_max=lat_max,
                lon_min=lon_min,
                lon_max=lon_max,
            )
        except Exception:
            return CoordinateModel()
    
    def get_time_axis(self) -> List[str]:
        """Get time axis."""
        return []
    
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """Read data."""
        f = self._open()
        
        if variable_name not in f:
            raise ValueError(f"Dataset {variable_name} not found")
        
        ds = f[variable_name]
        data = ds[:]
        
        if time_index is not None and data.ndim >= 3:
            data = data[time_index, ...]
        
        return data.astype(np.float32)
    
    def read_subset(
        self,
        variable_name: str,
        lat_slice: Optional[slice] = None,
        lon_slice: Optional[slice] = None,
        time_index: Optional[int] = None,
        depth_index: Optional[int] = None,
    ) -> np.ndarray:
        """Read subset."""
        return self.read_data(variable_name, time_index)
    
    def close(self) -> None:
        """Close."""
        if self._file is not None:
            self._file.close()
            self._file = None
            logger.info(f"[HDF5] Closed: {self.path}")
