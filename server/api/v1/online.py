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
    COPERNICUS_DATASET_ID,
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

def _build_copernicus_dataset_entry():
    return {
        "id": COPERNICUS_DATASET_ID,
        "name": COPERNICUS_DATASET["display_name"],
        "provider": COPERNICUS_DATASET["provider"],
        "source": COPERNICUS_DATASET["source"],
        "description": "Copernicus Marine Global Ocean Physics Reanalysis (GLOBAL_MULTIYEAR_PHY_001_030)",
        "temporal_resolution": COPERNICUS_DATASET["temporal_resolution"],
        "spatial_resolution": "0.083°",
        "coverage": {"north": 90.0, "south": -80.0, "east": 180.0, "west": -180.0},
        "capabilities": {"subset": True, "timeseries": True, "point": True},
        "variables": [
            {
                "id": key,
                "source_name": key,
                "name": cfg["display_name"],
                "units": cfg["units_display"],
                "type": "scalar",
                "category": "physics",
                "colormap": cfg["colormap"],
                "vmin": cfg["vmin"],
                "vmax": cfg["vmax"],
                "log_scale": cfg.get("log_scale", False),
            }
            for key, cfg in ONLINE_DATASETS.items()
        ],
    }

@router.get("/datasets")
async def list_datasets():
    copernicus_entry = _build_copernicus_dataset_entry()
    # Return both array format for OnlineDataset[] and dict format for backward compatibility
    result = {
        "datasets": [copernicus_entry],
    }
    for key, cfg in ONLINE_DATASETS.items():
        result[key] = {
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
    return result

@router.get("/catalog")
async def catalog():
    return {
        "dataset": COPERNICUS_DATASET,
        "variables": list(ONLINE_DATASETS.keys()),
    }

@router.get("/datasets/{dataset_id}/metadata")
async def dataset_metadata(dataset_id: str):
    _require_backend()
    entry = _build_copernicus_dataset_entry()
    variables_list = entry["variables"]
    return {
        **entry,
        "id": dataset_id,
        "inspection": {
            "coordinates": {"time": "time", "latitude": "latitude", "longitude": "longitude", "depth": "depth"},
            "dimensions": {"time": 12227, "depth": 50, "latitude": 2041, "longitude": 4320},
            "time_range": ["1993-01-01T00:00:00", "2026-06-23T00:00:00"],
            "temporal_resolution": "P1D",
            "coverage": {"north": 90.0, "south": -80.0, "east": 180.0, "west": -180.0},
            "variables": variables_list,
        },
    }

@router.get("/datasets/{dataset_id}/times")
async def dataset_times(dataset_id: str, response: Response):
    _require_backend()
    cfg = ONLINE_DATASETS.get("thetao", next(iter(ONLINE_DATASETS.values())))
    loop = asyncio.get_running_loop()
    try:
        values = await loop.run_in_executor(
            _executor, get_available_times, "thetao", cfg
        )
        if not values:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Unable to retrieve Copernicus time coordinate",
                    "dataset_id": dataset_id,
                    "reason": "Copernicus Marine dataset returned no timestamps.",
                },
            )
        response.headers["Cache-Control"] = "public, max-age=3600"
        return {
            "dataset_id": dataset_id,
            "count": len(values),
            "start": values[0],
            "end": values[-1],
            "start_date": values[0],
            "end_date": values[-1],
            "timestamps": values,
            "available_dates": values,
            "temporal_resolution": "P1D",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[ONLINE] dataset_times failed for %s", dataset_id)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Unable to retrieve Copernicus time coordinate",
                "dataset_id": dataset_id,
                "reason": str(exc),
            },
        ) from exc

@router.get("/data")
async def online_data(
    variable: str = Query("thetao"),
    dataset_id: Optional[str] = Query(None),
    time: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    lat_min: float = Query(-80.0, ge=-90, le=90),
    lat_max: float = Query(90.0, ge=-90, le=90),
    lon_min: float = Query(-180.0, ge=-180, le=180),
    lon_max: float = Query(180.0, ge=-180, le=180),
    max_pixels: int = Query(2048, ge=64, le=4096),
    colormap: Optional[str] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
):
    target_date = date or time or "latest"
    return await frame(
        variable=variable,
        date=target_date,
        time=time,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        max_pixels=max_pixels,
        colormap=colormap,
        vmin=vmin,
        vmax=vmax,
    )

@router.get("/point")
async def online_point_query(
    variable: str = Query("thetao"),
    dataset_id: Optional[str] = Query(None),
    time: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
):
    target_date = date or time or "latest"
    return await point(
        variable=variable,
        date=target_date,
        time=time,
        lon=lon,
        lat=lat,
    )

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
            "dataset_id": cfg["dataset_id"],
            "latest_date": value,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Unable to retrieve latest Copernicus time: {exc}") from exc

@router.get("/{variable}/times")
async def times(variable: str, response: Response):
    _require_backend()
    cfg = _cfg(variable)
    loop = asyncio.get_running_loop()
    try:
        values = await loop.run_in_executor(
            _executor, get_available_times, variable, cfg
        )
        if not values:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Unable to retrieve Copernicus time coordinate",
                    "dataset_id": cfg["dataset_id"],
                    "variable": variable,
                    "reason": "Copernicus Marine dataset returned no timestamps.",
                },
            )
        response.headers["Cache-Control"] = "public, max-age=3600"
        return {
            "variable": variable,
            "dataset_id": cfg["dataset_id"],
            "count": len(values),
            "start": values[0],
            "end": values[-1],
            "start_date": values[0],
            "end_date": values[-1],
            "timestamps": values,
            "available_dates": values,
            "temporal_resolution": "P1D",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[ONLINE] times failed for variable %s", variable)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Unable to retrieve Copernicus time coordinate",
                "dataset_id": cfg["dataset_id"],
                "variable": variable,
                "reason": str(exc),
            },
        ) from exc

@router.get("/{variable}/frame.png")
async def frame(
    variable: str,
    date: Optional[str] = Query(None),
    time: Optional[str] = Query(None),
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
    target_date = date or time or "latest"
    if lat_min > lat_max or lon_min > lon_max:
        raise HTTPException(400, "Minimum coordinate must not exceed maximum coordinate.")
    loop = asyncio.get_running_loop()
    try:
        png, matched, bounds = await loop.run_in_executor(
            _executor, render_to_png, variable, cfg, target_date,
            lat_min, lat_max, lon_min, lon_max, max_pixels,
            colormap, vmin, vmax,
        )
        return Response(
            content=png,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=300",
                "Vary": "Origin",
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
    date: Optional[str] = Query(None),
    time: Optional[str] = Query(None),
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
):
    _require_backend()
    cfg = _cfg(variable)
    target_date = date or time or "latest"
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            _executor, query_point, variable, cfg, target_date, lon, lat
        )
    except Exception as exc:
        logger.exception("[ONLINE] point failed for %s", variable)
        raise HTTPException(
            502, f"Unable to query Copernicus point for '{variable}': {exc}"
        ) from exc
