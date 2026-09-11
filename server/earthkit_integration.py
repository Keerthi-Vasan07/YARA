"""
Earthkit Integration for ECV Data Processing

This module provides integration with ECMWF's Earthkit ecosystem, specifically
designed to enhance the existing ECV pipeline with ECMWF's preferred tooling.

Integration Points:
1. Data Loading (earthkit-data) - Replace raw xarray for NetCDF/GRIB loading
2. Regridding (earthkit-regrid) - Replace scipy.ndimage.zoom for resampling
3. Meteorological Calculations (earthkit-meteo) - Enhanced anomaly/trend calculations
4. Unit Conversions - Kelvin/Celsius, etc.

Usage:
    # In downloaders (e.g., sst.py):
    from server.earthkit_integration import load_netcdf, kelvin_to_celsius
    
    # In zarr_builder.py:
    from server.earthkit_integration import resample_to_grid, compute_anomalies

See: https://earthkit.readthedocs.io/
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

# =============================================================================
# Feature Detection - Graceful Degradation
# =============================================================================

try:
    import earthkit.data as ekd
    HAS_EARTHKIT_DATA = True
    logger.info("✓ earthkit-data available - using for data loading")
except ImportError:
    HAS_EARTHKIT_DATA = False
    logger.debug("earthkit-data not installed, using xarray fallback")

try:
    import earthkit.regrid as ekr
    HAS_EARTHKIT_REGRID = True
    logger.info("✓ earthkit-regrid available - using for resampling")
except ImportError:
    HAS_EARTHKIT_REGRID = False
    logger.debug("earthkit-regrid not installed, using scipy fallback")

try:
    import earthkit.meteo as ekm
    HAS_EARTHKIT_METEO = True
    logger.info("✓ earthkit-meteo available - using for climate calculations")
except ImportError:
    HAS_EARTHKIT_METEO = False
    logger.debug("earthkit-meteo not installed, using numpy fallback")


def get_earthkit_status() -> dict[str, bool]:
    """Return availability status of earthkit components."""
    return {
        "earthkit-data": HAS_EARTHKIT_DATA,
        "earthkit-regrid": HAS_EARTHKIT_REGRID,
        "earthkit-meteo": HAS_EARTHKIT_METEO,
    }


# =============================================================================
# Data Loading (replaces xr.open_dataset in downloaders)
# =============================================================================

def load_netcdf(path: Path | str, variables: list[str] | None = None) -> xr.Dataset:
    """
    Load NetCDF file using earthkit-data if available.
    
    This replaces direct xr.open_dataset() calls in downloaders like sst.py.
    Earthkit provides better handling of CF conventions and ECMWF-specific formats.
    
    Args:
        path: Path to NetCDF file
        variables: Optional list of variables to load
        
    Returns:
        xarray Dataset
        
    Example:
        # Before (sst.py):
        ds = xr.open_dataset(nc_path)
        
        # After:
        from server.earthkit_integration import load_netcdf
        ds = load_netcdf(nc_path, variables=["analysed_sst"])
    """
    path = Path(path)
    
    if HAS_EARTHKIT_DATA:
        try:
            # Earthkit handles CF conventions, units, coordinates automatically
            source = ekd.from_source("file", str(path))
            ds = source.to_xarray()
            
            if variables:
                available = [v for v in variables if v in ds.data_vars]
                if available:
                    ds = ds[available]
            
            logger.debug(f"Loaded {path.name} with earthkit-data")
            return ds
        except Exception as e:
            logger.warning(f"earthkit-data failed, falling back to xarray: {e}")
    
    # Fallback to xarray
    ds = xr.open_dataset(path)
    if variables:
        available = [v for v in variables if v in ds.data_vars]
        if available:
            ds = ds[available]
    return ds


def load_grib(path: Path | str) -> xr.Dataset:
    """
    Load GRIB file using earthkit-data.
    
    GRIB is ECMWF's native format - earthkit handles it much better than cfgrib.
    
    Args:
        path: Path to GRIB file
        
    Returns:
        xarray Dataset
    """
    path = Path(path)
    
    if HAS_EARTHKIT_DATA:
        source = ekd.from_source("file", str(path))
        return source.to_xarray()
    else:
        # Fallback - requires cfgrib
        return xr.open_dataset(path, engine="cfgrib")


# =============================================================================
# Unit Conversions (used in sst.py, etc.)
# =============================================================================

def kelvin_to_celsius(data: np.ndarray | xr.DataArray) -> np.ndarray | xr.DataArray:
    """
    Convert temperature from Kelvin to Celsius.
    
    Uses earthkit-meteo if available for proper handling of units metadata.
    
    Args:
        data: Temperature data in Kelvin
        
    Returns:
        Temperature data in Celsius
        
    Example:
        # In sst.py _convert():
        sst_c = kelvin_to_celsius(ds["analysed_sst"])
    """
    if HAS_EARTHKIT_METEO and isinstance(data, xr.DataArray):
        try:
            # earthkit-meteo handles units properly
            return ekm.thermo.celsius_from_kelvin(data)
        except Exception:
            pass
    
    # Simple conversion
    return data - 273.15


def celsius_to_kelvin(data: np.ndarray | xr.DataArray) -> np.ndarray | xr.DataArray:
    """Convert temperature from Celsius to Kelvin."""
    if HAS_EARTHKIT_METEO and isinstance(data, xr.DataArray):
        try:
            return ekm.thermo.kelvin_from_celsius(data)
        except Exception:
            pass
    
    return data + 273.15


# =============================================================================
# Regridding (replaces scipy.ndimage.zoom in zarr_builder.py)
# =============================================================================

def resample_to_grid(
    data: np.ndarray,
    source_lat: np.ndarray,
    source_lon: np.ndarray,
    target_shape: tuple[int, int],
    method: str = "linear",
) -> np.ndarray:
    """
    Resample 2D data to a target grid shape.
    
    This replaces scipy.ndimage.zoom() in zarr_builder.py for resampling COG data
    to the target Zarr resolution. Earthkit-regrid provides proper geographic
    interpolation rather than simple image scaling.
    
    Args:
        data: 2D array to resample (lat, lon)
        source_lat: Source latitude coordinates
        source_lon: Source longitude coordinates
        target_shape: Target (nlat, nlon) shape
        method: Interpolation method ("linear", "nearest", "conservative")
        
    Returns:
        Resampled 2D array
        
    Example:
        # Before (zarr_builder.py):
        from scipy.ndimage import zoom
        zoom_factors = (nlat / var_data.shape[0], nlon / var_data.shape[1])
        var_resampled = zoom(var_data, zoom_factors, order=1, mode='nearest')
        
        # After:
        from server.earthkit_integration import resample_to_grid
        var_resampled = resample_to_grid(var_data, lat, lon, (nlat, nlon))
    """
    nlat, nlon = target_shape
    
    if data.shape == target_shape:
        return data
    
    if HAS_EARTHKIT_REGRID:
        try:
            # Create xarray DataArray for earthkit
            da = xr.DataArray(
                data,
                dims=["latitude", "longitude"],
                coords={"latitude": source_lat, "longitude": source_lon}
            )
            
            # Define target grid
            target_grid = {
                "type": "regular_ll",
                "grid": [180.0 / nlat, 360.0 / nlon],  # lat_step, lon_step
            }
            
            result = ekr.regrid(da, target_grid, method=method)
            logger.debug(f"Resampled {data.shape} -> {target_shape} with earthkit-regrid")
            return result.values
            
        except Exception as e:
            logger.warning(f"earthkit-regrid failed, using scipy fallback: {e}")
    
    # Scipy fallback
    from scipy.ndimage import zoom
    
    zoom_factors = (nlat / data.shape[0], nlon / data.shape[1])
    order = 1 if method == "linear" else 0  # 1=bilinear, 0=nearest
    
    result = zoom(data, zoom_factors, order=order, mode='nearest')
    
    # Preserve NaN mask
    nan_mask = zoom(np.isnan(data).astype(float), zoom_factors, order=0) > 0.5
    result[nan_mask] = np.nan
    
    return result


def resample_rgb_to_grid(
    rgb_data: np.ndarray,
    source_lat: np.ndarray,
    source_lon: np.ndarray,
    target_shape: tuple[int, int],
) -> np.ndarray:
    """
    Resample RGB (3-band) data to a target grid.
    
    For RRS composite data - resamples each band independently.
    
    Args:
        rgb_data: 3D array (band, lat, lon)
        source_lat: Source latitude coordinates
        source_lon: Source longitude coordinates
        target_shape: Target (nlat, nlon) shape
        
    Returns:
        Resampled 3D array (band, nlat, nlon)
    """
    n_bands = rgb_data.shape[0]
    nlat, nlon = target_shape
    
    result = np.zeros((n_bands, nlat, nlon), dtype=np.float32)
    
    for band in range(n_bands):
        result[band] = resample_to_grid(
            rgb_data[band],
            source_lat,
            source_lon,
            target_shape,
            method="linear"
        )
    
    return result


# =============================================================================
# Climate Statistics (for zarr_builder.py pre-computed metrics)
# =============================================================================

def compute_climatology(
    data: np.ndarray,
    time_axis: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute climatological mean and standard deviation.
    
    Args:
        data: 3D array (time, lat, lon)
        time_axis: Axis representing time dimension
        
    Returns:
        Tuple of (mean, std) arrays
        
    Example:
        # In zarr_builder.py compute_aggregate_stats():
        climatology, climatology_std = compute_climatology(data_array)
    """
    with np.errstate(all='ignore'):
        mean = np.nanmean(data, axis=time_axis).astype(np.float32)
        std = np.nanstd(data, axis=time_axis).astype(np.float32)
    
    return mean, std


