"""
Local Scientific Dataset API Endpoints for YARA.
Provides upload, format detection, metadata inspection, frame streaming,
and point querying for local scientific datasets.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import shutil
import json
import logging
import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Response
from fastapi.responses import Response

from ...data_sources.local.registry import registry
from ...data_sources.local.common_model import DatasetInfo, PointQueryResponse
from ...pipeline.playback_manager import playback_manager
from ...pipeline.frame_cache import frame_cache
from ...pipeline.gradient_colormap import compute_filter_mask_and_count

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local-dataset", tags=["local-dataset"])

UPLOAD_DIR = Path("cache/local_datasets")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Scan local_dataset folder automatically on import
try:
    registry.scan_directory(Path("local_dataset"))
except Exception as e:
    logger.warning(f"Initial scan of local_dataset failed: {e}")


@router.post("/upload", response_model=DatasetInfo)
async def upload_dataset(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    dataset_id: Optional[str] = Form(None)
):
    """
    Upload a scientific data file (.nc, .zarr, .tif, .csv, .asc, .json, .grib, etc.)
    or register an existing file path. Automatically detects format and extracts metadata.
    """
    if file:
        dest_path = UPLOAD_DIR / file.filename
        try:
            with open(dest_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")
        target_path = dest_path
        ds_id = dataset_id or Path(file.filename).stem
    elif file_path:
        target_path = Path(file_path)
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"Specified file path does not exist: {file_path}")
        ds_id = dataset_id or target_path.stem
    else:
        raise HTTPException(status_code=400, detail="Must provide either 'file' or 'file_path'")

    try:
        info, _ = registry.register_file(target_path, dataset_id=ds_id)
        # Automatically set as active dataset upon upload
        registry.set_active(info.id)
        return info
    except Exception as e:
        logger.error(f"Failed to process dataset {target_path}: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/list", response_model=List[DatasetInfo])
def list_datasets():
    """List all registered scientific datasets, auto-scanning local_dataset/ and cache/local_datasets."""
    try:
        registry.scan_directory(Path("local_dataset"))
        registry.scan_directory(UPLOAD_DIR)
    except Exception as e:
        logger.warning(f"Error scanning local dataset directories: {e}")
    return registry.list_datasets()


@router.get("/active")
def get_active_mode():
    """Returns currently active mode ('online' vs 'local') and active dataset info."""
    active_id, active_info = registry.get_active()
    return {
        "mode": "local" if active_id else "online",
        "active_dataset_id": active_id,
        "dataset": active_info
    }


@router.post("/{dataset_id}/activate", response_model=DatasetInfo)
def activate_dataset(dataset_id: str):
    """Activates a local dataset for visualization."""
    try:
        info = registry.set_active(dataset_id)
        return info
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not activate dataset: {e}")


@router.post("/deactivate")
def deactivate_dataset():
    """Deactivates local dataset mode and returns to Online (NOAA OPeNDAP) mode."""
    registry.set_active(None)
    return {"mode": "online", "message": "Returned to Online NOAA OPeNDAP mode."}


@router.get("/{dataset_id}/metadata", response_model=DatasetInfo)
def get_metadata(dataset_id: str):
    """Returns complete metadata, dimensions, coordinates, variables, and time axis."""
    try:
        reader = registry.get_reader(dataset_id)
        return reader._dataset_info
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{dataset_id}/variables")
def get_variables(dataset_id: str):
    """Returns list of variables with shapes, units, and ranges."""
    try:
        reader = registry.get_reader(dataset_id)
        return {
            "default_variable": reader._dataset_info.default_variable,
            "variables": reader._dataset_info.variables
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{dataset_id}/times")
def get_times(dataset_id: str):
    """Returns time axis, timestamps array, and detected temporal resolution."""
    try:
        reader = registry.get_reader(dataset_id)
        return reader._dataset_info.time_axis
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


def _resolve_time_index(reader, time_index: int, time: Optional[str]) -> int:
    if time and reader._dataset_info.time_axis.timestamps:
        ts_list = reader._dataset_info.time_axis.timestamps
        if time in ts_list:
            return ts_list.index(time)
        for i, ts in enumerate(ts_list):
            if ts.startswith(time[:10]):
                return i
    return time_index


def _parse_gradient_stops(gradient_stops: Optional[str]) -> Optional[list]:
    if not gradient_stops:
        return None
    try:
        parsed = json.loads(gradient_stops)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid gradient_stops JSON: {e}")
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="gradient_stops must be a JSON array")
    return parsed


def _validate_filter_params(
    filter_mode: str,
    exact_value: Optional[float],
    range_min: Optional[float],
    range_max: Optional[float]
):
    if filter_mode == "exact" and exact_value is None:
        raise HTTPException(status_code=400, detail="exact_value is required when filter_mode='exact'")
    if filter_mode == "range":
        if range_min is None or range_max is None:
            raise HTTPException(status_code=400, detail="range_min and range_max are required when filter_mode='range'")
        if range_min > range_max:
            raise HTTPException(status_code=400, detail="range_min must be less than or equal to range_max")


@router.get("/{dataset_id}/frame")
def get_frame(
    dataset_id: str,
    variable: Optional[str] = Query(None, description="Variable name to render"),
    time_index: int = Query(0, ge=0, description="Zero-based index along time axis"),
    time: Optional[str] = Query(None, description="Optional ISO timestamp"),
    colormap: Optional[str] = Query(None, description="Colormap name"),
    min_val: Optional[float] = Query(None, description="Minimum color scale value"),
    max_val: Optional[float] = Query(None, description="Maximum color scale value"),
    filter_mode: str = Query("none", pattern="^(none|exact|range)$", description="none|exact|range"),
    exact_value: Optional[float] = Query(None, description="Target value for exact mode"),
    exact_tolerance: Optional[float] = Query(None, ge=0, description="Tolerance (+/-) for exact mode"),
    range_min: Optional[float] = Query(None, description="Minimum value for range mode"),
    range_max: Optional[float] = Query(None, description="Maximum value for range mode"),
    gradient_stops: Optional[str] = Query(None, description="JSON-encoded [{position,color},...]")
):
    """
    Renders and streams a transparent RGBA PNG image for Cesium visualization.
    Uses two-tier caching for zero-latency frame playback.
    """
    _validate_filter_params(filter_mode, exact_value, range_min, range_max)
    parsed_stops = _parse_gradient_stops(gradient_stops)
    try:
        reader = registry.get_reader(dataset_id)
        time_index = _resolve_time_index(reader, time_index, time)

        png_bytes = playback_manager.get_or_render_frame(
            dataset_id=dataset_id,
            variable=variable,
            time_index=time_index,
            colormap=colormap,
            min_val=min_val,
            max_val=max_val,
            filter_mode=filter_mode,
            exact_value=exact_value,
            exact_tolerance=exact_tolerance,
            range_min=range_min,
            range_max=range_max,
            gradient_stops=parsed_stops
        )

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Dataset-ID": dataset_id,
                "X-Time-Index": str(time_index),
                "X-Variable": variable or reader._dataset_info.default_variable or ""
            }
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error rendering frame for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/frame/stats")
def get_frame_stats(
    dataset_id: str,
    variable: Optional[str] = Query(None),
    time_index: int = Query(0, ge=0),
    time: Optional[str] = Query(None),
    filter_mode: str = Query("none", pattern="^(none|exact|range)$"),
    exact_value: Optional[float] = Query(None),
    exact_tolerance: Optional[float] = Query(None, ge=0),
    range_min: Optional[float] = Query(None),
    range_max: Optional[float] = Query(None)
):
    """Cheap (no PNG encode) match-count for current filter settings, used to drive
    'N matching cells' / 'No dataset values found near X' UI messaging."""
    _validate_filter_params(filter_mode, exact_value, range_min, range_max)
    try:
        reader = registry.get_reader(dataset_id)
        time_index = _resolve_time_index(reader, time_index, time)
        var_name = variable or reader._dataset_info.default_variable
        slice_data = reader.read_frame(var_name, time_index)
        base_mask = slice_data.mask if slice_data.mask is not None else np.isnan(slice_data.data)
        _combined_mask, matching, total = compute_filter_mask_and_count(
            slice_data.data, base_mask, filter_mode, exact_value, exact_tolerance, range_min, range_max
        )
        return {"matching_cells": matching, "total_cells": total}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error computing frame stats for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/grid")
def get_grid_lines(
    dataset_id: str,
    resolution: Optional[float] = Query(None, gt=0, description="Grid resolution in degrees; default = dataset native step if ~1 deg, else 1.0")
):
    """Returns 1-degree (or native-resolution) reference grid lines within the dataset's
    real geographic bounds, for a graticule overlay on the globe."""
    try:
        reader = registry.get_reader(dataset_id)
        info = reader._dataset_info
        ext = info.spatial_extent

        # Use the reader's own normalized coordinate arrays (works uniformly across
        # formats, including HDF5 where CoordinateInfo isn't populated).
        slice_data = reader.read_frame(info.default_variable, 0)
        native_lat_step = None
        native_lon_step = None
        if slice_data.lat_coords is not None and len(slice_data.lat_coords) > 1:
            native_lat_step = float(np.median(np.abs(np.diff(np.sort(slice_data.lat_coords)))))
        if slice_data.lon_coords is not None and len(slice_data.lon_coords) > 1:
            native_lon_step = float(np.median(np.abs(np.diff(np.sort(slice_data.lon_coords)))))
        native_step = native_lat_step or native_lon_step

        if resolution is not None:
            step = resolution
        elif native_step and 0.9 <= native_step <= 1.1:
            step = native_step
        else:
            step = 1.0

        lat_lines = list(np.arange(np.ceil(ext.south / step) * step, ext.north + 1e-9, step))
        lon_lines = list(np.arange(np.ceil(ext.west / step) * step, ext.east + 1e-9, step))

        return {
            "lat_lines": [float(v) for v in lat_lines],
            "lon_lines": [float(v) for v in lon_lines],
            "resolution_deg": step,
            "native": resolution is None and native_step is not None and abs(step - native_step) < 1e-9
        }
    except Exception as e:
        logger.error(f"Error computing grid lines for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/point", response_model=PointQueryResponse)
def get_point(
    dataset_id: str,
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude [-90, 90]"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude [-180, 180]"),
    variable: Optional[str] = Query(None, description="Variable name"),
    time_index: int = Query(0, ge=0, description="Time index"),
    time: Optional[str] = Query(None, description="Optional ISO timestamp")
):
    """
    Queries exact data value and nearest grid coordinate cell for the clicked location on the globe.
    """
    try:
        reader = registry.get_reader(dataset_id)
        if time and reader._dataset_info.time_axis.timestamps:
            ts_list = reader._dataset_info.time_axis.timestamps
            if time in ts_list:
                time_index = ts_list.index(time)
            else:
                for i, ts in enumerate(ts_list):
                    if ts.startswith(time[:10]):
                        time_index = i
                        break

        return reader.get_point_value(
            lat=lat,
            lon=lon,
            var_name=variable,
            time_index=time_index
        )
    except Exception as e:
        logger.error(f"Point query error for {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dataset_id}/prefetch")
async def prefetch_frames(
    dataset_id: str,
    variable: Optional[str] = Query(None),
    start_index: int = Query(0, ge=0),
    count: int = Query(10, ge=1, le=100),
    colormap: Optional[str] = Query(None),
    min_val: Optional[float] = Query(None),
    max_val: Optional[float] = Query(None)
):
    """Asynchronously prefetches upcoming frames into the fast cache for smooth playback."""
    try:
        prefetched = await playback_manager.prefetch_range(
            dataset_id=dataset_id,
            variable=variable,
            start_index=start_index,
            count=count,
            colormap=colormap,
            min_val=min_val,
            max_val=max_val
        )
        return {"status": "ok", "prefetched_count": prefetched}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
