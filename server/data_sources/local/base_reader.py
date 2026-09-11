"""
Base Reader Interface.

All dataset readers must inherit from this base class and implement
the required methods.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from .common_model import Dataset, Variable, CoordinateModel


class BaseReader(ABC):
    """
    Abstract base class for all dataset readers.
    
    Every reader must expose a common interface for:
    - inspecting the dataset
    - getting metadata
    - getting variables
    - getting dimensions
    - getting coordinates
    - getting time axis
    - reading data
    - reading subsets
    - closing the dataset
    """
    
    def __init__(self, path: str):
        """
        Initialize the reader with a path to the dataset.
        
        Args:
            path: Path to the file or directory
        """
        self.path = path
        self._dataset: Optional[Dataset] = None
        self._handle: Any = None
    
    @abstractmethod
    def inspect(self) -> Dict[str, Any]:
        """
        Inspect the dataset and return basic information.
        
        Returns:
            Dictionary with format, dimensions, variables info
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get full dataset metadata.
        
        Returns:
            Dictionary with complete metadata
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_variables(self) -> List[Variable]:
        """
        Get list of variables in the dataset.
        
        Returns:
            List of Variable objects
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_dimensions(self) -> Dict[str, int]:
        """
        Get dimensions and their sizes.
        
        Returns:
            Dictionary mapping dimension names to sizes
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_coordinates(self) -> CoordinateModel:
        """
        Get coordinate model with lat/lon/time/depth.
        
        Returns:
            CoordinateModel object
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_time_axis(self) -> List[str]:
        """
        Get time axis as ISO format strings.
        
        Returns:
            List of ISO format timestamp strings
        """
        raise NotImplementedError
    
    @abstractmethod
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """
        Read data for a variable, optionally at a specific time index.
        
        Args:
            variable_name: Name of the variable to read
            time_index: Optional time index for 4D+ datasets
            
        Returns:
            NumPy array with the data
        """
        raise NotImplementedError
    
    @abstractmethod
    def read_subset(
        self,
        variable_name: str,
        lat_slice: Optional[slice] = None,
        lon_slice: Optional[slice] = None,
        time_index: Optional[int] = None,
        depth_index: Optional[int] = None,
    ) -> np.ndarray:
        """
        Read a subset of data.
        
        Args:
            variable_name: Name of the variable
            lat_slice: Latitude slice
            lon_slice: Longitude slice
            time_index: Time index
            depth_index: Depth index
            
        Returns:
            NumPy array with the subset data
        """
        raise NotImplementedError
    
    @abstractmethod
    def close(self) -> None:
        """Close the dataset and release resources."""
        raise NotImplementedError
    
    def get_value_at_point(
        self,
        variable_name: str,
        lat: float,
        lon: float,
        time_index: Optional[int] = None,
    ) -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Get value at a specific geographic point.
        
        Uses nearest-neighbor lookup to find the closest grid cell.
        
        Args:
            variable_name: Name of the variable
            lat: Latitude
            lon: Longitude
            time_index: Optional time index
            
        Returns:
            Tuple of (value, info_dict) where info_dict contains:
            - lat_idx: Latitude index
            - lon_idx: Longitude index
            - distance: Distance to nearest grid point (degrees)
        """
        coords = self.get_coordinates()
        
        if coords.latitude is None or coords.longitude is None:
            return None, {'error': 'No coordinates available'}
        
        # Handle 1D vs 2D coordinates
        if coords.latitude.ndim == 1:
            lat_1d = coords.latitude
            lon_1d = coords.longitude
            
            # Find nearest indices
            lat_idx = int(np.argmin(np.abs(lat_1d - lat)))
            
            # Handle longitude wrapping (0-360 vs -180-180)
            lon_normalized = lon % 360
            if lon_normalized > 180:
                lon_normalized -= 360
            
            lon_1d_normalized = lon_1d.copy()
            lon_1d_normalized[lon_1d_normalized > 180] -= 360
            
            lon_idx = int(np.argmin(np.abs(lon_1d_normalized - lon_normalized)))
            
            # Read the data
            data = self.read_data(variable_name, time_index)
            
            if lat_idx < data.shape[0] and lon_idx < data.shape[1]:
                value = float(data[lat_idx, lon_idx])
                lat_dist = abs(lat_1d[lat_idx] - lat)
                lon_dist = abs(lon_1d_normalized[lon_idx] - lon_normalized)
                distance = np.sqrt(lat_dist**2 + lon_dist**2)
                
                return value, {
                    'lat_idx': lat_idx,
                    'lon_idx': lon_idx,
                    'distance': distance,
                    'method': 'nearest_neighbor',
                }
        
        return None, {'error': 'Could not find nearest grid point'}
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
