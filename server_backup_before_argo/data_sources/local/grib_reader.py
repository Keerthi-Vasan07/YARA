"""
GRIB / GRIB2 Scientific Reader for YARA.
Supports GRIB1 and GRIB2 meteorological and oceanographic fields.
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


class GRIBReader(BaseScientificReader):
    """Reader for GRIB / GRIB2 datasets."""

    def inspect(self) -> DatasetInfo:
        # Check header
        with open(self.file_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"GRIB"):
            raise ValueError(f"File {self.file_path.name} does not have valid GRIB header.")

        edition = header[7] if len(header) > 7 else 2

        # Try opening with cfgrib / xarray if available
        try:
            import xarray as xr
            ds = xr.open_dataset(self.file_path, engine="cfgrib")
            from .netcdf_reader import NetCDFReader
            # Delegate to xarray processing logic
            proxy = NetCDFReader(self.file_path, self.dataset_id)
            proxy._ds = ds
            info = proxy.inspect()
            info.format = DatasetFormat.GRIB
            self._dataset_info = info
            return self._dataset_info
        except ImportError:
            raise RuntimeError(
                f"GRIB{edition} file validated successfully ({self.file_path.name}), but 'cfgrib'/'eccodes' "
                "engine is not installed on this system. To enable native GRIB reading, install eccodes/cfgrib."
            )
        except Exception as e:
            raise RuntimeError(f"GRIB reading failed: {e}")

    def read_frame(self, var_name: Optional[str] = None, time_index: int = 0) -> SliceData:
        raise NotImplementedError("GRIB frame extraction requires cfgrib.")

    def get_point_value(self, lat: float, lon: float, var_name: Optional[str] = None, time_index: int = 0) -> PointQueryResponse:
        raise NotImplementedError("GRIB point lookup requires cfgrib.")
