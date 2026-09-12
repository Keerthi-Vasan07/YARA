"""
GeoTIFF Scientific Reader for YARA.
Supports single and multi-band GeoTIFFs using rasterio with WGS84 reprojection.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

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


class GeoTIFFReader(BaseScientificReader):
    """Reader for GeoTIFF raster datasets."""

    def __init__(self, file_path: Union[str, Path], dataset_id: Optional[str] = None):
        super().__init__(file_path, dataset_id)
        self._src: Optional[rasterio.DatasetReader] = None

    def _open(self) -> rasterio.DatasetReader:
        if self._src is None or self._src.closed:
            self._src = rasterio.open(str(self.file_path))
        return self._src

    def inspect(self) -> DatasetInfo:
        src = self._open()
        crs = src.crs
        bounds = src.bounds
        width = src.width
        height = src.height
        count = src.count

        # Reproject bounds to EPSG:4326 if not already
        if crs and not crs.is_epsg_code and crs.to_epsg() != 4326:
            from rasterio.warp import transform_bounds
            west, south, east, north = transform_bounds(crs, "EPSG:4326", bounds.left, bounds.bottom, bounds.right, bounds.top)
        else:
            west, south, east, north = bounds.left, bounds.bottom, bounds.right, bounds.top

        is_global = (east - west >= 355.0) and (north - south >= 160.0)
        extent = SpatialExtent(
            west=float(west),
            south=float(south),
            east=float(east),
            north=float(north),
            is_global=is_global
        )

        lat_coords = np.linspace(north, south, height, endpoint=True, dtype=np.float32)
        lon_coords = np.linspace(west, east, width, endpoint=True, dtype=np.float32)

        coordinates_info: Dict[str, CoordinateInfo] = {
            "latitude": CoordinateInfo(
                name="latitude",
                axis="Y",
                dim_name="y",
                size=height,
                min_val=float(south),
                max_val=float(north),
                units="degrees_north",
                is_ascending=False
            ),
            "longitude": CoordinateInfo(
                name="longitude",
                axis="X",
                dim_name="x",
                size=width,
                min_val=float(west),
                max_val=float(east),
                units="degrees_east",
                is_ascending=True
            )
        }

        variables_info: Dict[str, VariableInfo] = {}
        for b_idx in range(1, count + 1):
            var_name = f"band_{b_idx}" if count > 1 else self.file_path.stem
            nodata = src.nodatavals[b_idx - 1]
            variables_info[var_name] = VariableInfo(
                name=var_name,
                standard_name="raster_band",
                long_name=f"Raster Band {b_idx}",
                dimensions=["y", "x"],
                shape=[height, width],
                dtype=str(src.dtypes[b_idx - 1]),
                var_type=VariableType.SCALAR_GRID,
                fill_value=float(nodata) if nodata is not None else None,
                aliases=[var_name]
            )

        time_axis = TimeAxisInfo(
            dim_name=None,
            timestamps=["static"],
            resolution="single",
            count=1
        )

        file_size = 0
        try:
            file_size = self.file_path.stat().st_size
        except Exception:
            pass

        self._dataset_info = DatasetInfo(
            id=self.dataset_id,
            name=self.file_path.name,
            format=DatasetFormat.GEOTIFF,
            source_type="local",
            file_path=str(self.file_path.resolve()),
            file_size_bytes=file_size,
            dimensions={"y": height, "x": width, "bands": count},
            coordinates=coordinates_info,
            variables=variables_info,
            default_variable=list(variables_info.keys())[0],
            time_axis=time_axis,
            spatial_extent=extent,
            metadata={
                "driver": src.driver,
                "crs": str(src.crs),
                "transform": str(src.transform)
            }
        )
        return self._dataset_info

    def read_frame(
        self,
        var_name: Optional[str] = None,
        time_index: int = 0
    ) -> SliceData:
        if not self._dataset_info:
            self.inspect()

        src = self._open()
        band_idx = 1
        if var_name and var_name.startswith("band_"):
            try:
                band_idx = int(var_name.split("_")[1])
            except Exception:
                band_idx = 1

        raw_data = src.read(band_idx).astype(np.float32)
        nodata = src.nodatavals[band_idx - 1]
        if nodata is not None:
            raw_data[raw_data == nodata] = np.nan
        raw_data[~np.isfinite(raw_data)] = np.nan

        extent = self._dataset_info.spatial_extent
        lat_coords = np.linspace(extent.north, extent.south, src.height, endpoint=True, dtype=np.float32)
        lon_coords = np.linspace(extent.west, extent.east, src.width, endpoint=True, dtype=np.float32)

        norm_data, norm_lat, norm_lon, norm_extent = normalize_grid_to_wgs84(
            raw_data, lat_coords, lon_coords
        )

        mask = np.isnan(norm_data)
        valid = norm_data[~mask]
        min_val = float(np.min(valid)) if len(valid) > 0 else 0.0
        max_val = float(np.max(valid)) if len(valid) > 0 else 1.0

        return SliceData(
            data=norm_data,
            lat_coords=norm_lat,
            lon_coords=norm_lon,
            extent=norm_extent,
            variable_name=var_name or self._dataset_info.default_variable,
            timestamp=None,
            time_index=0,
            units=None,
            min_val=min_val,
            max_val=max_val,
            fill_value=float(nodata) if nodata is not None else None,
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

    def close(self):
        if self._src is not None and not self._src.closed:
            self._src.close()
            self._src = None
