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

    # Raster extent is the outside cell edges, not the center coordinates.
    lon_edges = coordinate_edges(lon, -180, 180)
    lat_edges = coordinate_edges(lat, -90, 90)
    west = float(np.min(lon_edges))
    east = float(np.max(lon_edges))
    south = float(np.min(lat_edges))
    north = float(np.max(lat_edges))

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


def coordinate_edges(coords, lower, upper):
    """Midpoint-derived cell edges, preserving ascending/descending index order.

    A singleton axis has no measurable resolution; its center is returned as
    both edges rather than inventing a scientific cell size.
    """
    coords = np.asarray(coords, dtype=float)
    if coords.ndim != 1 or not coords.size or not np.all(np.isfinite(coords)):
        raise ValueError("Finite one-dimensional rectilinear coordinates are required")
    if coords.size == 1:
        return np.array([coords[0], coords[0]])
    diffs = np.diff(coords)
    if not (np.all(diffs > 0) or np.all(diffs < 0)):
        raise ValueError("Coordinates must be strictly monotonic")
    edges = np.concatenate(([coords[0] - diffs[0] / 2], (coords[:-1] + coords[1:]) / 2,
                            [coords[-1] + diffs[-1] / 2]))
    return np.clip(edges, lower, upper)


def cell_bounds(lat, lon, y, x):
    ys, xs = coordinate_edges(lat, -90, 90), coordinate_edges(lon, -180, 180)
    return SpatialExtent(south=float(min(ys[y:y + 2])), north=float(max(ys[y:y + 2])),
                         west=float(min(xs[x:x + 2])), east=float(max(xs[x:x + 2])))


def grid_metadata(frame):
    lat, lon = frame.lat_coords, frame.lon_coords
    ys, xs = coordinate_edges(lat, -90, 90), coordinate_edges(lon, -180, 180)
    dy, dx = np.abs(np.diff(lat)), np.abs(np.diff(lon))
    native = bool(dy.size and dx.size and np.allclose(dy, 1, atol=0.01, rtol=0)
                  and np.allclose(dx, 1, atol=0.01, rtol=0))
    extent = SpatialExtent(south=float(min(ys)), north=float(max(ys)),
                           west=float(min(xs)), east=float(max(xs)))
    return {
        "kind": "native" if native else "reference",
        "latitude_resolution": float(np.median(dy)) if dy.size else None,
        "longitude_resolution": float(np.median(dx)) if dx.size else None,
        "extent": extent.model_dump(),
        "latitudes": sorted(ys.tolist()) if native else np.arange(np.ceil(extent.south), np.floor(extent.north) + 1).tolist(),
        "longitudes": sorted(xs.tolist()) if native else np.arange(np.ceil(extent.west), np.floor(extent.east) + 1).tolist(),
    }


def read_rectilinear_slice(ds, da, lat_name, lon_name, time_name, time_index):
    """Slice by actual dimension names and transpose before coordinate normalization."""
    lat, lon = ds[lat_name], ds[lon_name]
    if lat.ndim != 1 or lon.ndim != 1:
        raise ValueError("Curvilinear coordinates require a dedicated regridding adapter")
    ydim, xdim = lat.dims[0], lon.dims[0]
    if ydim == xdim or ydim not in da.dims or xdim not in da.dims:
        raise ValueError("Variable does not contain both spatial dimensions")
    tdim = ds[time_name].dims[0] if time_name and ds[time_name].dims else None
    indexer = {d: 0 for d in da.dims if d not in (ydim, xdim)}
    if tdim in da.dims:
        if not 0 <= time_index < da.sizes[tdim]:
            raise ValueError("Time index outside dataset time axis")
        indexer[tdim] = time_index
    elif time_index != 0:
        raise ValueError("This variable has only one frame")
    return np.array(da.isel(indexer).transpose(ydim, xdim).values, dtype=np.float32, copy=True)
