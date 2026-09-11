"""
GRIB/GRIB2 Reader.

Reads GRIB meteorological/oceanographic data files.
Uses earthkit-data or cfgrib when available.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

from .base_reader import BaseReader
from .common_model import Variable, CoordinateModel

logger = logging.getLogger(__name__)


class GRIBReader(BaseReader):
    """
    Reader for GRIB/GRIB2 files.
    
    Requires earthkit-data or cfgrib package.
    """
    
    def __init__(self, path: str):
        super().__init__(path)
        self._data = None
        self._fields = []
    
    def _open(self):
        """Open GRIB file."""
        if self._data is None:
            try:
                import earthkit.data
                self._data = earthkit.data.from_source("file", self.path)
                logger.info(f"[GRIB] Opened: {self.path}")
            except ImportError:
                logger.warning("[GRIB] earthkit-data not available")
                raise ImportError("earthkit-data package required for GRIB support")
            except Exception as e:
                logger.error(f"[GRIB] Failed to open {self.path}: {e}")
                raise
        return self._data
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the file."""
        try:
            data = self._open()
            return {
                'format': 'grib',
                'path': self.path,
                'messages': len(data),
                'parameters': list(set([f.metadata('param') for f in data])) if len(data) > 0 else [],
            }
        except Exception as e:
            return {'format': 'grib', 'path': self.path, 'error': str(e)}
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata."""
        return self.inspect()
    
    def get_variables(self) -> List[Variable]:
        """Get variables."""
        try:
            data = self._open()
            variables = []
            
            params = set()
            for f in data:
                param = f.metadata('param', default='unknown')
                if param not in params:
                    params.add(param)
                    variables.append(Variable(
                        name=param,
                        long_name=f.metadata('paramName', default=param),
                        units=f.metadata('units', default=''),
                        dimensions=['lat', 'lon'],
                    ))
            
            return variables
        except Exception:
            return []
    
    def get_dimensions(self) -> Dict[str, int]:
        """Get dimensions."""
        try:
            data = self._open()
            if len(data) > 0:
                # Estimate from first field
                field = data[0]
                return {'lat': field.shape[0], 'lon': field.shape[1]}
        except Exception:
            pass
        return {}
    
    def get_coordinates(self) -> CoordinateModel:
        """Extract coordinates."""
        try:
            data = self._open()
            if len(data) > 0:
                field = data[0]
                lats = field.grid_points()[0][:, 1]  # latitude
                lons = field.grid_points()[0][:, 0]  # longitude
                
                return CoordinateModel(
                    latitude=np.array(lats),
                    longitude=np.array(lons),
                    lat_min=float(np.min(lats)),
                    lat_max=float(np.max(lats)),
                    lon_min=float(np.min(lons)),
                    lon_max=float(np.max(lons)),
                )
        except Exception:
            pass
        return CoordinateModel()
    
    def get_time_axis(self) -> List[str]:
        """Get time axis."""
        try:
            data = self._open()
            times = []
            for f in data:
                valid_time = f.metadata('validDate', default=None)
                if valid_time:
                    times.append(str(valid_time))
            return list(set(times))
        except Exception:
            return []
    
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """Read data."""
        data = self._open()
        
        # Find matching field
        for i, f in enumerate(data):
            param = f.metadata('param', default='')
            if param == variable_name:
                if time_index is None or i == time_index:
                    return f.values.astype(np.float32)
        
        raise ValueError(f"Parameter {variable_name} not found")
    
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
