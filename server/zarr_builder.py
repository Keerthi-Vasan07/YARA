"""
Zarr Dataset Builder for SST COGs.

Converts COG files to a consolidated Zarr store with:
- Time dimension (daily)
- Pre-calculated metrics (stats, climatology, trends)
- Optimized chunking for web access

Usage:
    python -m server.zarr_builder
"""

import os
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import rasterio
import zarr

from server.earthkit_integration import (
    resample_to_grid, 
    resample_rgb_to_grid,
    compute_climatology,
    compute_percentiles as ek_compute_percentiles,
    compute_linear_trend,
    compute_monthly_climatology as ek_compute_monthly_climatology,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
PRODUCTS_DIR = Path(__file__).parent / "products"
ZARR_DIR = Path(__file__).parent / "zarr"

# Zarr configuration (v3 uses different compression syntax)
CHUNK_SIZE_LAT = 512
CHUNK_SIZE_LON = 512
CHUNK_SIZE_TIME = 12  # Group by ~yearly chunks


def get_cog_dates(variable: str = "sst") -> list[tuple[str, Path]]:
    """Get all available COG dates for a variable."""
    cog_dir = PRODUCTS_DIR / variable
    if not cog_dir.exists():
        return []
    
    dates = []
    for cog_path in sorted(cog_dir.glob("*.tif")):
        date_str = cog_path.stem  # YYYY-MM-DD
        dates.append((date_str, cog_path))
    
    return dates


def read_cog_as_array(cog_path: Path, variable: str = "sst") -> tuple[np.ndarray, dict]:
    """Read a COG file and return data array + metadata.
    
    Returns:
        For single-band variables: (2D array, metadata)
        For rrs (RGB composite): (3D array [band, lat, lon], metadata)
    """
    with rasterio.open(cog_path) as ds:
        metadata = {
            "width": ds.width,
            "height": ds.height,
            "bounds": list(ds.bounds),
            "crs": str(ds.crs),
            "transform": list(ds.transform),
        }
        
        # Handle RGB composite (rrs)
        if variable == "rrs":
            # RGBA uint8 - read first 3 bands (RGB), use alpha as mask
            rgb = ds.read([1, 2, 3])  # shape: (3, height, width)
            alpha = ds.read(4)
            # Convert to float32 normalized [0, 1]
            decoded = rgb.astype(np.float32) / 255.0
            # Apply alpha mask (alpha=0 means nodata)
            mask = alpha == 0
            for band in range(3):
                decoded[band][mask] = np.nan
            return decoded, metadata
        
        # Single-band variables
        data = ds.read(1)
        nodata = ds.nodata
        
        # Decode based on variable encoding
        if variable == "sst":
            # SST: int16 with scale=0.01 (0.01°C precision)
            if nodata is not None:
                mask = data == nodata
                decoded = data.astype(np.float32) * 0.01
                decoded[mask] = np.nan
            else:
                decoded = data.astype(np.float32) * 0.01
        elif variable == "sla":
            # SLA: int16 with scale=0.001 (1mm precision)
            if nodata is not None:
                mask = data == nodata
                decoded = data.astype(np.float32) * 0.001
                decoded[mask] = np.nan
            else:
                decoded = data.astype(np.float32) * 0.001
        elif variable == "sic":
            # SIC: uint8 0-100%, nodata=255
            mask = data == 255 if nodata is None else data == nodata
            decoded = data.astype(np.float32)
            decoded[mask] = np.nan
        elif variable == "kd490":
            # Kd490: float32 with _FillValue for nodata
            nodata_val = nodata if nodata is not None else -999.0
            mask = (data == nodata_val) | np.isnan(data)
            decoded = data.astype(np.float32)
            decoded[mask] = np.nan
        elif variable == "chl":
            # CHL: float32 with _FillValue for nodata
            nodata_val = nodata if nodata is not None else -999.0
            mask = (data == nodata_val) | np.isnan(data)
            decoded = data.astype(np.float32)
            decoded[mask] = np.nan
        else:
            # Default: just convert to float32
            if nodata is not None:
                mask = data == nodata
                decoded = data.astype(np.float32)
                decoded[mask] = np.nan
            else:
                decoded = data.astype(np.float32)
        
        return decoded, metadata


def compute_stats(data: np.ndarray) -> dict:
    """Compute statistics for a 2D array."""
    valid = ~np.isnan(data)
    valid_count = np.sum(valid)
    total_count = data.size
    
    if valid_count == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "valid_fraction": 0.0,
            "valid_pixels": 0,
        }
    
    valid_data = data[valid]
    return {
        "min": float(np.min(valid_data)),
        "max": float(np.max(valid_data)),
        "mean": float(np.mean(valid_data)),
        "std": float(np.std(valid_data)),
        "valid_fraction": float(valid_count / total_count),
        "valid_pixels": int(valid_count),
    }


