"""
JSON Reader.

Reads JSON files with scientific observation data.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

from .base_reader import BaseReader
from .common_model import Variable, CoordinateModel

logger = logging.getLogger(__name__)


class JSONReader(BaseReader):
    """
    Reader for JSON files containing structured observation data.
    
    Expected structure:
    {
        "data": [
            {"lat": 10, "lon": 20, "time": "2024-01-01", "value": 25.5},
            ...
        ]
    }
    or array format:
    [
        {"lat": 10, "lon": 20, ...},
        ...
    ]
    """
    
    def __init__(self, path: str):
        super().__init__(path)
        self._data: Optional[Dict[str, np.ndarray]] = None
        self._columns: List[str] = []
    
    def _open(self) -> Dict[str, np.ndarray]:
        """Load JSON data."""
        if self._data is None:
            try:
                with open(self.path, 'r') as f:
                    content = json.load(f)
                
                # Handle different structures
                if isinstance(content, list):
                    rows = content
                elif isinstance(content, dict):
                    # Look for data array
                    for key in ['data', 'observations', 'records']:
                        if key in content and isinstance(content[key], list):
                            rows = content[key]
                            break
                    else:
                        # Treat whole dict as single record
                        rows = [content]
                else:
                    raise ValueError("Unsupported JSON structure")
                
                if not rows:
                    raise ValueError("Empty data")
                
                # Extract columns
                self._columns = list(rows[0].keys())
                
                # Convert to arrays
                self._data = {}
                for col in self._columns:
                    values = [row.get(col) for row in rows]
                    
                    try:
                        self._data[col] = np.array([float(v) if v is not None else np.nan for v in values])
                    except (ValueError, TypeError):
                        self._data[col] = np.array(values, dtype=object)
                
                logger.info(f"[JSON] Loaded {len(rows)} records from {self.path}")
            except Exception as e:
                logger.error(f"[JSON] Failed to load {self.path}: {e}")
                raise
        return self._data
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the file."""
        data = self._open()
        return {
            'format': 'json',
            'path': self.path,
            'columns': self._columns,
            'records': len(list(data.values())[0]) if data else 0,
        }
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata."""
        data = self._open()
        
        columns_info = []
        for col in self._columns:
            col_data = data.get(col, [])
            col_meta = {'name': col}
            
            if isinstance(col_data, np.ndarray) and np.issubdtype(col_data.dtype, np.number):
                valid = col_data[~np.isnan(col_data)]
                if len(valid) > 0:
                    col_meta['dtype'] = str(col_data.dtype)
                    col_meta['min'] = float(np.min(valid))
                    col_meta['max'] = float(np.max(valid))
            else:
                col_meta['dtype'] = 'mixed'
            
            columns_info.append(col_meta)
        
        return {
            'format': 'json',
            'path': self.path,
            'source': 'local',
            'columns': columns_info,
        }
    
    def get_variables(self) -> List[Variable]:
        """Get variables."""
        data = self._open()
        variables = []
        
        coord_names = {'lat', 'latitude', 'lon', 'longitude', 'time', 'datetime', 'date'}
        
        for col in self._columns:
            if col.lower() not in coord_names:
                variables.append(Variable(name=col, long_name=col, dimensions=['observation']))
        
        return variables
    
    def get_dimensions(self) -> Dict[str, int]:
        """Get dimensions."""
        data = self._open()
        if data:
            n_obs = len(list(data.values())[0])
            return {'observation': n_obs}
        return {}
    
    def get_coordinates(self) -> CoordinateModel:
        """Extract coordinates."""
        data = self._open()
        
        latitude = None
        longitude = None
        time = None
        
        lat_min = lat_max = lon_min = lon_max = None
        
        for name in ['lat', 'latitude']:
            if name in data:
                latitude = data[name].astype(np.float64)
                lat_min = float(np.nanmin(latitude))
                lat_max = float(np.nanmax(latitude))
                break
        
        for name in ['lon', 'longitude']:
            if name in data:
                longitude = data[name].astype(np.float64)
                lon_min = float(np.nanmin(longitude))
                lon_max = float(np.nanmax(longitude))
                break
        
        for name in ['time', 'datetime', 'date']:
            if name in data:
                try:
                    time_strs = data[name]
                    time_vals = []
                    for t in time_strs:
                        if t:
                            try:
                                time_vals.append(datetime.fromisoformat(str(t)))
                            except Exception:
                                pass
                    if time_vals:
                        time = np.array(time_vals)
                except Exception:
                    pass
                break
        
        return CoordinateModel(
            latitude=latitude,
            longitude=longitude,
            time=time if time is not None else None,
            lat_name='lat' if latitude is not None else None,
            lon_name='lon' if longitude is not None else None,
            time_name='time' if time is not None else None,
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
        )
    
    def get_time_axis(self) -> List[str]:
        """Get time axis."""
        coords = self.get_coordinates()
        if coords.time is None:
            return []
        return [t.isoformat() if isinstance(t, datetime) else str(t) for t in coords.time]
    
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """Read data."""
        data = self._open()
        if variable_name not in data:
            raise ValueError(f"Field {variable_name} not found")
        
        result = data[variable_name].astype(np.float32) if np.issubdtype(data[variable_name].dtype, np.number) else data[variable_name]
        
        if time_index is not None:
            return np.array([result[time_index]])
        
        return result
    
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
        self._data = None
