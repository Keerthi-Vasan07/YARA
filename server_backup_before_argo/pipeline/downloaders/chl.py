"""
CHL (Chlorophyll-a) Downloader

Downloads L4 gap-free chlorophyll data from Copernicus Marine.
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
from server.pipeline.utils import download_cmems_subset, compute_stats
from server.earthkit_integration import load_netcdf

logger = logging.getLogger(__name__)


class CHLDownloader(BaseDownloader):
    """Downloader for Chlorophyll-a Concentration (L4 gap-free)."""
    
    variable = "chl"
    
    def _download(self, date: str, stream: str, temp_dir: Path) -> Path | None:
        """Download CHL data."""
        dataset_id = (
            self.var_config.nrt_dataset_id if stream == "nrt"
            else self.var_config.rep_dataset_id
        )
        
        if not dataset_id:
            logger.error(f"No dataset ID for stream: {stream}")
            return None
        
        return download_cmems_subset(
            dataset_id=dataset_id,
            variables=["CHL"],
            date=date,
            output_dir=temp_dir,
        )
    
    def _convert(self, nc_path: Path, cog_path: Path, date: str) -> dict[str, Any] | None:
        """Convert CHL NetCDF to COG."""
        try:
            ds = load_netcdf(nc_path, variables=["CHL"])
            
            # Find CHL variable (case insensitive)
            chl_var = None
            for v in ds.data_vars:
                if v.upper() == "CHL":
                    chl_var = v
                    break
            
            if chl_var is None:
                logger.error(f"CHL variable not found. Available: {list(ds.data_vars)}")
                return None
            
            chl = ds[chl_var]
            if "time" in chl.dims:
                chl = chl.isel(time=0)
            
            chl_data = chl.values.astype(np.float32)
            
            # Get coordinates
            lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
            lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
            
            # Ensure north-to-south
            if lat[0] < lat[-1]:
                chl_data = np.flipud(chl_data)
                lat = lat[::-1]
            
            # Compute stats
            stats = compute_stats(chl_data)
            
            # Keep as float32 (log-scale visualization)
            # NaN for nodata
            
            # Calculate bounds
            lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
            lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
            
            west = float(lon.min() - lon_res / 2)
            east = float(lon.max() + lon_res / 2)
            north = float(lat.max() + lat_res / 2)
            south = float(lat.min() - lat_res / 2)
            
            height, width = chl_data.shape
            transform = from_bounds(west, south, east, north, width, height)
            
            # Write COG
            cog_path.parent.mkdir(parents=True, exist_ok=True)
            
            profile = {
                "driver": "GTiff",
                "height": height,
                "width": width,
                "count": 1,
                "dtype": "float32",
                "crs": CRS.from_epsg(4326),
                "transform": transform,
                "nodata": float("nan"),
                "compress": "deflate",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "predictor": 2,
            }
            
            with rasterio.open(cog_path, "w", **profile) as dst:
                dst.write(chl_data, 1)
                dst.update_tags(
                    variable="chl",
                    units="mg/m3",
                    date=date,
                )
            
            # Build overviews
            with rasterio.open(cog_path, "r+") as dst:
                dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")
            
            ds.close()
            logger.info(f"Created CHL COG: {cog_path}")
            return stats
            
        except Exception as e:
            logger.error(f"CHL conversion error: {e}")
            import traceback
            traceback.print_exc()
            return None
