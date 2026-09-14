"""
Common Scientific Data Model for YARA.
Defines normalized schemas and data classes for all ingested scientific datasets.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from pydantic import BaseModel, Field


class DatasetFormat(str, Enum):
    NETCDF = "netcdf"
    ZARR = "zarr"
    GEOTIFF = "geotiff"
    HDF5 = "hdf5"
    CSV = "csv"
    TEXT_ASCII = "text_ascii"
    JSON = "json"
    GRIB = "grib"
    BUFR = "bufr"
    UNKNOWN = "unknown"


class TemporalResolution(str, Enum):
    HOURLY = "hourly"
    SUB_HOURLY = "sub_hourly"
    THREE_HOURLY = "3_hourly"
    DAILY = "daily"
    MONTHLY = "monthly"
    IRREGULAR = "irregular"
    SINGLE = "single"


class VariableType(str, Enum):
    SCALAR_GRID = "scalar_grid"
    VECTOR_GRID = "vector_grid"
    POINT_OBSERVATION = "point_observation"
    UNKNOWN = "unknown"


class SpatialExtent(BaseModel):
    west: float = Field(..., description="Westernmost longitude [-180, 180]")
    south: float = Field(..., description="Southernmost latitude [-90, 90]")
    east: float = Field(..., description="Easternmost longitude [-180, 180]")
    north: float = Field(..., description="Northernmost latitude [-90, 90]")
    is_global: bool = Field(False, description="True if covering 360 lon and ~180 lat")


class CoordinateInfo(BaseModel):
    name: str
    axis: str  # 'X', 'Y', 'Z', 'T'
    dim_name: str
    size: int
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: Optional[float] = None
    units: Optional[str] = None
    is_regular: bool = True
    is_ascending: bool = True


class TimeAxisInfo(BaseModel):
    dim_name: Optional[str] = None
    timestamps: List[str] = Field(default_factory=list, description="ISO-8601 formatted timestamps")
    resolution: TemporalResolution = TemporalResolution.SINGLE
    step_seconds: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    count: int = 0


class VariableInfo(BaseModel):
    name: str
    standard_name: Optional[str] = None
    long_name: Optional[str] = None
    units: Optional[str] = None
    dimensions: List[str] = Field(default_factory=list)
    shape: List[int] = Field(default_factory=list)
    dtype: str = "float32"
    var_type: VariableType = VariableType.SCALAR_GRID
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    fill_value: Optional[float] = None
    has_time: bool = False
    has_depth: bool = False
    aliases: List[str] = Field(default_factory=list)


class DatasetInfo(BaseModel):
    id: str
    name: str
    format: DatasetFormat
    source_type: str = "local"
    file_path: str
    file_size_bytes: int = 0
    dimensions: Dict[str, int] = Field(default_factory=dict)
    coordinates: Dict[str, CoordinateInfo] = Field(default_factory=dict)
    variables: Dict[str, VariableInfo] = Field(default_factory=dict)
    default_variable: Optional[str] = None
    time_axis: TimeAxisInfo = Field(default_factory=TimeAxisInfo)
    spatial_extent: SpatialExtent
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


@dataclass
class SliceData:
    """Raw 2D numpy grid slice ready for visual projection."""
    data: np.ndarray              # 2D array [lat, lon], north-up (lat decreasing or top-to-bottom)
    lat_coords: np.ndarray        # 1D array of latitudes
    lon_coords: np.ndarray        # 1D array of longitudes [-180, 180]
    extent: SpatialExtent         # Bounding box
    variable_name: str
    timestamp: Optional[str]
    time_index: int
    units: Optional[str]
    min_val: float
    max_val: float
    fill_value: Optional[float] = None
    mask: Optional[np.ndarray] = None  # True where data is invalid/nodata


class PointQueryResponse(BaseModel):
    dataset_id: str
    variable: str
    units: Optional[str] = None
    requested_lat: float
    requested_lon: float
    matched_lat: float
    matched_lon: float
    grid_index_y: int
    grid_index_x: int
    cell_bounds: Optional[SpatialExtent] = None
    value: Optional[float] = None
    is_valid: bool = True
    timestamp: Optional[str] = None
    time_index: Optional[int] = None