def compute_anomaly(
    data: np.ndarray,
    climatology: np.ndarray,
    standardize: bool = False,
    climatology_std: np.ndarray | None = None,
) -> np.ndarray:
    """
    Compute anomalies relative to climatology.
    
    Args:
        data: 2D or 3D array
        climatology: Climatological mean (2D)
        standardize: If True, compute standardized anomaly (requires std)
        climatology_std: Climatological standard deviation (required if standardize=True)
        
    Returns:
        Anomaly array (same shape as data)
        
    Example:
        # Compute SST anomaly for a specific date:
        anomaly = compute_anomaly(sst_today, sst_climatology)
        
        # Standardized anomaly:
        std_anomaly = compute_anomaly(sst_today, sst_mean, standardize=True, climatology_std=sst_std)
    """
    if HAS_EARTHKIT_METEO:
        try:
            # Convert to xarray for earthkit
            if isinstance(data, np.ndarray):
                da = xr.DataArray(data)
                clim = xr.DataArray(climatology)
                result = ekm.stats.anomaly(da, clim)
                
                if standardize and climatology_std is not None:
                    std = xr.DataArray(climatology_std)
                    result = result / std
                
                return result.values
        except Exception as e:
            logger.debug(f"earthkit-meteo anomaly failed: {e}")
    
    # Numpy fallback
    anomaly = data - climatology
    
    if standardize and climatology_std is not None:
        with np.errstate(divide='ignore', invalid='ignore'):
            anomaly = anomaly / climatology_std
            anomaly[~np.isfinite(anomaly)] = np.nan
    
    return anomaly.astype(np.float32)


