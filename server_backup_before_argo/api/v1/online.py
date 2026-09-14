"""
YARA Online Ocean Data API.

The UI consumes these routes. The registry is Copernicus-centric and exposes
the same stable route shape for all 11 scientific variables.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from server.data_sources.online_registry import (
    ONLINE_DATASETS,
    COPERNICUS_DATASET,
    get_dataset_config,
)
from server.data_sources.erddap_opendap import (
    HAS_XARRAY,
    HAS_COPERNICUS,
    inspect_dataset_metadata,
    get_latest_time,
    get_available_times,
    render_to_png,
    query_point,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/online", tags=["Online / Copernicus OPeNDAP"])
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="online")

def _require_backend():
    if not HAS_XARRAY:
        raise HTTPException(503, "xarray is not installed.")
    if not HAS_COPERNICUS:
        raise HTTPException(503, "copernicusmarine is not installed.")

def _cfg(variable: str):
    try:
        return get_dataset_config(variable)
    except KeyError as exc:
        raise HTTPException(
            404,
            f"Unknown online variable '{variable}'. "
            f"Available: {list(ONLINE_DATASETS)}",
        ) from exc

@router.get("/datasets")
async def list_datasets():
    return {
        key: {
            "variable_key": key,
            "dataset_id": cfg["dataset_id"],
            "display_name": cfg["display_name"],
            "units_display": cfg["units_display"],
            "temporal_resolution": cfg["temporal_resolution"],
            "spatial_resolution_deg": cfg["spatial_resolution_deg"],
            "vmin": cfg["vmin"], "vmax": cfg["vmax"],
            "log_scale": cfg.get("log_scale", False),
            "colormap": cfg.get("colormap", "viridis"),
            "colorbar_label": cfg["colorbar_label"],
            "description": cfg["description"],
            "source": cfg["source"], "provider": cfg["provider"],
            "opendap_url": cfg["opendap_url"],
            "dimensions": cfg["dimensions"],
            "is_3d": cfg["is_3d"],
        }
        for key, cfg in ONLINE_DATASETS.items()
    }

@router.get("/catalog")
async def catalog():
    return {
        "dataset": COPERNICUS_DATASET,
        "variables": list_datasets.__annotations__ and list(ONLINE_DATASETS.keys()),
    }

@router.get("/{variable}/metadata")
async def metadata(variable: str):
    _require_backend()
    cfg = _cfg(variable)
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _executor, inspect_dataset_metadata, variable, cfg
        )
    except Exception as exc:
        logger.exception("[ONLINE] metadata failed for %s", variable)
        raise HTTPException(502, f"Unable to retrieve Copernicus metadata: {exc}") from exc

@router.get("/{variable}/latest")
async def latest(variable: str):
    _require_backend()
    cfg = _cfg(variable)
    loop = asyncio.get_running_loop()
    try:
        value = await loop.run_in_executor(
            _executor, get_latest_time, variable, cfg
        )
        if value is None:
            raise HTTPException(404, "Dataset has no time coordinate.")
        return {
            "variable": variable,
            "display_name": cfg["display_name"],
            "latest_date": value,
            "dataset_id": cfg["dataset_id"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Unable to retrieve latest Copernicus time: {exc}") from exc

@router.get("/{variable}/times")
async def times(variable: str):
    _require_backend()
    cfg = _cfg(variable)
    loop = asyncio.get_running_loop()
    try:
        values = await loop.run_in_executor(
            _executor, get_available_times, variable, cfg
        )
        return {
            "variable": variable,
            "dataset_id": cfg["dataset_id"],
            "count": len(values),
            "start_date": values[0] if values else None,
            "end_date": values[-1] if values else None,
            "available_dates": values,
        }
    except Exception as exc:
        raise HTTPException(502, f"Unable to retrieve Copernicus times: {exc}") from exc

@router.get("/{variable}/frame.png")
async def frame(
    variable: str,
    date: str = Query("latest"),
    lat_min: float = Query(-80.0, ge=-90, le=90),
    lat_max: float = Query(90.0, ge=-90, le=90),
    lon_min: float = Query(-180.0, ge=-180, le=180),
    lon_max: float = Query(180.0, ge=-180, le=180),
    max_pixels: int = Query(2048, ge=64, le=4096),
    colormap: Optional[str] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
):
    _require_backend()
    cfg = _cfg(variable)
    if lat_min > lat_max or lon_min > lon_max:
        raise HTTPException(400, "Minimum coordinate must not exceed maximum coordinate.")
    loop = asyncio.get_running_loop()
    try:
        png, matched, bounds = await loop.run_in_executor(
            _executor, render_to_png, variable, cfg, date,
            lat_min, lat_max, lon_min, lon_max, max_pixels,
            colormap, vmin, vmax,
        )
        return Response(
            content=png,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300",
                "X-Date-Matched": str(matched),
                "X-Variable": variable,
                "X-Dataset-Id": cfg["dataset_id"],
                "X-Bounds-West": str(bounds["west"]),
                "X-Bounds-South": str(bounds["south"]),
                "X-Bounds-East": str(bounds["east"]),
                "X-Bounds-North": str(bounds["north"]),
                "X-Raster-Width": str(bounds.get("width", 0)),
                "X-Raster-Height": str(bounds.get("height", 0)),
                "Access-Control-Expose-Headers":
                    "X-Date-Matched, X-Variable, X-Dataset-Id, "
                    "X-Bounds-West, X-Bounds-South, X-Bounds-East, X-Bounds-North, "
                    "X-Raster-Width, X-Raster-Height",
            },
        )
    except Exception as exc:
        logger.exception("[ONLINE] frame failed for %s", variable)
        raise HTTPException(
            502, f"Unable to render Copernicus frame for '{variable}': {exc}"
        ) from exc

@router.get("/{variable}/point")
async def point(
    variable: str,
    date: str = Query("latest"),
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
):
    _require_backend()
    cfg = _cfg(variable)
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _executor, query_point, variable, cfg, date, lon, lat
        )
    except Exception as exc:
        logger.exception("[ONLINE] point failed for %s", variable)
        raise HTTPException(
            502, f"Unable to query Copernicus point for '{variable}': {exc}"
        ) from exc
