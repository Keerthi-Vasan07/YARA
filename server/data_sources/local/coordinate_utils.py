"""
Coordinate processing utilities for YARA.
Handles coordinate normalization, 0-360 to -180-180 wrapping, grid orientation,
and geospatial point matching.
"""

from typing import Tuple, Optional
import numpy as np
from .common_model import SpatialExtent, CoordinateInfo


def normalize_longitude_180(lon: np.ndarray) -> np.ndarray:
    """Normalize longitudes to [-180, 180] range."""
    return ((lon + 180) % 360) - 180


def is_0_to_360(lon: np.ndarray) -> bool:
    """Check if longitude array is primarily in 0-360 range."""
    return float(np.nanmax(lon)) > 180.5 or (float(np.nanmin(lon)) >= -0.1 and float(np.nanmax(lon)) > 180.0)


def normalize_grid_to_wgs84(
    data: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, SpatialExtent]:
    """
    Normalizes a 2D data grid [lat, lon] to standard WGS84 orientation:
    - Longitude in [-180, 180] in ascending order.
    - Latitude ordered North-to-South (top-down, lat[0] is North, lat[-1] is South),
      matching image raster coordinate systems (row 0 = top = North).
    - Rolls data array across longitude boundary if data was originally 0..360.
    """
    data = np.array(data, copy=True)
    lat = np.array(lat, copy=True)
    lon = np.array(lon, copy=True)

    # 1. Handle Longitude wrapping if 0..360
    if is_0_to_360(lon):
        # Convert to [-180, 180]
        lon_180 = normalize_longitude_180(lon)
        # Find sort order to make it monotonic ascending
        sort_indices = np.argsort(lon_180)
        lon = lon_180[sort_indices]
        # Reorder columns along lon axis (axis -1)
        data = data[:, sort_indices]
    else:
        # Check if lon is descending, if so flip
        if len(lon) > 1 and lon[0] > lon[-1]:
            lon = lon[::-1]
            data = np.fliplr(data)

    # 2. Handle Latitude orientation
    # In GIS raster/image conventions: row 0 is North (top), row N is South (bottom).
    # Cesium SingleTileImageryProvider expects image row 0 at the North edge.
    if len(lat) > 1 and lat[0] < lat[-1]:
        # Latitude is South-to-North (ascending) -> flip to North-to-South
        lat = lat[::-1]
        data = np.flipud(data)

    # 3. Calculate spatial extent
    west = float(np.nanmin(lon))
    east = float(np.nanmax(lon))
    south = float(np.nanmin(lat))
    north = float(np.nanmax(lat))

    is_global = (east - west >= 355.0) and (north - south >= 160.0)
    if is_global:
        west = -180.0
        east = 180.0
        south = max(-90.0, south)
        north = min(90.0, north)

    extent = SpatialExtent(
        west=west,
        south=south,
        east=east,
        north=north,
        is_global=is_global
    )

    return data, lat, lon, extent


def find_nearest_cell(
    target_lat: float,
    target_lon: float,
    lat_coords: np.ndarray,
    lon_coords: np.ndarray
) -> Tuple[int, int, float, float]:
    """
    Finds nearest grid cell indices (y_idx, x_idx) and matched coordinates (matched_lat, matched_lon).
    lat_coords is assumed 1D [North to South or South to North].
    lon_coords is assumed 1D [-180 to 180].
    """
    # Normalize query lon to [-180, 180]
    norm_lon = ((target_lon + 180) % 360) - 180
    
    # Distance in lat
    lat_diff = np.abs(lat_coords - target_lat)
    y_idx = int(np.argmin(lat_diff))
    matched_lat = float(lat_coords[y_idx])

    # Distance in lon, accounting for circular boundary
    lon_diff = np.abs(lon_coords - norm_lon)
    lon_diff = np.minimum(lon_diff, 360 - lon_diff)
    x_idx = int(np.argmin(lon_diff))
    matched_lon = float(lon_coords[x_idx])

    return y_idx, x_idx, matched_lat, matched_lon


def compute_grid_step(coords: np.ndarray) -> Optional[float]:
    """Median absolute spacing of a 1D coordinate array; None if fewer than 2 points."""
    coords = np.asarray(coords)
    if coords.size < 2:
        return None
    diffs = np.abs(np.diff(np.sort(coords)))
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return None
    return float(np.median(diffs))


def compute_cell_bounds(
    y_idx: int,
    x_idx: int,
    lat_coords: np.ndarray,
    lon_coords: np.ndarray
) -> Tuple[float, float, float, float]:
    """
    Returns (south, north, west, east) degree bounds of the grid cell at
    (y_idx, x_idx), using half-step padding around the matched coordinate.
    lat_coords/lon_coords must be the SAME normalized arrays passed to
    find_nearest_cell (post normalize_grid_to_wgs84).
    """
    lat_step = compute_grid_step(lat_coords) or 1.0
    lon_step = compute_grid_step(lon_coords) or 1.0

    lat_val = float(lat_coords[y_idx])
    lon_val = float(lon_coords[x_idx])

    south = lat_val - lat_step / 2.0
    north = lat_val + lat_step / 2.0
    west = lon_val - lon_step / 2.0
    east = lon_val + lon_step / 2.0

    return south, north, west, east
