"""Provider-neutral online dataset API.

Local uploads remain served exclusively by ``/api/local-dataset``. This router
only exposes registry-backed remote data and never leaks a provider URL to the
frontend request contract.
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

import matplotlib
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image

from server.data_sources.online_registry import ONLINE_DATASETS, get_dataset, get_variable
from server.data_sources.providers import OPeNDAPProvider, ProviderError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/online", tags=["Online datasets"])
provider = OPeNDAPProvider()
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="yara-opendap")
_frame_cache: OrderedDict[tuple, tuple[bytes, dict[str, str]]] = OrderedDict()
_cache_lock = RLock()
_FRAME_CACHE_SIZE = 24


def _dataset_or_404(dataset_id: str):
    try:
        return get_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _variable_or_404(dataset_id: str, variable: str):
    try:
        return get_variable(dataset_id, variable)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


def _api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderError):
        return HTTPException(status_code=422, detail=str(exc))
    logger.exception("Online provider request failed")
    return HTTPException(status_code=502, detail=f"Unable to retrieve online dataset: {exc}")


def _edge_bounds(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 1:
        return float(values[0]), float(values[0])
    step = float(np.median(np.abs(np.diff(values))))
    return float(np.nanmin(values) - step / 2), float(np.nanmax(values) + step / 2)


def _render(dataset_id: str, variable_id: str, timestamp: str, *, lat_min: float, lat_max: float, lon_min: float, lon_max: float, max_pixels: int, colormap: str, vmin: float | None, vmax: float | None) -> tuple[bytes, dict[str, str]]:
    dataset = get_dataset(dataset_id)
    variable = get_variable(dataset_id, variable_id)
    cache_key = (dataset.provider, dataset_id, variable_id, timestamp, lat_min, lat_max, lon_min, lon_max, max_pixels, colormap, vmin, vmax)
    with _cache_lock:
        cached = _frame_cache.get(cache_key)
        if cached:
            _frame_cache.move_to_end(cache_key)
            return cached
    grid = provider.get_data(dataset, variable_id, timestamp, lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max, max_pixels=max_pixels)
    finite = np.isfinite(grid.values)
    if not finite.any():
        raise ProviderError(f"No valid '{variable_id}' observations are available for {grid.timestamp} in this area.")
    low = float(variable.vmin if vmin is None else vmin)
    high = float(variable.vmax if vmax is None else vmax)
    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        raise ProviderError("Color-scale limits must be finite and minimum must be smaller than maximum.")
    values = grid.values
    if variable.log_scale:
        valid = finite & (values > 0)
        values = np.where(valid, np.log10(values), np.nan)
        low, high = np.log10(low), np.log10(high)
        finite = valid
    normalized = np.clip((values - low) / (high - low), 0, 1)
    cmap = matplotlib.colormaps.get(colormap, matplotlib.colormaps["viridis"])
    rgba = (cmap(normalized) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(finite, 255, 0).astype(np.uint8)
    if len(grid.latitude) > 1 and grid.latitude[0] < grid.latitude[-1]:
        rgba = np.flipud(rgba)
    west, east = _edge_bounds(grid.longitude)
    south, north = _edge_bounds(grid.latitude)
    output = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(output, format="PNG", optimize=True)
    headers = {
        "X-Dataset-Id": dataset_id, "X-Variable": variable_id, "X-Time-Matched": grid.timestamp,
        "X-Bounds-West": str(west), "X-Bounds-South": str(south), "X-Bounds-East": str(east), "X-Bounds-North": str(north),
        "X-Raster-Width": str(rgba.shape[1]), "X-Raster-Height": str(rgba.shape[0]),
        "X-Units": grid.variable.units, "X-ColorMap": colormap,
        "X-Color-Min": str(variable.vmin if vmin is None else vmin), "X-Color-Max": str(variable.vmax if vmax is None else vmax),
        "Access-Control-Expose-Headers": "X-Dataset-Id, X-Variable, X-Time-Matched, X-Bounds-West, X-Bounds-South, X-Bounds-East, X-Bounds-North, X-Raster-Width, X-Raster-Height, X-Units, X-ColorMap, X-Color-Min, X-Color-Max",
    }
    result = (output.getvalue(), headers)
    with _cache_lock:
        _frame_cache[cache_key] = result
        _frame_cache.move_to_end(cache_key)
        while len(_frame_cache) > _FRAME_CACHE_SIZE:
            _frame_cache.popitem(last=False)
    return result


@router.get("/datasets")
async def list_datasets():
    """Return declarative public dataset metadata, grouped by dataset not variable."""
    return {"datasets": [dataset.public() for dataset in ONLINE_DATASETS.values()]}


@router.get("/datasets/{dataset_id}")
async def dataset_detail(dataset_id: str):
    return _dataset_or_404(dataset_id).public()


@router.get("/datasets/{dataset_id}/variables")
async def dataset_variables(dataset_id: str):
    dataset = _dataset_or_404(dataset_id)
    try:
        inspection = await asyncio.get_running_loop().run_in_executor(executor, provider.inspect_dataset, dataset)
        return {"dataset_id": dataset_id, "variables": inspection.variables}
    except Exception as exc:
        raise _api_error(exc)


@router.get("/datasets/{dataset_id}/metadata")
async def dataset_metadata(dataset_id: str):
    dataset = _dataset_or_404(dataset_id)
    try:
        inspection = await asyncio.get_running_loop().run_in_executor(executor, provider.inspect_dataset, dataset)
        payload = dataset.public()
        payload["inspection"] = inspection.public()
        return payload
    except Exception as exc:
        raise _api_error(exc)


@router.get("/datasets/{dataset_id}/times")
async def dataset_times(dataset_id: str):
    dataset = _dataset_or_404(dataset_id)
    try:
        inspection = await asyncio.get_running_loop().run_in_executor(executor, provider.inspect_dataset, dataset)
        return {"dataset_id": dataset_id, "start": inspection.time_range[0], "end": inspection.time_range[1], "temporal_resolution": inspection.temporal_resolution, "timestamps": inspection.timestamps}
    except Exception as exc:
        raise _api_error(exc)


@router.get("/data")
async def get_data(
    dataset_id: str, variable: str, time: str,
    lat_min: float = Query(-90, ge=-90, le=90), lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180), lon_max: float = Query(180, ge=-180, le=180),
    max_pixels: int = Query(1536, ge=128, le=4096), colormap: str = Query("viridis", max_length=100),
    vmin: float | None = None, vmax: float | None = None,
):
    """Return a normalized scalar frame encoded for the existing Cesium layer."""
    _dataset_or_404(dataset_id)
    _variable_or_404(dataset_id, variable)
    try:
        png, headers = await asyncio.get_running_loop().run_in_executor(executor, lambda: _render(dataset_id, variable, time, lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max, max_pixels=max_pixels, colormap=colormap, vmin=vmin, vmax=vmax))
        return Response(png, media_type="image/png", headers=headers)
    except Exception as exc:
        raise _api_error(exc)


@router.get("/point")
async def get_point(dataset_id: str, variable: str, time: str, lon: float = Query(..., ge=-180, le=180), lat: float = Query(..., ge=-90, le=90)):
    dataset = _dataset_or_404(dataset_id)
    _variable_or_404(dataset_id, variable)
    try:
        return await asyncio.get_running_loop().run_in_executor(executor, lambda: provider.get_point_value(dataset, variable, time, latitude=lat, longitude=lon))
    except Exception as exc:
        raise _api_error(exc)
