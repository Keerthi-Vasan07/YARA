"""
CSV Reader.

Reads CSV files with scientific data (tabular observations).
"""

import csv
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

from .base_reader import BaseReader
from .common_model import Dataset, Variable, CoordinateModel

logger = logging.getLogger(__name__)


class CSVReader(BaseReader):
    """
    Reader for CSV files containing tabular scientific data.
    
    Expected columns:
    - latitude or lat
    - longitude or lon
    - time or datetime (optional)
    - One or more value columns
    """
    
    def __init__(self, path: str, delimiter: str = ','):
        super().__init__(path)
        self._delimiter = delimiter
        self._data: Optional[Dict[str, np.ndarray]] = None
        self._columns: List[str] = []
    
    def _open(self) -> Dict[str, np.ndarray]:
        """Load CSV data."""
        if self._data is None:
            try:
                with open(self.path, 'r') as f:
                    reader = csv.DictReader(f, delimiter=self._delimiter)
                    self._columns = reader.fieldnames or []
                    
                    # Read all rows
                    rows = list(reader)
                    
                    # Convert to numpy arrays
                    self._data = {}
                    for col in self._columns:
                        values = [row.get(col, '') for row in rows]
                        
                        # Try numeric conversion
                        try:
                            self._data[col] = np.array([float(v) if v else np.nan for v in values])
                        except ValueError:
                            self._data[col] = np.array(values)
                
                logger.info(f"[CSV] Loaded {len(rows)} rows from {self.path}")
            except Exception as e:
                logger.error(f"[CSV] Failed to load {self.path}: {e}")
                raise
        return self._data
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the CSV file."""
        data = self._open()
        return {
            'format': 'csv',
            'path': self.path,
            'columns': self._columns,
            'rows': len(list(data.values())[0]) if data else 0,
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
                col_meta['dtype'] = 'string'
            
            columns_info.append(col_meta)
        
        return {
            'format': 'csv',
            'path': self.path,
            'source': 'local',
            'columns': columns_info,
        }
    
    def get_variables(self) -> List[Variable]:
        """Get variables (value columns)."""
        data = self._open()
        variables = []
        
        coord_names = {'lat', 'latitude', 'lon', 'longitude', 'time', 'datetime', 'date'}
        
        for col in self._columns:
            if col.lower() not in coord_names:
                variables.append(Variable(
                    name=col,
                    long_name=col,
                    dimensions=['observation'],
                ))
        
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
        
        # Find latitude
        for name in ['lat', 'latitude']:
            if name in data:
                latitude = data[name].astype(np.float64)
                lat_min = float(np.nanmin(latitude))
                lat_max = float(np.nanmax(latitude))
                break
        
        # Find longitude
        for name in ['lon', 'longitude']:
            if name in data:
                longitude = data[name].astype(np.float64)
                lon_min = float(np.nanmin(longitude))
                lon_max = float(np.nanmax(longitude))
                break
        
        # Find time
        for name in ['time', 'datetime', 'date']:
            if name in data:
                try:
                    time_strs = data[name]
                    time = np.array([datetime.fromisoformat(str(t)) for t in time_strs if t])
                    if len(time) > 0:
                        time_min = np.min(time)
                        time_max = np.max(time)
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
        """Read data for a variable."""
        data = self._open()
        
        if variable_name not in data:
            raise ValueError(f"Column {variable_name} not found")
        
        result = data[variable_name].astype(np.float32)
        
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
        data = self._open()
        
        if variable_name not in data:
            raise ValueError(f"Column {variable_name} not found")
        
        result = data[variable_name].astype(np.float32)
        
        if lat_slice:
            result = result[lat_slice]
        if time_index is not None:
            result = np.array([result[time_index]])
        
        return result
    
    def close(self) -> None:
        """Close and release resources."""
        self._data = None
        logger.info(f"[CSV] Closed: {self.path}")
