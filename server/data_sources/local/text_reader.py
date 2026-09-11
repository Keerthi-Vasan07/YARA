"""
Text/ASCII Reader.

Reads plain text files with scientific data.
"""

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from .base_reader import BaseReader
from .common_model import Variable, CoordinateModel

logger = logging.getLogger(__name__)


class TextReader(BaseReader):
    """
    Reader for ASCII/text files (.txt, .asc).
    
    Supports simple tabular formats with headers.
    """
    
    def __init__(self, path: str, delimiter: str = None):
        super().__init__(path)
        self._delimiter = delimiter  # Auto-detect if None
        self._data: Optional[Dict[str, np.ndarray]] = None
        self._columns: List[str] = []
    
    def _detect_delimiter(self, sample: str) -> str:
        """Detect delimiter from file content."""
        if '\t' in sample:
            return '\t'
        elif ';' in sample:
            return ';'
        else:
            return ','  # Default to comma
    
    def _open(self) -> Dict[str, np.ndarray]:
        """Load text data."""
        if self._data is None:
            try:
                with open(self.path, 'r') as f:
                    lines = f.readlines()
                
                if not lines:
                    raise ValueError("Empty file")
                
                # Detect delimiter from first line
                if self._delimiter is None:
                    self._delimiter = self._detect_delimiter(lines[0])
                
                # Parse header
                header_line = lines[0].strip()
                self._columns = [c.strip() for c in header_line.split(self._delimiter)]
                
                # Parse data
                rows = []
                for line in lines[1:]:
                    if line.strip() and not line.startswith('#'):
                        values = [v.strip() for v in line.split(self._delimiter)]
                        rows.append(values)
                
                # Convert to arrays
                self._data = {}
                for i, col in enumerate(self._columns):
                    values = [row[i] if i < len(row) else '' for row in rows]
                    
                    try:
                        self._data[col] = np.array([float(v) if v else np.nan for v in values])
                    except ValueError:
                        self._data[col] = np.array(values)
                
                logger.info(f"[Text] Loaded {len(rows)} rows from {self.path}")
            except Exception as e:
                logger.error(f"[Text] Failed to load {self.path}: {e}")
                raise
        return self._data
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the file."""
        data = self._open()
        return {
            'format': 'text',
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
            'format': 'text',
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
        # Similar to CSV - simplified for brevity
        return CoordinateModel()
    
    def get_time_axis(self) -> List[str]:
        """Get time axis."""
        return []
    
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """Read data."""
        data = self._open()
        if variable_name not in data:
            raise ValueError(f"Column {variable_name} not found")
        return data[variable_name].astype(np.float32)
    
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
