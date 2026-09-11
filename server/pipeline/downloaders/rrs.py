"""
Rrs (Remote Sensing Reflectance) RGB Downloader

Downloads L3 Rrs data for blue/green/red bands and creates RGB composite.
Note: L3 data has gaps (no L4 gap-free product exists for Rrs).
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.enums import Resampling

from server.pipeline.downloaders.base import BaseDownloader
from server.pipeline.utils import download_cmems_subset
from server.earthkit_integration import load_netcdf

logger = logging.getLogger(__name__)

# Spectral bands for RGB composite
RRS_BANDS = {
    "red": "RRS670",    # 670nm
    "green": "RRS555",  # 555nm  
    "blue": "RRS443",   # 443nm
}

# Scaling factors for visualization
# Typical ocean Rrs ranges from 0 to ~0.02 sr^-1
RRS_MIN = 0.0
RRS_MAX = 0.015  # sr^-1 (captures most open ocean values)


def normalize_rrs(data: np.ndarray, min_val: float = RRS_MIN, max_val: float = RRS_MAX) -> np.ndarray:
    """Normalize Rrs to 0-255 for visualization."""
    # Clip to valid range
    clipped = np.clip(data, min_val, max_val)
    # Normalize to 0-255
    normalized = ((clipped - min_val) / (max_val - min_val) * 255).astype(np.uint8)
    return normalized


class RrsDownloader(BaseDownloader):
    """Downloader for Remote Sensing Reflectance RGB composite."""
    
    variable = "rrs"
    
    def _download(self, date: str, stream: str, temp_dir: Path) -> Path | None:
        """Download Rrs data for all RGB bands."""
        dataset_id = (
            self.var_config.nrt_dataset_id if stream == "nrt"
            else self.var_config.rep_dataset_id
        )
        
        if not dataset_id:
            logger.error(f"No dataset ID for stream: {stream}")
            return None
        
        # Download all three bands
        return download_cmems_subset(
            dataset_id=dataset_id,
            variables=list(RRS_BANDS.values()),
            date=date,
            output_dir=temp_dir,
        )
    
    def _convert(self, nc_path: Path, cog_path: Path, date: str) -> dict[str, Any] | None:
        """Convert Rrs NetCDF to RGBA COG."""
        try:
            ds = load_netcdf(nc_path, variables=list(RRS_BANDS.values()))
            
            # Find available variables (case insensitive)
            var_map = {}
            for color, expected in RRS_BANDS.items():
                for v in ds.data_vars:
                    if v.upper() == expected.upper():
                        var_map[color] = v
                        break
            
            if len(var_map) < 3:
                missing = set(RRS_BANDS.keys()) - set(var_map.keys())
                logger.error(f"Missing Rrs bands: {missing}. Available: {list(ds.data_vars)}")
                return None
            
            # Load each band
            bands = {}
            for color, var_name in var_map.items():
                band = ds[var_name]
                if "time" in band.dims:
                    band = band.isel(time=0)
                bands[color] = band.values.astype(np.float32)
            
            # Get coordinates
            lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
            lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
            
            # Ensure north-to-south
            if lat[0] < lat[-1]:
                for color in bands:
                    bands[color] = np.flipud(bands[color])
                lat = lat[::-1]
            
            # Create RGBA array
            height, width = bands["red"].shape
            rgba = np.zeros((4, height, width), dtype=np.uint8)
            
            # Create valid mask (where all bands have data)
            valid_mask = np.ones((height, width), dtype=bool)
            for color in bands:
                valid_mask &= ~np.isnan(bands[color])
            
            # Normalize each band to 0-255
            rgba[0] = normalize_rrs(np.nan_to_num(bands["red"], nan=0))
            rgba[1] = normalize_rrs(np.nan_to_num(bands["green"], nan=0))
            rgba[2] = normalize_rrs(np.nan_to_num(bands["blue"], nan=0))
            
            # Alpha channel: 255 where valid, 0 where NaN
            rgba[3] = np.where(valid_mask, 255, 0).astype(np.uint8)
            
            # Compute stats for all bands
            stats = {
                "red_mean": float(np.nanmean(bands["red"])),
                "green_mean": float(np.nanmean(bands["green"])),
                "blue_mean": float(np.nanmean(bands["blue"])),
                "valid_pixels": int(valid_mask.sum()),
                "total_pixels": int(height * width),
                "coverage_pct": float(valid_mask.sum() / (height * width) * 100),
            }
            
            # Calculate bounds
            lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
            lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
            
            west = float(lon.min() - lon_res / 2)
            east = float(lon.max() + lon_res / 2)
            north = float(lat.max() + lat_res / 2)
            south = float(lat.min() - lat_res / 2)
            
            transform = from_bounds(west, south, east, north, width, height)
            
            # Write RGBA COG
            cog_path.parent.mkdir(parents=True, exist_ok=True)
            
            profile = {
                "driver": "GTiff",
                "height": height,
                "width": width,
                "count": 4,
                "dtype": "uint8",
                "crs": CRS.from_epsg(4326),
                "transform": transform,
                "compress": "deflate",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "photometric": "RGBA",
            }
            
            with rasterio.open(cog_path, "w", **profile) as dst:
                dst.write(rgba)
                dst.update_tags(
                    variable="rrs_rgb",
                    units="sr-1",
                    date=date,
                    red_band="RRS670",
                    green_band="RRS555",
                    blue_band="RRS443",
                    scale_min=str(RRS_MIN),
                    scale_max=str(RRS_MAX),
                )
            
            # Build overviews
            with rasterio.open(cog_path, "r+") as dst:
                dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")
            
            ds.close()
            logger.info(f"Created Rrs RGB COG: {cog_path} (coverage: {stats['coverage_pct']:.1f}%)")
            return stats
            
        except Exception as e:
            logger.error(f"Rrs conversion error: {e}")
            import traceback
            traceback.print_exc()
            return None
