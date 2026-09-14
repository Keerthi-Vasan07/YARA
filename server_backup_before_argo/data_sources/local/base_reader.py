"""
Abstract Base Scientific Reader for YARA.
Defines the uniform interface for all format-specific dataset readers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import numpy as np

from .common_model import (
    DatasetInfo,
    VariableInfo,
    TimeAxisInfo,
    SpatialExtent,
    SliceData,
    PointQueryResponse
)


class BaseScientificReader(ABC):
    """Abstract base reader for scientific ocean/climate datasets."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        self.file_path = Path(file_path)
        self.dataset_id = dataset_id or self.file_path.stem
        self._dataset_info: Optional[DatasetInfo] = None

    @abstractmethod
    def inspect(self) -> DatasetInfo:
        """Inspects metadata, dimensions, coordinates, variables, and time axis."""
        pass

    @abstractmethod
    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        """
        Reads a single 2D grid slice [lat, lon] for the specified variable and time index.
        Normalizes grid coordinates and orientation to standard WGS84 for Cesium projection.
        """
        pass

    @abstractmethod
    def get_point_value(
        self,
        lat: float,
        lon: float,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> PointQueryResponse:
        """Queries the exact data value at specified geographic coordinates."""
        pass

    def get_time_axis(self) -> TimeAxisInfo:
        """Returns time axis metadata."""
        if not self._dataset_info:
            self.inspect()
        return self._dataset_info.time_axis

    def get_variables(self) -> Dict[str, VariableInfo]:
        """Returns detected variables dictionary."""
        if not self._dataset_info:
            self.inspect()
        return self._dataset_info.variables

    def get_spatial_extent(self) -> SpatialExtent:
        """Returns geographic bounding box."""
        if not self._dataset_info:
            self.inspect()
        return self._dataset_info.spatial_extent

    def close(self):
        """Releases file handles or memory resources."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
