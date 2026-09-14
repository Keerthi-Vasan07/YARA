"""
Pipeline Utilities

Shared functions for downloading, converting, and processing ECV data.
"""

import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.enums import Resampling

from server.pipeline.config import get_config, VariableConfig

logger = logging.getLogger(__name__)


def download_cmems_subset(
    dataset_id: str,
    variables: list[str],
    date: str,
    output_dir: Path,
    bbox: tuple[float, float, float, float] = (-180, -90, 180, 90),
    timeout: int | None = None,
) -> Path | None:
    """
    Download data from Copernicus Marine Service using CLI.
    
    Args:
        dataset_id: CMEMS dataset identifier
        variables: List of variable names to download
        date: Date string (YYYY-MM-DD)
        output_dir: Directory for output file
        bbox: Bounding box (west, south, east, north)
        timeout: Download timeout in seconds
        
    Returns:
        Path to downloaded NetCDF file, or None on failure
    """
    config = get_config()
    timeout = timeout or config.download_timeout
    
    output_file = output_dir / f"{dataset_id}_{date}.nc"
    
    # Build command
    cmd = [
        "copernicusmarine", "subset",
        "--dataset-id", dataset_id,
        "--start-datetime", f"{date}T00:00:00",
        "--end-datetime", f"{date}T23:59:59",
        "--minimum-longitude", str(bbox[0]),
        "--minimum-latitude", str(bbox[1]),
        "--maximum-longitude", str(bbox[2]),
        "--maximum-latitude", str(bbox[3]),
        "-o", str(output_dir),
        "-f", output_file.name,
        "--force-download",
    ]
    
    # Add variables
    for var in variables:
        cmd.extend(["--variable", var])
    
    logger.info(f"Downloading {dataset_id} for {date}...")
    logger.debug(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        if result.returncode != 0:
            logger.error(f"Download failed: {result.stderr}")
            return None
        
        # Check if file was created
        if output_file.exists():
            logger.info(f"Downloaded: {output_file}")
            return output_file
        
        # Sometimes output has different name
        nc_files = list(output_dir.glob("*.nc"))
        if nc_files:
            return nc_files[0]
        
        logger.error("No output file found after download")
        return None
        
    except subprocess.TimeoutExpired:
        logger.error(f"Download timed out after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


def netcdf_to_cog(
    nc_path: Path,
    cog_path: Path,
    variable: str,
    var_config: VariableConfig,
) -> dict[str, Any] | None:
    """
    Convert NetCDF to Cloud-Optimized GeoTIFF.
    
    Args:
        nc_path: Path to input NetCDF
        cog_path: Path to output COG
        variable: Variable name
        var_config: Variable configuration
        
    Returns:
        Statistics dict, or None on failure
    """
    config = get_config()
    
    try:
        ds = xr.open_dataset(nc_path)
        
        # Get data variable
        data_var = var_config.data_variable
        if data_var not in ds.data_vars:
            # Try case-insensitive match
            for v in ds.data_vars:
                if v.lower() == data_var.lower():
                    data_var = v
                    break
            else:
                logger.error(f"Variable {data_var} not found. Available: {list(ds.data_vars)}")
                return None
        
        data = ds[data_var]
        
        # Squeeze time dimension
        if "time" in data.dims:
            data = data.isel(time=0)
        
        # Get data as numpy array
        arr = data.values.astype(np.float32)
        
        # Get coordinates
        lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
        lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
        
        # Ensure north-to-south orientation
        if lat[0] < lat[-1]:
            arr = np.flipud(arr)
            lat = lat[::-1]
        
        # Apply encoding based on variable type
        encoded, nodata = encode_data(arr, var_config)
        
        # Compute statistics before encoding
        stats = compute_stats(arr)
        
        # Calculate bounds
        lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
        lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
        
        west = float(lon.min() - lon_res / 2)
        east = float(lon.max() + lon_res / 2)
        north = float(lat.max() + lat_res / 2)
        south = float(lat.min() - lat_res / 2)
        
        height, width = encoded.shape
        transform = from_bounds(west, south, east, north, width, height)
        
        # Write COG
        cog_path.parent.mkdir(parents=True, exist_ok=True)
        
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": encoded.dtype,
            "crs": CRS.from_epsg(4326),
            "transform": transform,
            "nodata": nodata,
            "compress": config.cog_compress,
            "tiled": True,
            "blockxsize": config.cog_blocksize,
            "blockysize": config.cog_blocksize,
        }
        
        # Add predictor for integer types
        if encoded.dtype in [np.int16, np.int32, np.uint8, np.uint16]:
            profile["predictor"] = 2
        
        with rasterio.open(cog_path, "w", **profile) as dst:
            dst.write(encoded, 1)
            dst.update_tags(
                variable=variable,
                units=var_config.unit,
                scale_factor=str(var_config.scale),
            )
        
        # Build overviews
        with rasterio.open(cog_path, "r+") as dst:
            dst.build_overviews(config.overview_levels, Resampling.average)
            dst.update_tags(ns="rio_overview", resampling="average")
        
        ds.close()
        
        logger.info(f"Created COG: {cog_path}")
        return stats
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        import traceback
        traceback.print_exc()
        return None


def encode_data(arr: np.ndarray, var_config: VariableConfig) -> tuple[np.ndarray, Any]:
    """
    Encode data array according to variable configuration.
    
    Returns:
        (encoded_array, nodata_value)
    """
    if var_config.dtype == "int16":
        # Scale and convert to int16
        nodata = -32768
        encoded = np.round(arr / var_config.scale).astype(np.int16)
        encoded[np.isnan(arr)] = nodata
        return encoded, nodata
    
    elif var_config.dtype == "uint8":
        # Convert to uint8 (0-255 scale)
        nodata = 255
        # Clip to valid range
        encoded = np.clip(arr, 0, 100).astype(np.uint8)
        encoded[np.isnan(arr)] = nodata
        return encoded, nodata
    
    else:
        # Keep as float32
        nodata = np.nan
        encoded = arr.astype(np.float32)
        return encoded, nodata


def compute_stats(arr: np.ndarray) -> dict[str, Any]:
    """Compute statistics for a data array."""
    valid = ~np.isnan(arr)
    valid_count = int(np.sum(valid))
    total_count = arr.size
    
    if valid_count == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "valid_fraction": 0.0,
            "valid_pixels": 0,
        }
    
    valid_data = arr[valid]
    return {
        "min": float(np.min(valid_data)),
        "max": float(np.max(valid_data)),
        "mean": float(np.mean(valid_data)),
        "std": float(np.std(valid_data)),
        "valid_fraction": float(valid_count / total_count),
        "valid_pixels": valid_count,
    }


def get_available_dates(variable: str) -> list[str]:
    """Get list of available dates for a variable from existing COGs."""
    config = get_config()
    cog_dir = config.products_dir / variable
    
    if not cog_dir.exists():
        return []
    
    dates = []
    for cog_path in sorted(cog_dir.glob("*.tif")):
        date_str = cog_path.stem
        # Validate date format
        try:
            from datetime import datetime
            datetime.strptime(date_str, "%Y-%m-%d")
            dates.append(date_str)
        except ValueError:
            continue
    
    return dates


def date_exists(variable: str, date: str) -> bool:
    """Check if a date already exists for a variable."""
    config = get_config()
    cog_path = config.get_cog_path(variable, date)
    return cog_path.exists()


def cleanup_temp_files(temp_dir: Path):
    """Clean up temporary files."""
    import shutil
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