def compute_percentiles(
    data: np.ndarray,
    percentiles: list[float] = [10, 50, 90],
    time_axis: int = 0,
) -> dict[int, np.ndarray]:
    """
    Compute percentiles over time axis.
    
    Args:
        data: 3D array (time, lat, lon)
        percentiles: List of percentile values (0-100)
        time_axis: Axis representing time
        
    Returns:
        Dict mapping percentile value to 2D array
        
    Example:
        # In zarr_builder.py:
        pcts = compute_percentiles(data_array, [10, 50, 90])
        p10 = pcts[10]
    """
    result = {}
    
    with np.errstate(all='ignore'):
        for p in percentiles:
            result[int(p)] = np.nanpercentile(data, p, axis=time_axis).astype(np.float32)
    
    return result


def compute_linear_trend(
    data: np.ndarray,
    time_values: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute linear trend per pixel.
    
    Args:
        data: 3D array (time, lat, lon)
        time_values: Optional time values (defaults to 0, 1, 2, ...)
        
    Returns:
        Tuple of (slope, intercept) arrays
        
    Example:
        # In zarr_builder.py compute_trends():
        slope, intercept = compute_linear_trend(data_array)
    """
    n_times, nlat, nlon = data.shape
    
    if time_values is None:
        time_values = np.arange(n_times, dtype=np.float64)
    
    # Reshape for vectorized computation
    # (time, lat*lon)
    data_flat = data.reshape(n_times, -1)
    
    # Compute trend for all pixels at once
    # Using least squares: slope = cov(x,y) / var(x)
    t_mean = np.mean(time_values)
    t_var = np.var(time_values)
    
    if t_var == 0:
        # Single time step - no trend
        slope = np.zeros((nlat, nlon), dtype=np.float32)
        intercept = np.nanmean(data, axis=0).astype(np.float32)
        return slope, intercept
    
    with np.errstate(all='ignore'):
        # Center time
        t_centered = time_values - t_mean
        
        # Compute slope for each pixel
        # slope = sum((t - t_mean) * (y - y_mean)) / sum((t - t_mean)^2)
        data_mean = np.nanmean(data_flat, axis=0)
        
        numerator = np.nansum(t_centered[:, np.newaxis] * (data_flat - data_mean), axis=0)
        denominator = np.sum(t_centered ** 2)
        
        slope_flat = numerator / denominator
        intercept_flat = data_mean - slope_flat * t_mean
    
    slope = slope_flat.reshape(nlat, nlon).astype(np.float32)
    intercept = intercept_flat.reshape(nlat, nlon).astype(np.float32)
    
    return slope, intercept


def compute_monthly_climatology(
    data: np.ndarray,
    dates: list[str],  # List of "YYYY-MM-DD" strings
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute monthly climatology (12 months).
    
    Args:
        data: 3D array (time, lat, lon)
        dates: List of date strings corresponding to time axis
        
    Returns:
        Tuple of (monthly_mean, monthly_std) with shape (12, lat, lon)
        
    Example:
        # In zarr_builder.py:
        monthly_mean, monthly_std = compute_monthly_climatology(data_array, dates)
    """
    from datetime import datetime
    
    n_times, nlat, nlon = data.shape
    
    # Initialize monthly arrays
    monthly_mean = np.full((12, nlat, nlon), np.nan, dtype=np.float32)
    monthly_std = np.full((12, nlat, nlon), np.nan, dtype=np.float32)
    
    # Group data by month
    month_indices = {m: [] for m in range(12)}
    
    for i, date_str in enumerate(dates):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            month = dt.month - 1  # 0-indexed
            month_indices[month].append(i)
        except ValueError:
            continue
    
    # Compute stats for each month
    for month, indices in month_indices.items():
        if indices:
            month_data = data[indices, :, :]
            with np.errstate(all='ignore'):
                monthly_mean[month] = np.nanmean(month_data, axis=0)
                monthly_std[month] = np.nanstd(month_data, axis=0)
    
    return monthly_mean, monthly_std
