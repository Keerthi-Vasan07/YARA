"""
geo_service.py

Fast, offline global land-sea boundary detection and spatial masking.
Utilizes `global-land-mask` (0.25-degree offline global raster) to prevent
synthesizing false ocean volumes over continental landmasses and carve out
transparent voids for coastal zones.
"""

from __future__ import annotations

import logging
from typing import Union
import numpy as np
from global_land_mask import globe

logger = logging.getLogger("geo_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[GEO-SERVICE] %(levelname)s - %(message)s"))
    logger.addHandler(_ch)


def normalize_lon(lon: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Ensure longitudes are mapped into standard [-180.0, 180.0] interval.
    """
    if isinstance(lon, (int, float)):
        while lon < -180.0:
            lon += 360.0
        while lon > 180.0:
            lon -= 360.0
        return float(lon)
    arr = np.asarray(lon, dtype=np.float64).copy()
    arr = (arr + 180.0) % 360.0 - 180.0
    return arr


def is_point_land(lat: float, lon: float) -> bool:
    """
    Returns True if the specified (lat, lon) coordinate is on land, False if ocean/water.
    """
    norm_lon = normalize_lon(lon)
    return bool(globe.is_land(lat, norm_lon))


is_point_real_land = is_point_land


def check_region_land_fraction(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    samples: int = 15,
) -> float:
    """
    Returns the fraction (0.0 to 1.0) of the bounding box that is land.
    0.0 = Pure Open Ocean, 1.0 = Pure Continental Landmass.
    """
    lats = np.linspace(min_lat, max_lat, samples)
    norm_min_lon = normalize_lon(min_lon)
    norm_max_lon = normalize_lon(max_lon)

    # Handle prime meridian or antimeridian wrap if max_lon < min_lon
    if norm_max_lon < norm_min_lon:
        lons = np.linspace(norm_min_lon, norm_min_lon + (max_lon - min_lon), samples)
        lons = normalize_lon(lons)
    else:
        lons = np.linspace(norm_min_lon, norm_max_lon, samples)

    lon_grid, lat_grid = np.meshgrid(lons, lats)
    is_land_matrix = globe.is_land(lat_grid, lon_grid)
    land_fraction = float(np.sum(is_land_matrix) / is_land_matrix.size)
    return land_fraction


def get_2d_land_mask(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """
    Generates a 2D boolean mask of shape (len(lats), len(lons)) where True = Land.
    """
    norm_lons = normalize_lon(lons)
    lon_grid, lat_grid = np.meshgrid(norm_lons, lats)
    return globe.is_land(lat_grid, lon_grid)
