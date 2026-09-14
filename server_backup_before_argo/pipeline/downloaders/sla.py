"""
SLA (Sea Level Anomaly) Downloader

Downloads DUACS L4 altimetry data from Copernicus Marine.
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


class SLADownloader(BaseDownloader):
    """Downloader for Sea Level Anomaly (DUACS L4)."""
    
    variable = "sla"
    
    def _download(self, date: str, stream: str, temp_dir: Path) -> Path | None:
        """Download SLA data."""
        dataset_id = (
            self.var_config.nrt_dataset_id if stream == "nrt"
            else self.var_config.rep_dataset_id
        )
        
        if not dataset_id:
            logger.error(f"No dataset ID for stream: {stream}")
            return None
        
        return download_cmems_subset(
            dataset_id=dataset_id,
            variables=["sla", "adt", "ugos", "vgos"],  # SLA + ADT + currents
            date=date,
            output_dir=temp_dir,
        )
    
    def _convert(self, nc_path: Path, cog_path: Path, date: str) -> dict[str, Any] | None:
        """Convert SLA NetCDF to COG."""
        try:
            ds = load_netcdf(nc_path, variables=["sla", "adt", "ugos", "vgos"])
            
            # Get SLA data
            sla = ds["sla"]
            if "time" in sla.dims:
                sla = sla.isel(time=0)
            
            sla_data = sla.values.astype(np.float32)
            
            # Get coordinates
            lat = ds["latitude"].values if "latitude" in ds else ds["lat"].values
            lon = ds["longitude"].values if "longitude" in ds else ds["lon"].values
            
            # Ensure north-to-south
            if lat[0] < lat[-1]:
                sla_data = np.flipud(sla_data)
                lat = lat[::-1]
            
            # Compute stats in meters
            stats = compute_stats(sla_data)
            
            # Encode as int16 with 1mm precision (0.001m scale)
            nodata = -32768
            scale = 0.001
            sla_encoded = np.round(sla_data / scale).astype(np.int16)
            sla_encoded[np.isnan(sla_data)] = nodata
            
            # Calculate bounds
            lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.25
            lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.25
            
            west = float(lon.min() - lon_res / 2)
            east = float(lon.max() + lon_res / 2)
            north = float(lat.max() + lat_res / 2)
            south = float(lat.min() - lat_res / 2)
            
            height, width = sla_encoded.shape
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
                dst.write(sla_encoded, 1)
                dst.update_tags(
                    variable="sla",
                    units="m",
                    scale_factor="0.001",
                    date=date,
                )
            
            # Build overviews
            with rasterio.open(cog_path, "r+") as dst:
                dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")
            
            ds.close()
            logger.info(f"Created SLA COG: {cog_path}")
            return stats
            
        except Exception as e:
            logger.error(f"SLA conversion error: {e}")
            import traceback
            traceback.print_exc()
            return None
