"""
backend/geo_service.py

Re-exports from backend.services.geo_service.
"""

from backend.services.geo_service import (
    normalize_lon,
    is_point_land,
    check_region_land_fraction,
    get_2d_land_mask,
)
