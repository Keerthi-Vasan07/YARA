"""
Coordinate Utilities.

Functions for extracting and normalizing coordinates from scientific datasets.
"""

from typing import Optional, Tuple
import numpy as np
import xarray as xr


def normalize_longitude(lon: np.ndarray) -> np.ndarray:
    """
    Normalize longitude values to the range [-180, 180].
    
    Args:
        lon: Longitude array (can be in any range)
        
    Returns:
        Normalized longitude array
    """
    lon_normalized = lon.copy()
    
    # Convert 0-360 to -180-180
    lon_normalized = np.where(lon_normalized > 180, lon_normalized - 360, lon_normalized)
    
    return lon_normalized


def extract_1d_coordinates(ds: xr.Dataset) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Extract 1D latitude and longitude coordinates from an xarray Dataset.
    
    Looks for coordinates with standard names or common variable names.
    
    Args:
        ds: xarray Dataset
        
    Returns:
        Tuple of (latitude, longitude) arrays, or (None, None) if not found
    """
    lat_names = ['lat', 'latitude', 'y', 'grid_latitude']
    lon_names = ['lon', 'longitude', 'x', 'grid_longitude']
    
    latitude = None
    longitude = None
    
    # Find latitude
    for name in lat_names:
        if name in ds.coords:
            coord = ds.coords[name]
            if coord.ndim == 1:
                latitude = coord.values.astype(np.float64)
                break
    
    # Also try standard_name attribute
    if latitude is None:
        for coord_name in ds.coords:
            if ds.coords[coord_name].attrs.get('standard_name') == 'latitude':
                coord = ds.coords[coord_name]
                if coord.ndim == 1:
                    latitude = coord.values.astype(np.float64)
                    break
    
    # Find longitude
    for name in lon_names:
        if name in ds.coords:
            coord = ds.coords[name]
            if coord.ndim == 1:
                longitude = coord.values.astype(np.float64)
                break
    
    # Also try standard_name attribute
    if longitude is None:
        for coord_name in ds.coords:
            if ds.coords[coord_name].attrs.get('standard_name') == 'longitude':
                coord = ds.coords[coord_name]
                if coord.ndim == 1:
                    longitude = coord.values.astype(np.float64)
                    break
    
    return latitude, longitude


def extract_2d_coordinates(ds: xr.Dataset) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Extract 2D latitude and longitude coordinates from an xarray Dataset.
    
    Some datasets (especially on curvilinear grids) have 2D coordinate arrays.
    
    Args:
        ds: xarray Dataset
        
    Returns:
        Tuple of (latitude_2d, longitude_2d) arrays, or (None, None) if not found
    """
    # Common names for 2D coordinates
    lat_2d_names = ['lat_2d', 'latitude_2d', 'grid_lat', 'grid_latitude']
    lon_2d_names = ['lon_2d', 'longitude_2d', 'grid_lon', 'grid_longitude']
    
    latitude_2d = None
    longitude_2d = None
    
    # Find 2D latitude
    for name in lat_2d_names:
        if name in ds.coords:
            coord = ds.coords[name]
            if coord.ndim == 2:
                latitude_2d = coord.values.astype(np.float64)
                break
    
    # Also try standard_name
    if latitude_2d is None:
        for coord_name in ds.coords:
            coord = ds.coords[coord_name]
            if coord.ndim == 2 and coord.attrs.get('standard_name') == 'latitude':
                latitude_2d = coord.values.astype(np.float64)
                break
    
    # Find 2D longitude
    for name in lon_2d_names:
        if name in ds.coords:
            coord = ds.coords[name]
            if coord.ndim == 2:
                longitude_2d = coord.values.astype(np.float64)
                break
    
    # Also try standard_name
    if longitude_2d is None:
        for coord_name in ds.coords:
            coord = ds.coords[coord_name]
            if coord.ndim == 2 and coord.attrs.get('standard_name') == 'longitude':
                longitude_2d = coord.values.astype(np.float64)
                break
    
    return latitude_2d, longitude_2d


def extract_coordinates(ds: xr.Dataset) -> Tuple[
    Optional[np.ndarray],
    Optional[np.ndarray],
    Optional[np.ndarray],
    Optional[np.ndarray],
]:
    """
    Extract all coordinates from a dataset.
    
    Args:
        ds: xarray Dataset
        
    Returns:
        Tuple of (lat_1d, lon_1d, lat_2d, lon_2d)
    """
    lat_1d, lon_1d = extract_1d_coordinates(ds)
    lat_2d, lon_2d = extract_2d_coordinates(ds)
    
    return lat_1d, lon_1d, lat_2d, lon_2d


def get_coordinate_bounds(
    latitude: Optional[np.ndarray],
    longitude: Optional[np.ndarray],
) -> Tuple[
    Optional[float],
    Optional[float],
    Optional[float],
    Optional[float],
]:
    """
    Get spatial bounds from coordinates.
    
    Args:
        latitude: Latitude array
        longitude: Longitude array
        
    Returns:
        Tuple of (lat_min, lat_max, lon_min, lon_max)
    """
    lat_min = float(np.min(latitude)) if latitude is not None else None
    lat_max = float(np.max(latitude)) if latitude is not None else None
    
    if longitude is not None:
        lon_normalized = normalize_longitude(longitude)
        lon_min = float(np.min(lon_normalized))
        lon_max = float(np.max(lon_normalized))
    else:
        lon_min = None
        lon_max = None
    
    return lat_min, lat_max, lon_min, lon_max
