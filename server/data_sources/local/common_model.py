"""
Common Scientific Data Model.

This module defines the unified internal representation that all dataset readers
must normalize their data into. This allows the Cesium frontend to work with a
consistent data structure regardless of the original file format.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import numpy as np


@dataclass
class Variable:
    """
    Represents a scientific variable in the dataset.
    
    Attributes:
        name: Variable name as it appears in the dataset
        standard_name: CF standard name if available (e.g., 'sea_surface_temperature')
        long_name: Descriptive name (e.g., 'Sea Surface Temperature')
        units: Units of measurement (e.g., 'degC', 'm/s')
        dimensions: List of dimension names (e.g., ['time', 'lat', 'lon'])
        dtype: NumPy data type
        min: Minimum valid value
        max: Maximum valid value
        fill_value: Fill/missing value indicator
    """
    name: str
    standard_name: Optional[str] = None
    long_name: Optional[str] = None
    units: Optional[str] = None
    dimensions: List[str] = field(default_factory=list)
    dtype: str = "float32"
    min: Optional[float] = None
    max: Optional[float] = None
    fill_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'standard_name': self.standard_name,
            'long_name': self.long_name,
            'units': self.units,
            'dimensions': self.dimensions,
            'dtype': self.dtype,
            'min': self.min,
            'max': self.max,
            'fill_value': self.fill_value,
        }


@dataclass
class CoordinateModel:
    """
    Represents coordinate axes in the dataset.
    
    Attributes:
        latitude: 1D or 2D latitude coordinates
        longitude: 1D or 2D longitude coordinates
        time: Time coordinates (datetime or numeric with units)
        depth: Depth/level coordinates (optional)
    """
    latitude: Optional[np.ndarray] = None
    longitude: Optional[np.ndarray] = None
    time: Optional[np.ndarray] = None
    depth: Optional[np.ndarray] = None
    
    # Metadata
    lat_name: Optional[str] = None
    lon_name: Optional[str] = None
    time_name: Optional[str] = None
    depth_name: Optional[str] = None
    time_units: Optional[str] = None  # e.g., 'days since 1970-01-01'
    
    # Spatial extent
    lat_min: Optional[float] = None
    lat_max: Optional[float] = None
    lon_min: Optional[float] = None
    lon_max: Optional[float] = None
    
    # Temporal extent
    time_min: Optional[Union[datetime, float]] = None
    time_max: Optional[Union[datetime, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'latitude': {
                'name': self.lat_name,
                'size': len(self.latitude) if self.latitude is not None else 0,
                'min': self.lat_min,
                'max': self.lat_max,
            },
            'longitude': {
                'name': self.lon_name,
                'size': len(self.longitude) if self.longitude is not None else 0,
                'min': self.lon_min,
                'max': self.lon_max,
            },
            'spatial_extent': {
                'lat_min': self.lat_min,
                'lat_max': self.lat_max,
                'lon_min': self.lon_min,
                'lon_max': self.lon_max,
            }
        }
        
        if self.time is not None:
            if isinstance(self.time[0], datetime):
                time_values = [t.isoformat() if isinstance(t, datetime) else str(t) for t in self.time]
                result['time'] = {
                    'name': self.time_name,
                    'size': len(self.time),
                    'values': time_values,
                    'units': self.time_units,
                }
                result['temporal_extent'] = {
                    'time_min': self.time_min.isoformat() if isinstance(self.time_min, datetime) else str(self.time_min),
                    'time_max': self.time_max.isoformat() if isinstance(self.time_max, datetime) else str(self.time_max),
                }
            else:
                result['time'] = {
                    'name': self.time_name,
                    'size': len(self.time),
                    'units': self.time_units,
                }
                result['temporal_extent'] = {
                    'time_min': float(self.time_min) if self.time_min is not None else None,
                    'time_max': float(self.time_max) if self.time_max is not None else None,
                }
        
        if self.depth is not None:
            result['depth'] = {
                'name': self.depth_name,
                'size': len(self.depth),
                'min': float(np.min(self.depth)),
                'max': float(np.max(self.depth)),
            }
        
        return result


@dataclass
class Dataset:
    """
    Common dataset representation.
    
    Attributes:
        id: Unique identifier for the dataset
        source: Source type ('local' or 'opendap')
        format: File format (e.g., 'netcdf', 'zarr', 'csv')
        path: Path to the dataset file/directory
        variables: List of variables in the dataset
        coordinates: Coordinate model
        dimensions: Dictionary of dimension names and sizes
        metadata: Additional metadata attributes
        temporal_resolution: Detected temporal resolution (e.g., 'hourly', 'daily')
        time_axis: List of actual timestamps (ISO format strings)
    """
    id: str
    source: str
    format: str
    path: str
    variables: List[Variable] = field(default_factory=list)
    coordinates: Optional[CoordinateModel] = None
    dimensions: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    temporal_resolution: Optional[str] = None
    time_axis: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'source': self.source,
            'format': self.format,
            'path': self.path,
            'variables': [v.to_dict() for v in self.variables],
            'coordinates': self.coordinates.to_dict() if self.coordinates else None,
            'dimensions': self.dimensions,
            'metadata': self.metadata,
            'temporal_resolution': self.temporal_resolution,
            'time_axis': self.time_axis,
        }


class CommonDataModel:
    """
    Container for the common data model used throughout the application.
    
    This class provides a unified interface for accessing scientific data
    regardless of the original format.
    """
    
    def __init__(self):
        self._datasets: Dict[str, Dataset] = {}
        self._active_dataset_id: Optional[str] = None
        self._frame_cache: Dict[str, Any] = {}  # Cache for processed frames
    
    def register_dataset(self, dataset: Dataset) -> None:
        """Register a dataset in the model."""
        self._datasets[dataset.id] = dataset
    
    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        """Get a dataset by ID."""
        return self._datasets.get(dataset_id)
    
    def set_active_dataset(self, dataset_id: str) -> None:
        """Set the active dataset for visualization."""
        if dataset_id not in self._datasets:
            raise ValueError(f"Dataset {dataset_id} not found")
        self._active_dataset_id = dataset_id
    
    def get_active_dataset(self) -> Optional[Dataset]:
        """Get the currently active dataset."""
        if self._active_dataset_id:
            return self._datasets.get(self._active_dataset_id)
        return None
    
    def clear(self) -> None:
        """Clear all datasets and caches."""
        self._datasets.clear()
        self._frame_cache.clear()
        self._active_dataset_id = None
    
    def cache_frame(self, key: str, frame_data: Any) -> None:
        """Cache a processed frame."""
        self._frame_cache[key] = frame_data
    
    def get_cached_frame(self, key: str) -> Optional[Any]:
        """Get a cached frame."""
        return self._frame_cache.get(key)
    
    def clear_frame_cache(self) -> None:
        """Clear the frame cache."""
        self._frame_cache.clear()
