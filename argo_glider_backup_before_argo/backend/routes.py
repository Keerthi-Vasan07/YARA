"""
YARA bridge for the existing standalone Argo/Glider module.

This file is intentionally only an adapter. It does not copy or reimplement
Argo/Glider data processing. The existing readers remain under argo_glider/.
If that module is unavailable, these endpoints return a clear 503 while the
main YARA ocean service continues to start.
"""
from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/argo-glider", tags=["Argo / Glider"])


def _jsonable(value: Any) -> Any:
    """Convert common reader outputs/dataclasses to JSON-safe structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _jsonable(value.dict())
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        return _jsonable(asdict(value))
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _reader(module_name: str):
    try:
        module = __import__(
            f"argo_glider.backend.{module_name}",
            fromlist=["*"],
        )
        return module
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Argo/Glider module unavailable: {exc}",
        ) from exc


async def _call_reader(module_name: str, function_name: str):
    module = _reader(module_name)
    function = getattr(module, function_name, None)
    if function is None:
        raise HTTPException(
            status_code=503,
            detail=f"{module_name}.{function_name} is not available",
        )
    try:
        result = function()
        if inspect.isawaitable(result):
            result = await result
        return _jsonable(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{function_name} failed: {exc}",
        ) from exc


@router.get("/health")
async def health():
    argo_ok = glider_ok = False
    errors = {}
    try:
        _reader("argo_reader")
        argo_ok = True
    except HTTPException as exc:
        errors["argo"] = exc.detail
    try:
        _reader("glider_reader")
        glider_ok = True
    except HTTPException as exc:
        errors["glider"] = exc.detail

    return {
        "status": "ok" if (argo_ok or glider_ok) else "degraded",
        "argo_reader_available": argo_ok,
        "glider_reader_available": glider_ok,
        "errors": errors,
    }


@router.get("/floats")
async def floats():
    return await _call_reader("argo_reader", "get_float_trajectories")


@router.get("/stats")
async def stats():
    data = await _call_reader("argo_reader", "get_float_trajectories")

    # Preserve reader-provided statistics when available.
    if isinstance(data, dict):
        for key in ("stats", "statistics"):
            if isinstance(data.get(key), dict):
                return _jsonable(data[key])

    items = data if isinstance(data, list) else []
    platform_count = len(items)
    observation_count = 0
    latest = None
    for item in items:
        if not isinstance(item, dict):
            continue
        observations = item.get("observations") or item.get("points") or item.get("trajectory") or []
        if isinstance(observations, list):
            observation_count += len(observations)
            for point in observations:
                if isinstance(point, dict):
                    t = point.get("time") or point.get("datetime")
                    if t is not None and (latest is None or str(t) > str(latest)):
                        latest = str(t)
    return {
        "platform_count": platform_count,
        "observation_count": observation_count,
        "latest_time": latest,
    }


@router.get("/gliders")
async def gliders():
    """Adapter for glider_reader.get_glider_trajectories().

    The existing reader returns a (trajectories, statuses, discovery) tuple
    so that FTP-level failures/partial results are visible even when the
    call itself doesn't raise. This endpoint only reshapes that tuple into
    JSON (no scientific processing) so the frontend can render trajectories
    and surface source errors without crashing the Argo/Glider panel.
    """
    module = _reader("glider_reader")
    function = getattr(module, "get_glider_trajectories", None)
    if function is None:
        raise HTTPException(
            status_code=503,
            detail="glider_reader.get_glider_trajectories is not available",
        )
    try:
        result = function()
        if inspect.isawaitable(result):
            result = await result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"get_glider_trajectories failed: {exc}",
        ) from exc

    if isinstance(result, tuple) and len(result) == 3:
        trajectories, statuses, discovery = result
        return {
            "gliders": _jsonable(trajectories),
            "statuses": _jsonable(statuses),
            "discovery": _jsonable(discovery),
        }
    return _jsonable(result)


@router.get("/sources")
async def sources():
    return {
        "argo": {
            "module": "argo_glider.backend.argo_reader",
            "endpoint": "/api/argo-glider/floats",
            "processing": "existing reader",
        },
        "glider": {
            "module": "argo_glider.backend.glider_reader",
            "endpoint": "/api/argo-glider/gliders",
            "processing": "existing reader",
        },
    }
