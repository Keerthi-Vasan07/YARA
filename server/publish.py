"""
COG Publisher for Ocean ECV data.

Converts NetCDF source files to Cloud-Optimized GeoTIFFs with:
- Numeric data preservation (no pre-colorization)
- QC-based masking
- Proper nodata handling
- Internal tiling + overviews for efficient tile serving
"""

import json
import logging
from pathlib import Path
from typing import Optional
import numpy as np
import xarray as xr
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load dataset configuration
DATASETS_CONFIG = Path(__file__).parent / "datasets.json"


def load_datasets_config() -> dict:
    """Load the datasets configuration."""
    with open(DATASETS_CONFIG) as f:
        return json.load(f)


def kelvin_to_celsius(data: np.ndarray) -> np.ndarray:
    """Convert temperature from Kelvin to Celsius."""
    return data - 273.15


def apply_sst_qc_mask(
    data: xr.DataArray, 
    quality: xr.DataArray, 
    min_quality: int = 4
) -> np.ndarray:
    """
    Apply QC mask to SST data.
    
    Args:
        data: SST data array (in Kelvin)
        quality: Quality level array (0-5)
        min_quality: Minimum acceptable quality level (4 = acceptable, 5 = best)
    
    Returns:
        Masked SST data in Celsius as float32
    """
    # Convert to numpy
    sst_values = data.values.astype(np.float32)
    qc_values = quality.values
    
    # Convert Kelvin to Celsius
    sst_celsius = kelvin_to_celsius(sst_values)
    
    # Apply QC mask - set invalid pixels to NaN
    sst_celsius[qc_values < min_quality] = np.nan
    
    return sst_celsius


def apply_chl_mask(data: xr.DataArray) -> np.ndarray:
    """
    Apply mask to CHL data.
    
    CHL uses NaN for invalid pixels (cloud, land, glint).
    We just ensure the data is float32.
    
    Args:
        data: CHL data array (in mg/m³)
    
    Returns:
        CHL data as float32 with NaN for invalid pixels
    """
    return data.values.astype(np.float32)


def encode_sst_int16(data: np.ndarray, scale: float = 0.01) -> tuple[np.ndarray, dict]:
    """
    Encode SST data as int16 with scale factor.
    
    Args:
        data: SST in Celsius as float32
        scale: Scale factor (0.01 = 0.01°C precision)
    
    Returns:
        Tuple of (encoded int16 array, metadata dict)
    """
    nodata = -32768
    
    # Scale and convert
    scaled = data / scale
    
    # Clamp to int16 range (excluding nodata)
    scaled = np.clip(scaled, -32767, 32767)
    
    # Convert to int16, preserving NaN as nodata
    encoded = np.where(np.isnan(data), nodata, scaled.astype(np.int16))
    
    return encoded.astype(np.int16), {
        "scale": scale,
        "offset": 0.0,
        "nodata": nodata,
        "units": "degrees_C",
        "dtype": "int16"
    }


