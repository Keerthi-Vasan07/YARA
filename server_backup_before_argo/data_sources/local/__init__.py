"""
Local scientific dataset ingestion and reader package.
"""

from .common_model import (
    DatasetFormat,
    TemporalResolution,
    VariableType,
    SpatialExtent,
    CoordinateInfo,
    TimeAxisInfo,
    VariableInfo,
    DatasetInfo,
    SliceData,
    PointQueryResponse
)
from .registry import registry, DatasetRegistry
from .detector import detect_dataset_format

__all__ = [
    "DatasetFormat",
    "TemporalResolution",
    "VariableType",
    "SpatialExtent",
    "CoordinateInfo",
    "TimeAxisInfo",
    "VariableInfo",
    "DatasetInfo",
    "SliceData",
    "PointQueryResponse",
    "registry",
    "DatasetRegistry",
    "detect_dataset_format",
]
