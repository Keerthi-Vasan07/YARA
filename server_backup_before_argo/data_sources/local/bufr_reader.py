"""
BUFR Scientific Reader for YARA.
Supports WMO BUFR observation records.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import numpy as np

from .base_reader import BaseScientificReader
from .common_model import (
    DatasetFormat,
    DatasetInfo,
    VariableInfo,
    VariableType,
    CoordinateInfo,
    TimeAxisInfo,
    SpatialExtent,
    SliceData,
    PointQueryResponse
)


class BUFRReader(BaseScientificReader):
    """Reader for WMO BUFR observation records."""

    def inspect(self) -> DatasetInfo:
        with open(self.file_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"BUFR"):
            raise ValueError(f"File {self.file_path.name} does not have valid BUFR header.")

        edition = header[7] if len(header) > 7 else 4

        # BUFR requires ecCodes / pybufr / earthkit
        raise RuntimeError(
            f"BUFR Edition {edition} file validated successfully ({self.file_path.name}). "
            "BUFR table decoding requires WMO ecCodes/pdbufr tables."
        )

    def read_frame(self, var_name: Optional[str] = None, time_index: int = 0) -> SliceData:
        raise NotImplementedError("BUFR frame extraction requires WMO ecCodes table decoders.")

    def get_point_value(self, lat: float, lon: float, var_name: Optional[str] = None, time_index: int = 0) -> PointQueryResponse:
        raise NotImplementedError("BUFR point lookup requires WMO ecCodes table decoders.")
