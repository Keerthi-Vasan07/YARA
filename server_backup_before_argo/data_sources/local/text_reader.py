"""
ASCII / Text Scientific Reader for YARA.
Supports ESRI ASCII Grid formats (.asc, .txt) and delimited scientific text data.
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
from .coordinate_utils import normalize_grid_to_wgs84, find_nearest_cell


class TextASCIIReader(BaseScientificReader):
    """Reader for ASCII grids and formatted scientific text files."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        super().__init__(file_path, dataset_id)
        self._grid_data: Optional[np.ndarray] = None
        self._extent: Optional[SpatialExtent] = None
        self._nodata: Optional[float] = None

    def inspect(self) -> DatasetInfo:
        # Check for ESRI ASCII Grid headers: ncols, nrows, xllcorner, yllcorner, cellsize, nodata_value
        header = {}
        data_start_line = 0
        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_idx, line in enumerate(f):
                parts = line.strip().split()
                if not parts:
                    continue
                key = parts[0].lower()
                if key in ("ncols", "nrows", "xllcorner", "xllcenter", "yllcorner", "yllcenter", "cellsize", "nodata_value"):
                    try:
                        header[key] = float(parts[1]) if "." in parts[1] else int(parts[1])
                    except Exception:
                        header[key] = parts[1]
                    data_start_line = line_idx + 1
                else:
                    break

        if "ncols" in header and "nrows" in header:
            ncols = int(header["ncols"])
            nrows = int(header["nrows"])
            cellsize = float(header.get("cellsize", 1.0))
            xll = float(header.get("xllcorner", header.get("xllcenter", -180.0)))
            yll = float(header.get("yllcorner", header.get("yllcenter", -90.0)))
            nodata = float(header.get("nodata_value", -9999))
            self._nodata = nodata

            west = xll
            east = xll + ncols * cellsize
            south = yll
            north = yll + nrows * cellsize

            extent = SpatialExtent(
                west=west,
                south=south,
                east=east,
                north=north,
                is_global=(east - west >= 355.0 and north - south >= 160.0)
            )
            self._extent = extent

            # Read remaining as 2D numpy array
            data = np.loadtxt(self.file_path, skiprows=data_start_line, dtype=np.float32)
            if data.shape != (nrows, ncols):
                data = data.reshape((nrows, ncols))
            self._grid_data = data
        else:
            # Fallback: treat as whitespace delimited array
            try:
                data = np.loadtxt(self.file_path, dtype=np.float32)
                if data.ndim != 2:
                    raise ValueError(f"Text file must be 2D matrix or ASCII grid, got shape {data.shape}")
                nrows, ncols = data.shape
                extent = SpatialExtent(west=-180.0, south=-90.0, east=180.0, north=90.0, is_global=True)
                self._extent = extent
                self._grid_data = data
                self._nodata = None
            except Exception as e:
                raise ValueError(f"Unable to parse scientific ASCII structure: {e}")

        var_name = self.file_path.stem
        variables_info = {
            var_name: VariableInfo(
                name=var_name,
                standard_name="ascii_field",
                dimensions=["y", "x"],
                shape=[nrows, ncols],
                dtype="float32",
                var_type=VariableType.SCALAR_GRID,
                fill_value=self._nodata,
                aliases=[var_name]
            )
        }

        file_size = 0
        try:
            file_size = self.file_path.stat().st_size
        except Exception:
            pass

        self._dataset_info = DatasetInfo(
            id=self.dataset_id,
            name=self.file_path.name,
            format=DatasetFormat.TEXT_ASCII,
            source_type="local",
            file_path=str(self.file_path.resolve()),
            file_size_bytes=file_size,
            dimensions={"y": nrows, "x": ncols},
            coordinates={},
            variables=variables_info,
            default_variable=var_name,
            time_axis=TimeAxisInfo(timestamps=["static"], resolution="single", count=1),
            spatial_extent=self._extent,
            metadata=header
        )
        return self._dataset_info

    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        if self._grid_data is None:
            self.inspect()

        raw_data = np.array(self._grid_data, copy=True)
        if self._nodata is not None:
            raw_data[raw_data == self._nodata] = np.nan
        raw_data[~np.isfinite(raw_data)] = np.nan

        nrows, ncols = raw_data.shape
        lat_coords = np.linspace(self._extent.north, self._extent.south, nrows, endpoint=True, dtype=np.float32)
        lon_coords = np.linspace(self._extent.west, self._extent.east, ncols, endpoint=True, dtype=np.float32)

        norm_data, norm_lat, norm_lon, extent = normalize_grid_to_wgs84(
            raw_data, lat_coords, lon_coords
        )

        mask = np.isnan(norm_data)
        valid = norm_data[~mask]
        min_v = float(np.min(valid)) if len(valid) > 0 else 0.0
        max_v = float(np.max(valid)) if len(valid) > 0 else 1.0

        return SliceData(
            data=norm_data,
            lat_coords=norm_lat,
            lon_coords=norm_lon,
            extent=extent,
            variable_name=var_name or self._dataset_info.default_variable,
            timestamp=None,
            time_index=0,
            units=None,
            min_val=min_v,
            max_val=max_v,
            mask=mask
        )

    def get_point_value(
        self,
        lat: float,
        lon: float,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> PointQueryResponse:
        frame = self.read_frame(var_name=var_name, time_index=time_index)
        y_idx, x_idx, m_lat, m_lon = find_nearest_cell(
            lat, lon, frame.lat_coords, frame.lon_coords
        )
        val = frame.data[y_idx, x_idx]
        is_valid = bool(np.isfinite(val) and not frame.mask[y_idx, x_idx])

        return PointQueryResponse(
            dataset_id=self.dataset_id,
            variable=frame.variable_name,
            units=frame.units,
            requested_lat=lat,
            requested_lon=lon,
            matched_lat=m_lat,
            matched_lon=m_lon,
            grid_index_y=y_idx,
            grid_index_x=x_idx,
            value=float(val) if is_valid else None,
            is_valid=is_valid,
            timestamp=frame.timestamp,
            time_index=time_index
        )