def create_zarr_store(
    variable: str = "sst",
    target_resolution: tuple[int, int] = (3600, 7200),  # lat, lon
    force_rebuild: bool = False
) -> Path:
    """
    Create or update Zarr store from COG files.
    
    Args:
        variable: Variable name (sst, chl, etc.)
        target_resolution: Target grid size (lat, lon)
        force_rebuild: Force complete rebuild even if exists
        
    Returns:
        Path to Zarr store
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    
    # Get all COG dates
    cog_dates = get_cog_dates(variable)
    if not cog_dates:
        raise ValueError(f"No COG files found for {variable}")
    
    logger.info(f"Found {len(cog_dates)} COG files for {variable}")
    
    # Parse dates and sort
    dates_parsed = []
    for date_str, cog_path in cog_dates:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            dates_parsed.append((dt, date_str, cog_path))
        except ValueError:
            logger.warning(f"Skipping invalid date: {date_str}")
    
    dates_parsed.sort(key=lambda x: x[0])
    n_times = len(dates_parsed)
    
    # Create coordinate arrays
    nlat, nlon = target_resolution
    lat = np.linspace(90, -90, nlat).astype(np.float32)  # North to South
    lon = np.linspace(-180, 180, nlon).astype(np.float32)  # West to East
    
    # Time as days since 1970-01-01
    time_values = np.array([
        (dt - datetime(1970, 1, 1)).days for dt, _, _ in dates_parsed
    ], dtype=np.int32)
    
    # Create or open Zarr store (v3 API)
    if force_rebuild and zarr_path.exists():
        shutil.rmtree(zarr_path)
    
    ZARR_DIR.mkdir(parents=True, exist_ok=True)
    
    # Open/create zarr group
    mode = 'w' if force_rebuild or not zarr_path.exists() else 'r+'
    root = zarr.open_group(zarr_path, mode=mode)
    
    # Create coordinate arrays (zarr v3 style)
    if "lat" not in root:
        lat_arr = root.create_array("lat", shape=(nlat,), chunks=(nlat,), dtype=np.float32)
        lat_arr[:] = lat
        lat_arr.attrs["units"] = "degrees_north"
        lat_arr.attrs["long_name"] = "latitude"
        lat_arr.attrs["_ARRAY_DIMENSIONS"] = ["lat"]
    
    if "lon" not in root:
        lon_arr = root.create_array("lon", shape=(nlon,), chunks=(nlon,), dtype=np.float32)
        lon_arr[:] = lon
        lon_arr.attrs["units"] = "degrees_east"
        lon_arr.attrs["long_name"] = "longitude"
        lon_arr.attrs["_ARRAY_DIMENSIONS"] = ["lon"]
    
    if "time" not in root:
        time_arr = root.create_array(
            "time", 
            shape=(n_times,), 
            chunks=(min(CHUNK_SIZE_TIME, n_times),), 
            dtype=np.int32
        )
        time_arr[:] = time_values
        time_arr.attrs["units"] = "days since 1970-01-01"
        time_arr.attrs["calendar"] = "gregorian"
        time_arr.attrs["long_name"] = "time"
        time_arr.attrs["_ARRAY_DIMENSIONS"] = ["time"]
    else:
        root["time"][:] = time_values
    
    # Variable-specific metadata
    VAR_METADATA = {
        "sst": {
            "units": "degC",
            "long_name": "sea_surface_temperature",
            "standard_name": "sea_surface_temperature",
        },
        "sic": {
            "units": "%",
            "long_name": "sea_ice_concentration",
            "standard_name": "sea_ice_area_fraction",
        },
        "sla": {
            "units": "m",
            "long_name": "sea_level_anomaly",
            "standard_name": "sea_surface_height_above_sea_level",
        },
        "chl": {
            "units": "mg/m3",
            "long_name": "chlorophyll_a_concentration",
            "standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water",
        },
        "kd490": {
            "units": "m-1",
            "long_name": "diffuse_attenuation_coefficient_490nm",
            "standard_name": "volume_attenuation_coefficient_of_downwelling_radiative_flux_in_sea_water",
        },
        "rrs": {
            "units": "1",
            "long_name": "remote_sensing_reflectance_rgb",
            "standard_name": "surface_ratio_of_upwelling_radiance_emerging_from_sea_water_to_downwelling_radiative_flux_in_air",
            "bands": ["red (670nm)", "green (555nm)", "blue (443nm)"],
        },
    }
    
    var_meta = VAR_METADATA.get(variable, {"units": "unknown", "long_name": variable, "standard_name": variable})
    
    # Determine if this is an RGB variable (3 bands)
    is_rgb = variable == "rrs"
    n_bands = 3 if is_rgb else 1
    
    # Create band coordinate for RGB variables
    if is_rgb and "band" not in root:
        band_arr = root.create_array("band", shape=(3,), chunks=(3,), dtype=np.int32)
        band_arr[:] = [0, 1, 2]  # R, G, B indices
        band_arr.attrs["long_name"] = "RGB band index (0=R, 1=G, 2=B)"
        band_arr.attrs["band_names"] = var_meta.get("bands", ["red", "green", "blue"])
        band_arr.attrs["_ARRAY_DIMENSIONS"] = ["band"]
    
    # Create main data array
    if variable not in root:
        if is_rgb:
            # RGB: (time, band, lat, lon)
            data_arr = root.create_array(
                variable,
                shape=(n_times, n_bands, nlat, nlon),
                chunks=(min(CHUNK_SIZE_TIME, n_times), n_bands, CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
                dtype=np.float32,
                fill_value=np.nan,
            )
            data_arr.attrs.update({
                "units": var_meta["units"],
                "long_name": var_meta["long_name"],
                "standard_name": var_meta["standard_name"],
                "scale_factor": 1.0,
                "add_offset": 0.0,
                "_ARRAY_DIMENSIONS": ["time", "band", "lat", "lon"],
            })
        else:
            # Single-band: (time, lat, lon)
            data_arr = root.create_array(
                variable,
                shape=(n_times, nlat, nlon),
                chunks=(min(CHUNK_SIZE_TIME, n_times), CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
                dtype=np.float32,
                fill_value=np.nan,
            )
            data_arr.attrs.update({
                "units": var_meta["units"],
                "long_name": var_meta["long_name"],
                "standard_name": var_meta["standard_name"],
                "scale_factor": 1.0,
                "add_offset": 0.0,
                "_ARRAY_DIMENSIONS": ["time", "lat", "lon"],
            })
    
    # Process each COG
    logger.info(f"Processing {n_times} time steps...")
    all_stats = []
    
    for i, (dt, date_str, cog_path) in enumerate(dates_parsed):
        logger.info(f"  [{i+1}/{n_times}] Processing {date_str}...")
        
        # Read COG data
        var_data, cog_meta = read_cog_as_array(cog_path, variable)
        
        if is_rgb:
            # RGB data: shape (3, height, width) -> resample each band
            target_shape = (nlat, nlon)
            if var_data.shape[1:] != target_shape:
                # Create source coordinates from COG bounds
                src_lat = np.linspace(cog_meta["bounds"][3], cog_meta["bounds"][1], var_data.shape[1])
                src_lon = np.linspace(cog_meta["bounds"][0], cog_meta["bounds"][2], var_data.shape[2])
                var_data = resample_rgb_to_grid(var_data, src_lat, src_lon, target_shape)
            
            # Write to Zarr
            root[variable][i, :, :, :] = var_data
            
            # Compute stats (use mean across bands for summary)
            mean_data = np.nanmean(var_data, axis=0)
            stats = compute_stats(mean_data)
        else:
            # Resample to target resolution if needed
            if var_data.shape != (nlat, nlon):
                # Create source coordinates from COG bounds
                src_lat = np.linspace(cog_meta["bounds"][3], cog_meta["bounds"][1], var_data.shape[0])
                src_lon = np.linspace(cog_meta["bounds"][0], cog_meta["bounds"][2], var_data.shape[1])
                var_data = resample_to_grid(var_data, src_lat, src_lon, (nlat, nlon))
            
            # Write to Zarr
            root[variable][i, :, :] = var_data
            
            # Compute stats for this time step
            stats = compute_stats(var_data)
        
        stats["date"] = date_str
        stats["time_index"] = i
        all_stats.append(stats)
    
    # Store per-time stats as JSON metadata
    root.attrs["time_stats"] = all_stats
    root.attrs["dates"] = [date_str for _, date_str, _ in dates_parsed]
    
    # Compute and store aggregate statistics
    logger.info("Computing aggregate statistics...")
    compute_aggregate_stats(root, variable, all_stats, nlat, nlon)
    
    # Add global attributes
    root.attrs.update({
        "title": f"Global {variable.upper()} Dataset",
        "source": "Copernicus Marine Service L4 OSTIA",
        "institution": "PineView Labs",
        "created": datetime.utcnow().isoformat(),
        "conventions": "CF-1.8",
        "variable": variable,
        "resolution_lat": float(lat[0] - lat[1]),
        "resolution_lon": float(lon[1] - lon[0]),
    })
    
    logger.info(f"Zarr store created: {zarr_path}")
    logger.info(f"  Shape: {root[variable].shape}")
    logger.info(f"  Chunks: {root[variable].chunks}")
    logger.info(f"  Size: {sum(f.stat().st_size for f in zarr_path.rglob('*') if f.is_file()) / 1e6:.1f} MB")
    
    return zarr_path


def compute_aggregate_stats(root: zarr.Group, variable: str, time_stats: list[dict], nlat: int, nlon: int):
    """Compute and store aggregate statistics for the dataset."""
    
    # Check if this is an RGB variable
    is_rgb = variable == "rrs"
    
    # Time series stats
    dates = [s["date"] for s in time_stats]
    means = [s["mean"] for s in time_stats if s["mean"] is not None]
    
    if means:
        # Global temporal statistics
        root.attrs["global_stats"] = {
            "temporal_mean": float(np.mean(means)),
            "temporal_std": float(np.std(means)),
            "temporal_min": float(np.min(means)),
            "temporal_max": float(np.max(means)),
            "n_timesteps": len(dates),
            "date_range": [dates[0], dates[-1]] if dates else None,
        }
    
    # Skip climatology for RGB (not meaningful for color composites)
    if is_rgb:
        logger.info("  Skipping climatology for RGB variable.")
        return
    
    # Compute climatology (mean over all times) - stored as 2D array
    logger.info("  Computing climatology using earthkit...")
    data_array = root[variable][:]  # Load all (small dataset)
    
    # Get units from the variable
    var_units = root[variable].attrs.get("units", "unknown")
    
    # Use earthkit for climatology computation
    climatology, climatology_std = compute_climatology(data_array, time_axis=0)
    valid_count = np.sum(~np.isnan(data_array), axis=0).astype(np.int16)
    
    # Store climatology (zarr v3 API)
    if "climatology_mean" not in root:
        clim_arr = root.create_array(
            "climatology_mean",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        clim_arr[:] = climatology
        clim_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} climatology mean",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["climatology_mean"][:] = climatology
    
    if "climatology_std" not in root:
        std_arr = root.create_array(
            "climatology_std",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        std_arr[:] = climatology_std
        std_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} climatology standard deviation",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["climatology_std"][:] = climatology_std
    
    if "valid_count" not in root:
        count_arr = root.create_array(
            "valid_count",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.int16,
        )
        count_arr[:] = valid_count
        count_arr.attrs.update({
            "units": "count",
            "long_name": "Number of valid observations per pixel",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["valid_count"][:] = valid_count
    
    # Compute percentiles (overall)
    logger.info("  Computing percentiles (P10, P50, P90)...")
    compute_percentiles(root, variable, data_array, nlat, nlon, var_units)
    
    # Compute monthly climatology
    logger.info("  Computing monthly climatology...")
    compute_monthly_climatology(root, variable, data_array, dates, nlat, nlon, var_units)
    
    # Compute trend (simple linear regression per pixel) if we have enough data
    if len(dates) >= 2:
        logger.info("  Computing trends...")
        compute_trends(root, variable, data_array, nlat, nlon)
    
    logger.info("  Aggregate statistics computed.")


def compute_percentiles(root: zarr.Group, variable: str, data_array: np.ndarray, nlat: int, nlon: int, var_units: str):
    """Compute overall percentiles (P10, P50, P90) per pixel using earthkit."""
    
    # Use earthkit function for consistent percentile computation
    percentile_dict = ek_compute_percentiles(data_array, percentiles=[10, 50, 90], time_axis=0)
    p10 = percentile_dict[10].astype(np.float32)
    p50 = percentile_dict[50].astype(np.float32)
    p90 = percentile_dict[90].astype(np.float32)
    
    # Store P10
    if "percentile_10" not in root:
        p10_arr = root.create_array(
            "percentile_10",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        p10_arr[:] = p10
        p10_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} 10th percentile",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["percentile_10"][:] = p10
    
    # Store P50
    if "percentile_50" not in root:
        p50_arr = root.create_array(
            "percentile_50",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        p50_arr[:] = p50
        p50_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} 50th percentile (median)",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["percentile_50"][:] = p50
    
    # Store P90
    if "percentile_90" not in root:
        p90_arr = root.create_array(
            "percentile_90",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        p90_arr[:] = p90
        p90_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} 90th percentile",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["percentile_90"][:] = p90


def compute_monthly_climatology(root: zarr.Group, variable: str, data_array: np.ndarray, 
                                 dates: list[str], nlat: int, nlon: int, var_units: str):
    """Compute monthly climatology (mean and std for each calendar month)."""
    
    # Use earthkit function for mean/std computation
    monthly_mean, monthly_std = ek_compute_monthly_climatology(data_array, dates)
    
    # Parse months for percentile computation (earthkit doesn't have monthly percentiles)
    months = np.array([int(d.split('-')[1]) for d in dates], dtype=np.int32)
    
    # Initialize monthly percentile arrays (12 months) - not in earthkit
    monthly_p10 = np.full((12, nlat, nlon), np.nan, dtype=np.float32)
    monthly_p50 = np.full((12, nlat, nlon), np.nan, dtype=np.float32)
    monthly_p90 = np.full((12, nlat, nlon), np.nan, dtype=np.float32)
    monthly_count = np.zeros((12,), dtype=np.int32)
    
    with np.errstate(all='ignore'):
        for month_idx in range(12):
            month = month_idx + 1  # 1-12
            mask = months == month
            monthly_count[month_idx] = int(np.sum(mask))
            
            # Monthly percentiles (need at least 3 samples for meaningful percentiles)
            if monthly_count[month_idx] >= 3:
                month_data = data_array[mask, :, :]
                monthly_p10[month_idx] = np.nanpercentile(month_data, 10, axis=0)
                monthly_p50[month_idx] = np.nanpercentile(month_data, 50, axis=0)
                monthly_p90[month_idx] = np.nanpercentile(month_data, 90, axis=0)
    
    # Create month coordinate
    if "month" not in root:
        month_arr = root.create_array("month", shape=(12,), chunks=(12,), dtype=np.int32)
        month_arr[:] = np.arange(1, 13)
        month_arr.attrs.update({
            "long_name": "calendar month",
            "units": "1",
            "_ARRAY_DIMENSIONS": ["month"],
        })
    
    # Store monthly climatology mean
    if "climatology_monthly_mean" not in root:
        clim_monthly_arr = root.create_array(
            "climatology_monthly_mean",
            shape=(12, nlat, nlon),
            chunks=(1, CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        clim_monthly_arr[:] = monthly_mean
        clim_monthly_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} monthly climatology mean",
            "_ARRAY_DIMENSIONS": ["month", "lat", "lon"],
        })
    else:
        root["climatology_monthly_mean"][:] = monthly_mean
    
    # Store monthly climatology std
    if "climatology_monthly_std" not in root:
        std_monthly_arr = root.create_array(
            "climatology_monthly_std",
            shape=(12, nlat, nlon),
            chunks=(1, CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        std_monthly_arr[:] = monthly_std
        std_monthly_arr.attrs.update({
            "units": var_units,
            "long_name": f"{variable.upper()} monthly climatology standard deviation",
            "_ARRAY_DIMENSIONS": ["month", "lat", "lon"],
        })
    else:
        root["climatology_monthly_std"][:] = monthly_std
    
    # Store monthly percentiles (combined: 12 x 3 x lat x lon -> 12 x lat x lon for each P)
    for pname, pdata in [("monthly_percentile_10", monthly_p10), 
                          ("monthly_percentile_50", monthly_p50),
                          ("monthly_percentile_90", monthly_p90)]:
        if pname not in root:
            parr = root.create_array(
                pname,
                shape=(12, nlat, nlon),
                chunks=(1, CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
                dtype=np.float32,
            )
            parr[:] = pdata
            parr.attrs.update({
                "units": var_units,
                "long_name": f"{variable.upper()} monthly {pname.split('_')[-1]}th percentile",
                "_ARRAY_DIMENSIONS": ["month", "lat", "lon"],
            })
        else:
            root[pname][:] = pdata
    
    # Store metadata about monthly counts
    root.attrs["monthly_sample_count"] = monthly_count.tolist()
    root.attrs["reference_period"] = "full_record"


def compute_trends(root: zarr.Group, variable: str, data_array: np.ndarray, nlat: int, nlon: int):
    """Compute linear trend per pixel (units per year) using earthkit."""
    n_times = data_array.shape[0]
    
    if n_times < 2:
        return
    
    # Get units from the variable
    var_units = root[variable].attrs.get("units", "unknown")
    
    # Use earthkit vectorized trend computation
    # Returns slope per timestep - multiply by 12 for monthly data → yearly trend
    slope, _intercept = compute_linear_trend(data_array, time_values=None)
    trend = (slope * 12).astype(np.float32)
    
    # Store trend (zarr v3 API)
    if "trend" not in root:
        trend_arr = root.create_array(
            "trend",
            shape=(nlat, nlon),
            chunks=(CHUNK_SIZE_LAT, CHUNK_SIZE_LON),
            dtype=np.float32,
        )
        trend_arr[:] = trend
        trend_arr.attrs.update({
            "units": f"{var_units}/year",
            "long_name": f"{variable.upper()} linear trend",
            "_ARRAY_DIMENSIONS": ["lat", "lon"],
        })
    else:
        root["trend"][:] = trend


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Build Zarr dataset from COGs")
    parser.add_argument("--variable", default="sst", help="Variable name")
    parser.add_argument("--force", action="store_true", help="Force rebuild")
    parser.add_argument("--resolution", default="3600x7200", 
                       help="Target resolution (lat x lon)")
    
    args = parser.parse_args()
    
    lat_res, lon_res = map(int, args.resolution.split("x"))
    
    zarr_path = create_zarr_store(
        variable=args.variable,
        target_resolution=(lat_res, lon_res),
        force_rebuild=args.force,
    )
    
    print(f"\nZarr store ready: {zarr_path}")
