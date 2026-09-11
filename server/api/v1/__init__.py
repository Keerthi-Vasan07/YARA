"""
API v1 routers - aggregates all route modules.
"""

from fastapi import APIRouter

from .health import router as health_router
from .time_range import router as time_range_router
from .tiles import router as tiles_router
from .point import router as point_router
from .subset import router as subset_router
from .timeseries import router as timeseries_router
from .stac import router as stac_router
from .zarr import router as zarr_router
from .opendap_sst import router as opendap_sst_router

# Main v1 router that combines all sub-routers
router = APIRouter()

# Health endpoints (no prefix - /, /health, /ready)
router.include_router(health_router)

# Time range endpoints (/api/time-range/*)
router.include_router(time_range_router)

# Tile endpoints (/api/tiles/*, /api/sst/image/*)
router.include_router(tiles_router)

# Point query endpoints (/api/{variable}/point, /api/sst/point)
router.include_router(point_router)

# Subset download endpoints (/api/{variable}/subset)
router.include_router(subset_router)

# Timeseries endpoints (/api/sst/timeseries)
router.include_router(timeseries_router)

# STAC catalog endpoints (/api/stac/*)
router.include_router(stac_router)

# Zarr analytics endpoints (/api/zarr/*)
router.include_router(zarr_router)

# OPeNDAP SST endpoints
router.include_router(opendap_sst_router)

