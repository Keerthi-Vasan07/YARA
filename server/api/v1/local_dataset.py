"""
Local Scientific Dataset API Endpoints for YARA.
Provides upload, format detection, metadata inspection, frame streaming,
and point querying for local scientific datasets.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import shutil
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Response, Depends
from pydantic import ValidationError
from ...pipeline.gradient_colormap import AnalysisOptions, analyze_slice
from ...data_sources.local.coordinate_utils import grid_metadata
from fastapi.responses import Response

from ...data_sources.local.registry import registry
from ...data_sources.local.common_model import DatasetInfo, PointQueryResponse
from ...pipeline.playback_manager import playback_manager
from ...pipeline.frame_cache import frame_cache

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


def analysis_options(analysis: Optional[str] = Query(None, max_length=10000)):
    try:
        return AnalysisOptions.model_validate_json(analysis) if analysis is not None else AnalysisOptions()
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def resolve_request(dataset_id, variable, time_index, time=None):
    try:
        reader = registry.get_reader(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    info = reader._dataset_info
    variable = variable or info.default_variable
    if variable not in info.variables:
        raise HTTPException(status_code=422, detail="Variable not found in dataset")
    if time is not None:
        if time not in info.time_axis.timestamps:
            raise HTTPException(status_code=422, detail="Timestamp not found; use an exact value from /times")
        time_index = info.time_axis.timestamps.index(time)
    count = max(1, info.time_axis.count) if info.variables[variable].has_time else 1
    if not 0 <= time_index < count:
        raise HTTPException(status_code=422, detail="Time index outside variable time axis")
    return reader, variable, time_index


@router.get("/{dataset_id}/frame/stats")
def get_frame_stats(dataset_id: str, variable: Optional[str] = None,
                    time_index: int = Query(0, ge=0), time: Optional[str] = None,
                    options: AnalysisOptions = Depends(analysis_options)):
    reader, variable, time_index = resolve_request(dataset_id, variable, time_index, time)
    try:
        with playback_manager.lock:
            frame = reader.read_frame(variable, time_index)
            return analyze_slice(frame, options)[2]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}/grid")
def get_grid(dataset_id: str, variable: Optional[str] = None, time_index: int = Query(0, ge=0)):
    reader, variable, time_index = resolve_request(dataset_id, variable, time_index)
    try:
        with playback_manager.lock:
            return grid_metadata(reader.read_frame(variable, time_index))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}/frame")
def get_frame(
    dataset_id: str,
    variable: Optional[str] = Query(None, description="Variable name to render"),
    time_index: int = Query(0, ge=0, description="Zero-based index along time axis"),
    time: Optional[str] = Query(None, description="Optional ISO timestamp"),
    colormap: Optional[str] = Query(None, description="Colormap name"),
    min_val: Optional[float] = Query(None, description="Minimum color scale value"),
    max_val: Optional[float] = Query(None, description="Maximum color scale value", allow_inf_nan=False),
    options: AnalysisOptions = Depends(analysis_options)
):
    """
    Renders and streams a transparent RGBA PNG image for Cesium visualization.
    Uses two-tier caching for zero-latency frame playback.
    """
    try:
        reader, variable, time_index = resolve_request(dataset_id, variable, time_index, time)

        png_bytes = playback_manager.get_or_render_frame(
            dataset_id=dataset_id,
            variable=variable,
            time_index=time_index,
            colormap=colormap,
            min_val=min_val,
            max_val=max_val,
            analysis=options
        )

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache",
                "X-Dataset-ID": dataset_id,
                "X-Time-Index": str(time_index),
                "X-Variable": variable or reader._dataset_info.default_variable or ""
            }
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as e:
        logger.error(f"Error rendering frame for {dataset_id}: {e}")
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
        reader, variable, time_index = resolve_request(dataset_id, variable, time_index, time)
        with playback_manager.lock:
            return reader.get_point_value(lat=lat, lon=lon, var_name=variable, time_index=time_index)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    max_val: Optional[float] = Query(None, allow_inf_nan=False),
    options: AnalysisOptions = Depends(analysis_options)
):
    """Asynchronously prefetches upcoming frames into the fast cache for smooth playback."""
    try:
        resolve_request(dataset_id, variable, start_index)
        prefetched = await playback_manager.prefetch_range(
            dataset_id=dataset_id,
            variable=variable,
            start_index=start_index,
            count=count,
            colormap=colormap,
            min_val=min_val,
            max_val=max_val,
            analysis=options
        )
        return {"status": "ok", "prefetched_count": prefetched}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
