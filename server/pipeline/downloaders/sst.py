"""
SST (Sea Surface Temperature) Downloader

Downloads L4 OSTIA SST from Copernicus Marine.
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
from server.earthkit_integration import load_netcdf, kelvin_to_celsius

logger = logging.getLogger(__name__)


class SSTDownloader(BaseDownloader):
    """Downloader for Sea Surface Temperature (OSTIA L4)."""
    
    variable = "sst"
    
    def _download(self, date: str, stream: str, temp_dir: Path) -> Path | None:
        """Download SST data."""
        dataset_id = (
            self.var_config.nrt_dataset_id if stream == "nrt"
            else self.var_config.rep_dataset_id
        )
        
        if not dataset_id:
            logger.error(f"No dataset ID for stream: {stream}")
            return None
        
        return download_cmems_subset(
            dataset_id=dataset_id,
            variables=["analysed_sst", "analysis_error"],
            date=date,
            output_dir=temp_dir,
        )
    
    def _convert(self, nc_path: Path, cog_path: Path, date: str) -> dict[str, Any] | None:
        """Convert SST NetCDF to COG."""
        try:
            ds = load_netcdf(nc_path, variables=["analysed_sst", "analysis_error"])
            
            # Get SST data
            sst = ds["analysed_sst"]
            if "time" in sst.dims:
                sst = sst.isel(time=0)
            
            # Convert from Kelvin to Celsius
            sst_c = kelvin_to_celsius(sst).values
            
            # Get coordinates
            lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
            lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
            
            # Ensure north-to-south
            if lat[0] < lat[-1]:
                sst_c = np.flipud(sst_c)
                lat = lat[::-1]
            
            # Compute stats in Celsius
            stats = compute_stats(sst_c)
            
            # Encode as int16 with 0.01°C precision
            nodata = -32768
            scale = 0.01
            sst_encoded = np.round(sst_c / scale).astype(np.int16)
            sst_encoded[np.isnan(sst_c)] = nodata
            
            # Calculate bounds
            lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
            lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
            
            west = float(lon.min() - lon_res / 2)
            east = float(lon.max() + lon_res / 2)
            north = float(lat.max() + lat_res / 2)
            south = float(lat.min() - lat_res / 2)
            
            height, width = sst_encoded.shape
            transform = from_bounds(west, south, east, north, width, height)
            
            # Write COG
            cog_path.parent.mkdir(parents=True, exist_ok=True)
            
            profile = {
                "driver": "GTiff",
                "height": height,
                "width": width,
                "count": 1,
                "dtype": "int16",
                "crs": CRS.from_epsg(4326),
                "transform": transform,
                "nodata": nodata,
                "compress": "deflate",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "predictor": 2,
            }
            
            with rasterio.open(cog_path, "w", **profile) as dst:
                dst.write(sst_encoded, 1)
                dst.update_tags(
                    variable="sst",
                    units="degC",
                    scale_factor="0.01",
                    date=date,
                )
            
            # Build overviews
            with rasterio.open(cog_path, "r+") as dst:
                dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")
            
            ds.close()
            logger.info(f"Created SST COG: {cog_path}")
            return stats
            
        except Exception as e:
            logger.error(f"SST conversion error: {e}")
            import traceback
            traceback.print_exc()
            return None
