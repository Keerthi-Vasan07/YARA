"""
GeoTIFF Reader.

Reads GeoTIFF raster files with geospatial metadata.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np

try:
    import rasterio
    from rasterio.crs import CRS
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

from .base_reader import BaseReader
from .common_model import Variable, CoordinateModel

logger = logging.getLogger(__name__)


class GeoTIFFReader(BaseReader):
    """
    Reader for GeoTIFF files (.tif, .tiff).
    
    Requires rasterio package.
    """
    
    def __init__(self, path: str):
        if not HAS_RASTERIO:
            raise ImportError("rasterio package required for GeoTIFF support")
        
        super().__init__(path)
        self._dataset = None
    
    def _open(self):
        """Open GeoTIFF file."""
        if self._dataset is None:
            try:
                self._dataset = rasterio.open(self.path)
                logger.info(f"[GeoTIFF] Opened: {self.path}")
            except Exception as e:
                logger.error(f"[GeoTIFF] Failed to open {self.path}: {e}")
                raise
        return self._dataset
    
    def inspect(self) -> Dict[str, Any]:
        """Inspect the file."""
        try:
            ds = self._open()
            return {
                'format': 'geotiff',
                'path': self.path,
                'width': ds.width,
                'height': ds.height,
                'bands': ds.count,
                'crs': str(ds.crs),
                'dtype': ds.dtypes[0] if ds.count > 0 else None,
            }
        except Exception as e:
            return {'format': 'geotiff', 'path': self.path, 'error': str(e)}
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata."""
        return self.inspect()
    
    def get_variables(self) -> List[Variable]:
        """Get variables (bands)."""
        try:
            ds = self._open()
            variables = []
            
            for i in range(ds.count):
                band_name = f'band_{i+1}'
                desc = ds.descriptions[i] if ds.descriptions else None
                
                variables.append(Variable(
                    name=band_name,
                    long_name=desc or band_name,
                    units=None,
                    dimensions=['y', 'x'],
                    dtype=ds.dtypes[i],
                ))
            
            return variables
        except Exception:
            return []
    
    def get_dimensions(self) -> Dict[str, int]:
        """Get dimensions."""
        try:
            ds = self._open()
            return {
                'y': ds.height,
                'x': ds.width,
            }
        except Exception:
            return {}
    
    def get_coordinates(self) -> CoordinateModel:
        """Extract coordinates from geotransform."""
        try:
            ds = self._open()
            
            # Get geotransform
            transform = ds.transform
            
            # Generate coordinate arrays
            lon_min = transform[2]  # top-left x
            lat_max = transform[5]  # top-left y
            pixel_width = transform[0]
            pixel_height = transform[4]  # usually negative
            
            # Create 1D coordinate arrays
            longitude = np.linspace(lon_min, lon_min + pixel_width * ds.width, ds.width)
            latitude = np.linspace(lat_max, lat_max + pixel_height * ds.height, ds.height)
            
            # Handle CRS transformation if needed
            if ds.crs and ds.crs.to_epsg() != 4326:
                # Transform to WGS84
                from rasterio.warp import calculate_default_transform, transform_bounds
                
                bounds = ds.bounds
                left, bottom, right, top = transform_bounds(
                    ds.crs, CRS.from_epsg(4326),
                    bounds.left, bounds.bottom, bounds.right, bounds.top
                )
                
                longitude = np.linspace(left, right, ds.width)
                latitude = np.linspace(bottom, top, ds.height)
            
            return CoordinateModel(
                latitude=latitude.astype(np.float64),
                longitude=longitude.astype(np.float64),
                lat_min=float(np.min(latitude)),
                lat_max=float(np.max(latitude)),
                lon_min=float(np.min(longitude)),
                lon_max=float(np.max(longitude)),
            )
        except Exception as e:
            logger.warning(f"[GeoTIFF] Could not extract coordinates: {e}")
            return CoordinateModel()
    
    def get_time_axis(self) -> List[str]:
        """Get time axis from metadata."""
        try:
            ds = self._open()
            
            # Check for time in metadata
            tags = ds.tags()
            for key in ['DateTime', 'GRIB_VALID_TIME', 'time']:
                if key in tags:
                    return [tags[key]]
            
            return []
        except Exception:
            return []
    
    def read_data(self, variable_name: str, time_index: Optional[int] = None) -> np.ndarray:
        """Read data (first band by default)."""
        ds = self._open()
        
        # Parse band index from variable name
        band_idx = 1  # Default to first band
        if variable_name.startswith('band_'):
            try:
                band_idx = int(variable_name.split('_')[1])
            except (ValueError, IndexError):
                pass
        
        if band_idx < 1 or band_idx > ds.count:
            band_idx = 1
        
        data = ds.read(band_idx)
        return data.astype(np.float32)
    
    def read_subset(
        self,
        variable_name: str,
        lat_slice: Optional[slice] = None,
        lon_slice: Optional[slice] = None,
        time_index: Optional[int] = None,
        depth_index: Optional[int] = None,
    ) -> np.ndarray:
        """Read subset using window."""
        ds = self._open()
        
        band_idx = 1
        if variable_name.startswith('band_'):
            try:
                band_idx = int(variable_name.split('_')[1])
            except (ValueError, IndexError):
                pass
        
        # Build window
        from rasterio.windows import Window
        
        row_off = lat_slice.start if lat_slice else 0
        col_off = lon_slice.start if lon_slice else 0
        height = (lat_slice.stop - lat_slice.start) if lat_slice else ds.height
        width = (lon_slice.stop - lon_slice.start) if lon_slice else ds.width
        
        window = Window(col_off, row_off, width, height)
        data = ds.read(band_idx, window=window)
        
        return data.astype(np.float32)
    
    def close(self) -> None:
        """Close."""
        if self._dataset is not None:
            self._dataset.close()
            self._dataset = None
            logger.info(f"[GeoTIFF] Closed: {self.path}")