def write_cog(
    data: np.ndarray,
    output_path: Path,
    bounds: tuple[float, float, float, float],
    nodata: float | int,
    dtype: str = "float32",
    compress: str = "deflate",
    blocksize: int = 512
) -> Path:
    """
    Write data as a Cloud-Optimized GeoTIFF.
    
    Args:
        data: 2D numpy array (y, x)
        output_path: Output file path
        bounds: (west, south, east, north) in EPSG:4326
        nodata: Nodata value
        dtype: Output data type
        compress: Compression algorithm
        blocksize: Internal tile size
    
    Returns:
        Path to written COG
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    height, width = data.shape
    west, south, east, north = bounds
    
    transform = from_bounds(west, south, east, north, width, height)
    
    # COG profile
    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "width": width,
        "height": height,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": transform,
        "nodata": nodata,
        "compress": compress,
        "tiled": True,
        "blockxsize": blocksize,
        "blockysize": blocksize,
        "interleave": "band",
        # COG-specific options
        "BIGTIFF": "IF_SAFER",
    }
    
    # Write with overviews for COG
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data, 1)
        
        # Build overviews
        overview_levels = [2, 4, 8, 16, 32]
        dst.build_overviews(overview_levels, rasterio.enums.Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
    
    logger.info(f"Written COG: {output_path} ({width}x{height}, {dtype})")
    return output_path


def publish_sst(
    nc_path: Path,
    output_path: Path,
    config: Optional[dict] = None,
    use_int16: bool = True
) -> dict:
    """
    Publish SST NetCDF as numeric COG.
    
    Args:
        nc_path: Path to input NetCDF file
        output_path: Path for output COG
        config: Dataset configuration (loaded from datasets.json if None)
        use_int16: If True, encode as int16 with scale factor
    
    Returns:
        Metadata dict with stats and encoding info
    """
    if config is None:
        config = load_datasets_config()["sst"]
    
    # Determine which stream config to use based on filename
    stream = "rep" if "_my_" in nc_path.name or "rep" in nc_path.name.lower() else "nrt"
    stream_config = config[stream]
    
    logger.info(f"Publishing SST from {nc_path} (stream={stream})")
    
    # Open dataset
    ds = xr.open_dataset(nc_path)
    
    # Get data and QC
    data_var = stream_config["variables"]["data"]
    qc_var = stream_config["variables"]["quality"]
    
    sst_data = ds[data_var].squeeze()  # Remove time dimension if present
    qc_data = ds[qc_var].squeeze()
    
    # Apply QC mask and convert to Celsius
    sst_celsius = apply_sst_qc_mask(sst_data, qc_data, min_quality=4)
    
    # Get bounds - handle both lon/lat and longitude/latitude naming
    lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
    lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
    
    # Handle coordinate order (data should be north-to-south for GeoTIFF)
    if lat[0] < lat[-1]:
        # Data is south-to-north, flip it
        sst_celsius = np.flipud(sst_celsius)
        lat = lat[::-1]
    
    bounds = (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))
    
    # Compute stats before encoding
    valid_mask = ~np.isnan(sst_celsius)
    stats = {
        "min": float(np.nanmin(sst_celsius)) if valid_mask.any() else None,
        "max": float(np.nanmax(sst_celsius)) if valid_mask.any() else None,
        "mean": float(np.nanmean(sst_celsius)) if valid_mask.any() else None,
        "valid_fraction": float(valid_mask.sum() / valid_mask.size),
        "bounds": bounds
    }
    
    # Encode and write
    if use_int16:
        encoded, encoding_meta = encode_sst_int16(sst_celsius)
        write_cog(
            encoded,
            output_path,
            bounds,
            nodata=encoding_meta["nodata"],
            dtype="int16"
        )
        stats["encoding"] = encoding_meta
    else:
        # Write as float32 with NaN nodata
        write_cog(
            sst_celsius,
            output_path,
            bounds,
            nodata=np.nan,
            dtype="float32"
        )
        stats["encoding"] = {"dtype": "float32", "nodata": "nan", "units": "degrees_C"}
    
    ds.close()
    
    return stats


def publish_chl(
    nc_path: Path,
    output_path: Path,
    config: Optional[dict] = None
) -> dict:
    """
    Publish CHL NetCDF as numeric COG.
    
    Args:
        nc_path: Path to input NetCDF file
        output_path: Path for output COG
        config: Dataset configuration (loaded from datasets.json if None)
    
    Returns:
        Metadata dict with stats
    """
    if config is None:
        config = load_datasets_config()["chl"]
    
    # Determine which stream config to use
    stream = "rep" if "_my_" in nc_path.name or "rep" in nc_path.name.lower() else "nrt"
    stream_config = config[stream]
    
    logger.info(f"Publishing CHL from {nc_path} (stream={stream})")
    
    # Open dataset
    ds = xr.open_dataset(nc_path)
    
    # Get data
    data_var = stream_config["variables"]["data"]
    chl_data = ds[data_var].squeeze()
    
    # Apply mask (CHL uses NaN for invalid)
    chl_values = apply_chl_mask(chl_data)
    
    # Get bounds - handle both lon/lat and longitude/latitude naming
    lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
    lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
    
    # Handle coordinate order
    if lat[0] < lat[-1]:
        chl_values = np.flipud(chl_values)
        lat = lat[::-1]
    
    bounds = (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))
    
    # Compute stats (in linear space, not log)
    valid_mask = ~np.isnan(chl_values) & (chl_values > 0)
    stats = {
        "min": float(np.nanmin(chl_values[valid_mask])) if valid_mask.any() else None,
        "max": float(np.nanmax(chl_values[valid_mask])) if valid_mask.any() else None,
        "mean": float(np.nanmean(chl_values[valid_mask])) if valid_mask.any() else None,
        "valid_fraction": float(valid_mask.sum() / valid_mask.size),
        "bounds": bounds,
        "encoding": {"dtype": "float32", "nodata": "nan", "units": "mg/m³"}
    }
    
    # Write as float32 (CHL values span several orders of magnitude)
    write_cog(
        chl_values,
        output_path,
        bounds,
        nodata=np.nan,
        dtype="float32"
    )
    
    ds.close()
    
    return stats


def publish_sst_l4(
    nc_path: Path,
    output_path: Path,
    use_int16: bool = True
) -> dict:
    """
    Publish L4 OSTIA SST NetCDF as numeric COG.
    
    L4 data is gap-filled analysis with full ocean coverage.
    
    Args:
        nc_path: Path to input NetCDF file (L4 OSTIA)
        output_path: Path for output COG
        use_int16: If True, encode as int16 with scale factor
    
    Returns:
        Metadata dict with stats and encoding info
    """
    logger.info(f"Publishing L4 SST from {nc_path}")
    
    # Open dataset
    ds = xr.open_dataset(nc_path)
    
    # Get data - L4 uses analysed_sst (Kelvin) and mask
    sst_kelvin = ds["analysed_sst"].squeeze().values.astype(np.float32)
    mask = ds["mask"].squeeze().values
    
    # Convert Kelvin to Celsius
    sst_celsius = sst_kelvin - 273.15
    
    # Apply mask - keep only open ocean (mask == 1)
    # Mask values: 1=open ocean, 2=land, 6=lake, 9=ice, 14=sea ice
    ocean_mask = (mask == 1)
    sst_celsius[~ocean_mask] = np.nan
    
    # Get bounds
    lon = ds["longitude"].values
    lat = ds["latitude"].values
    
    # Handle coordinate order (data should be north-to-south for GeoTIFF)
    if lat[0] < lat[-1]:
        sst_celsius = np.flipud(sst_celsius)
        lat = lat[::-1]
    
    bounds = (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))
    
    # Compute stats
    valid_mask = ~np.isnan(sst_celsius)
    stats = {
        "min": float(np.nanmin(sst_celsius)) if valid_mask.any() else None,
        "max": float(np.nanmax(sst_celsius)) if valid_mask.any() else None,
        "mean": float(np.nanmean(sst_celsius)) if valid_mask.any() else None,
        "valid_fraction": float(valid_mask.sum() / valid_mask.size),
        "bounds": bounds,
        "product": "L4 OSTIA",
        "source": "Met Office"
    }
    
    # Encode and write
    if use_int16:
        encoded, encoding_meta = encode_sst_int16(sst_celsius)
        write_cog(
            encoded,
            output_path,
            bounds,
            nodata=encoding_meta["nodata"],
            dtype="int16"
        )
        stats["encoding"] = encoding_meta
    else:
        write_cog(
            sst_celsius,
            output_path,
            bounds,
            nodata=np.nan,
            dtype="float32"
        )
        stats["encoding"] = {"dtype": "float32", "nodata": "nan", "units": "degrees_C"}
    
    ds.close()
    
    return stats


def publish_sic(
    nc_path: Path,
    output_path: Path,
    config: Optional[dict] = None
) -> dict:
    """
    Publish Sea Ice Concentration NetCDF as numeric COG.
    
    SIC data is stored as fraction (0-1), output as percentage (0-100).
    Uses uint8 encoding for efficiency: 0-100 values, 255=nodata.
    
    Args:
        nc_path: Path to input NetCDF file
        output_path: Path for output COG
        config: Dataset configuration (loaded from datasets.json if None)
    
    Returns:
        Metadata dict with stats
    """
    if config is None:
        config = load_datasets_config()["sic"]
    
    logger.info(f"Publishing SIC from {nc_path}")
    
    # Open dataset
    ds = xr.open_dataset(nc_path)
    
    # Get data variable - varies by product
    data_var = None
    for var in ["ice_conc", "siconc", "ice_concentration"]:
        if var in ds:
            data_var = var
            break
    
    if data_var is None:
        raise ValueError(f"Could not find ice concentration variable in {nc_path}")
    
    ice_data = ds[data_var].squeeze().values.astype(np.float32)
    
    # Convert from fraction to percentage if needed
    if np.nanmax(ice_data) <= 1.5:
        ice_data = ice_data * 100.0
    
    # Clamp to valid range
    ice_data = np.clip(ice_data, 0, 100)
    
    # Apply status flag mask if available
    if "status_flag" in ds:
        status = ds["status_flag"].squeeze().values
        # Mask out coast/bad data (status >= 20)
        ice_data[status >= 20] = np.nan
    
    # Get bounds
    lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
    lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
    
    # Handle 2D coordinate grids (polar stereographic)
    if lon.ndim == 2:
        west, east = float(lon.min()), float(lon.max())
        south, north = float(lat.min()), float(lat.max())
        bounds = (west, south, east, north)
    else:
        # Handle coordinate order
        if lat[0] < lat[-1]:
            ice_data = np.flipud(ice_data)
            lat = lat[::-1]
        bounds = (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))
    
    # Compute stats
    valid_mask = ~np.isnan(ice_data)
    stats = {
        "min": float(np.nanmin(ice_data)) if valid_mask.any() else None,
        "max": float(np.nanmax(ice_data)) if valid_mask.any() else None,
        "mean": float(np.nanmean(ice_data)) if valid_mask.any() else None,
        "valid_fraction": float(valid_mask.sum() / valid_mask.size),
        "bounds": bounds,
        "encoding": {"dtype": "uint8", "nodata": 255, "units": "%"}
    }
    
    # Encode as uint8 (0-100, 255=nodata)
    encoded = np.where(np.isnan(ice_data), 255, ice_data.astype(np.uint8))
    
    write_cog(
        encoded,
        output_path,
        bounds,
        nodata=255,
        dtype="uint8"
    )
    
    ds.close()
    
    return stats


def publish_sla(
    nc_path: Path,
    output_path: Path,
    config: Optional[dict] = None,
    use_int16: bool = True
) -> dict:
    """
    Publish Sea Level Anomaly NetCDF as numeric COG.
    
    SLA data is in meters. Encoded as int16 with scale=0.001 (1mm precision).
    
    Args:
        nc_path: Path to input NetCDF file
        output_path: Path for output COG
        config: Dataset configuration (loaded from datasets.json if None)
        use_int16: If True, encode as int16 with scale factor
    
    Returns:
        Metadata dict with stats
    """
    if config is None:
        config = load_datasets_config()["sla"]
    
    # Determine stream from filename
    stream = "rep" if "_my_" in nc_path.name or "rep" in nc_path.name.lower() else "nrt"
    stream_config = config.get(stream, config.get("nrt"))
    
    logger.info(f"Publishing SLA from {nc_path} (stream={stream})")
    
    # Open dataset
    ds = xr.open_dataset(nc_path)
    
    # Get SLA data
    data_var = stream_config["variables"]["data"]
    sla_data = ds[data_var].squeeze().values.astype(np.float32)
    
    # Get bounds
    lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
    lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
    
    # Handle coordinate order
    if lat[0] < lat[-1]:
        sla_data = np.flipud(sla_data)
        lat = lat[::-1]
    
    bounds = (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max()))
    
    # Compute stats
    valid_mask = ~np.isnan(sla_data)
    stats = {
        "min": float(np.nanmin(sla_data)) if valid_mask.any() else None,
        "max": float(np.nanmax(sla_data)) if valid_mask.any() else None,
        "mean": float(np.nanmean(sla_data)) if valid_mask.any() else None,
        "valid_fraction": float(valid_mask.sum() / valid_mask.size),
        "bounds": bounds
    }
    
    if use_int16:
        # Encode as int16 with 1mm precision
        scale = 0.001  # 1mm
        nodata = -32768
        
        scaled = sla_data / scale
        scaled = np.clip(scaled, -32767, 32767)
        encoded = np.where(np.isnan(sla_data), nodata, scaled.astype(np.int16))
        
        write_cog(
            encoded.astype(np.int16),
            output_path,
            bounds,
            nodata=nodata,
            dtype="int16"
        )
        stats["encoding"] = {"dtype": "int16", "scale": scale, "nodata": nodata, "units": "m"}
    else:
        write_cog(
            sla_data,
            output_path,
            bounds,
            nodata=np.nan,
            dtype="float32"
        )
        stats["encoding"] = {"dtype": "float32", "nodata": "nan", "units": "m"}
    
    ds.close()
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Publish Ocean ECV data as COG")
    parser.add_argument("input", type=Path, help="Input NetCDF file")
    parser.add_argument("output", type=Path, help="Output COG file")
    parser.add_argument("--variable", choices=["sst", "chl", "sic", "sla"], required=True,
                        help="Variable type")
    parser.add_argument("--no-int16", action="store_true",
                        help="Don't encode SST/SLA as int16 (use float32)")
    
    args = parser.parse_args()
    
    if args.variable == "sst":
        stats = publish_sst(args.input, args.output, use_int16=not args.no_int16)
    elif args.variable == "chl":
        stats = publish_chl(args.input, args.output)
    elif args.variable == "sic":
        stats = publish_sic(args.input, args.output)
    elif args.variable == "sla":
        stats = publish_sla(args.input, args.output, use_int16=not args.no_int16)
    
    print(json.dumps(stats, indent=2))
