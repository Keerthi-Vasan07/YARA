"""
SIC (Sea Ice Concentration) Downloader

Downloads Arctic + Antarctic sea ice concentration and merges them.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.enums import Resampling

from server.pipeline.downloaders.base import BaseDownloader
from server.pipeline.utils import compute_stats
from server.earthkit_integration import load_netcdf

logger = logging.getLogger(__name__)


# Separate dataset IDs for Arctic and Antarctic
SIC_DATASETS = {
    "nrt": {
        "arctic": "cmems_obs-si_arc_phy_nrt_l4_P1D",
        "antarctic": "cmems_obs-si_ant_phy_nrt_l3-1km_P1D",  # Only L3 available
    },
    "rep": {
        "arctic": "cmems_obs-si_arc_phy_my_l4_P1D",
        "antarctic": "cmems_obs-si_ant_phy_nrt_l3-1km_P1D",  # No MY for Antarctic, use NRT
    },
}


class SICDownloader(BaseDownloader):
    """Downloader for Sea Ice Concentration (merged Arctic + Antarctic)."""
    
    variable = "sic"
    
    def _download(self, date: str, stream: str, temp_dir: Path) -> Path | None:
        """Download Arctic and Antarctic SIC data."""
        datasets = SIC_DATASETS.get(stream, SIC_DATASETS["rep"])
        
        arctic_path = self._download_hemisphere("arctic", datasets["arctic"], date, temp_dir)
        antarctic_path = self._download_hemisphere("antarctic", datasets["antarctic"], date, temp_dir)
        
        if arctic_path is None and antarctic_path is None:
            logger.error("Both hemisphere downloads failed")
            return None
        
        # Return a marker path - actual files are in temp_dir
        return temp_dir / "hemispheres_downloaded"
    
    def _download_hemisphere(
        self,
        hemisphere: str,
        dataset_id: str,
        date: str,
        temp_dir: Path,
    ) -> Path | None:
        """Download SIC for one hemisphere."""
        output_file = temp_dir / f"sic_{hemisphere}_{date}.nc"
        
        # Set bbox and variable name based on hemisphere
        if hemisphere == "arctic":
            bbox = (-180, 50, 180, 90)  # North of 50°N
            var_name = "sic"  # L4 uses 'sic'
        else:
            bbox = (-180, -90, 180, -50)  # South of 50°S
            var_name = "ice_concentration"  # L3 uses 'ice_concentration'
        
        cmd = [
            "copernicusmarine", "subset",
            "--dataset-id", dataset_id,
            "--variable", var_name,
            "--start-datetime", f"{date}T00:00:00",
            "--end-datetime", f"{date}T23:59:59",
            "--minimum-longitude", str(bbox[0]),
            "--minimum-latitude", str(bbox[1]),
            "--maximum-longitude", str(bbox[2]),
            "--maximum-latitude", str(bbox[3]),
            "-o", str(temp_dir),
            "-f", output_file.name,
        ]
        
        logger.info(f"Downloading {hemisphere} SIC for {date}...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.warning(f"{hemisphere} download failed: {result.stderr[:200]}")
                return None
            
            if output_file.exists():
                return output_file
            
            # Check for any nc file
            nc_files = list(temp_dir.glob(f"*{hemisphere}*.nc"))
            if nc_files:
                return nc_files[0]
            
            return None
            
        except Exception as e:
            logger.warning(f"{hemisphere} download error: {e}")
            return None
    
    def _convert(self, nc_path: Path, cog_path: Path, date: str) -> dict[str, Any] | None:
        """Merge hemispheres and convert to global COG."""
        try:
            temp_dir = nc_path.parent
            
            # Target grid: 0.1° global
            target_lat = np.linspace(89.95, -89.95, 1800).astype(np.float32)
            target_lon = np.linspace(-179.95, 179.95, 3600).astype(np.float32)
            
            # Initialize global grid
            global_sic = np.full((1800, 3600), np.nan, dtype=np.float32)
            
            # Process each hemisphere
            for hemisphere in ["arctic", "antarctic"]:
                nc_files = list(temp_dir.glob(f"*{hemisphere}*.nc"))
                if not nc_files:
                    continue
                
                ds = load_netcdf(nc_files[0])
                
                # Get ice concentration - variable name varies by product
                var_name = None
                for name in ["sic", "ice_concentration", "ice_conc"]:
                    if name in ds:
                        var_name = name
                        break
                
                if var_name is None:
                    logger.warning(f"No ice concentration variable found in {hemisphere} file")
                    ds.close()
                    continue
                
                ice_conc = ds[var_name]
                if "time" in ice_conc.dims:
                    ice_conc = ice_conc.isel(time=0)
                
                # Get native coordinates
                if "xc" in ds and "yc" in ds:
                    # Polar stereographic - need to reproject
                    logger.info(f"Reprojecting {hemisphere} from polar stereographic...")
                    sic_global = self._reproject_polar(ds, hemisphere, target_lat, target_lon)
                else:
                    # Regular lat/lon grid
                    lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
                    lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
                    sic_data = ice_conc.values
                    
                    # Interpolate to target grid
                    sic_global = self._interpolate_to_global(
                        sic_data, lat, lon, target_lat, target_lon
                    )
                
                # Merge into global grid
                valid_mask = ~np.isnan(sic_global)
                global_sic[valid_mask] = sic_global[valid_mask]
                
                ds.close()
            
            # Compute stats
            stats = compute_stats(global_sic)
            
            # Convert to percentage (0-100) and encode as uint8
            # Some products use fraction (0-1), normalize
            if np.nanmax(global_sic) <= 1.1:
                global_sic = global_sic * 100
            
            sic_encoded = np.clip(global_sic, 0, 100).astype(np.uint8)
            sic_encoded[np.isnan(global_sic)] = 255  # nodata
            
            # Write COG
            cog_path.parent.mkdir(parents=True, exist_ok=True)
            
            height, width = sic_encoded.shape
            transform = from_bounds(-180, -90, 180, 90, width, height)
            
            profile = {
                "driver": "GTiff",
                "height": height,
                "width": width,
                "count": 1,
                "dtype": "uint8",
                "crs": CRS.from_epsg(4326),
                "transform": transform,
                "nodata": 255,
                "compress": "deflate",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
            
            with rasterio.open(cog_path, "w", **profile) as dst:
                dst.write(sic_encoded, 1)
                dst.update_tags(
                    variable="sic",
                    units="percent",
                    date=date,
                )
            
            # Build overviews
            with rasterio.open(cog_path, "r+") as dst:
                dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
            
            logger.info(f"Created SIC COG: {cog_path}")
            return stats
            
        except Exception as e:
            logger.error(f"SIC conversion error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _interpolate_to_global(
        self,
        data: np.ndarray,
        src_lat: np.ndarray,
        src_lon: np.ndarray,
        dst_lat: np.ndarray,
        dst_lon: np.ndarray,
    ) -> np.ndarray:
        """Interpolate data to global grid."""
        from scipy.interpolate import RegularGridInterpolator
        
        # Ensure monotonic coordinates
        if src_lat[0] < src_lat[-1]:
            data = np.flipud(data)
            src_lat = src_lat[::-1]
        
        # Create interpolator
        interp = RegularGridInterpolator(
            (src_lat[::-1], src_lon),  # Must be increasing
            np.flipud(data),
            method='linear',
            bounds_error=False,
            fill_value=np.nan,
        )
        
        # Create output grid
        dst_lon_grid, dst_lat_grid = np.meshgrid(dst_lon, dst_lat)
        points = np.column_stack([dst_lat_grid.ravel(), dst_lon_grid.ravel()])
        
        # Interpolate
        result = interp(points).reshape(len(dst_lat), len(dst_lon))
        return result
    
    def _reproject_polar(
        self,
        ds: xr.Dataset,
        hemisphere: str,
        dst_lat: np.ndarray,
        dst_lon: np.ndarray,
    ) -> np.ndarray:
        """Reproject polar stereographic to lat/lon."""
        import pyproj
        
        # Get data variable - name varies by product
        var_name = None
        for name in ["sic", "ice_concentration", "ice_conc"]:
            if name in ds:
                var_name = name
                break
        
        if var_name is None:
            raise ValueError("No ice concentration variable found")
        
        ice_conc = ds[var_name]
        if "time" in ice_conc.dims:
            ice_conc = ice_conc.isel(time=0)
        
        data = ice_conc.values
        xc = ds["xc"].values * 1000  # km to m
        yc = ds["yc"].values * 1000
        
        # Define projections
        if hemisphere == "arctic":
            polar_crs = pyproj.CRS.from_epsg(3411)  # NSIDC Sea Ice Polar Stereographic North
        else:
            polar_crs = pyproj.CRS.from_epsg(3412)  # NSIDC Sea Ice Polar Stereographic South
        
        geo_crs = pyproj.CRS.from_epsg(4326)
        transformer = pyproj.Transformer.from_crs(polar_crs, geo_crs, always_xy=True)
        
        # Create meshgrid of polar coordinates
        xc_grid, yc_grid = np.meshgrid(xc, yc)
        
        # Transform to lat/lon
        lons, lats = transformer.transform(xc_grid.ravel(), yc_grid.ravel())
        lons = lons.reshape(xc_grid.shape)
        lats = lats.reshape(yc_grid.shape)
        
        # Create output grid
        result = np.full((len(dst_lat), len(dst_lon)), np.nan, dtype=np.float32)
        
        # Simple nearest-neighbor mapping
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                if np.isnan(data[i, j]):
                    continue
                
                lat_idx = np.argmin(np.abs(dst_lat - lats[i, j]))
                lon_idx = np.argmin(np.abs(dst_lon - lons[i, j]))
                
                if not np.isnan(data[i, j]):
                    result[lat_idx, lon_idx] = data[i, j]
        
        return result
