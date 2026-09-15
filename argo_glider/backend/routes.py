"""
YARA bridge for the existing standalone Argo/Glider module.

This file is intentionally only an adapter. It does not copy or reimplement
Argo/Glider data processing. The existing readers remain under argo_glider/.
If that module is unavailable, these endpoints return a clear 503 while the
main YARA ocean service continues to start.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/argo-glider", tags=["Argo / Glider"])

# Upstream source behind each reader, used for clear error reporting.
_SOURCE_OF = {
    "argo_reader": "INCOIS",
    "glider_reader": "IFREMER",
}


def _safe_reason(exc: Exception) -> str:
    """Short, non-leaky explanation of why an upstream fetch failed.

    The full exception (with URL and stack) is logged server-side; only this
    summary is returned to the browser.
    """
    name = type(exc).__name__
    text = f"{name} {exc}"
    if "SSL" in text or "Certificate" in text:
        return "TLS certificate verification failed"
    if "Timeout" in name or "timed out" in text:
        return "the source timed out"
    if "Connection" in name or "Resolution" in text:
        return "the source could not be reached"
    if "HTTPError" in name or "status" in text.lower():
        return "the source returned an error response"
    return "the source returned an unexpected error"


def _upstream_failure(module_name: str, exc: Exception) -> HTTPException:
    """Log the real cause, return a clean 502 the UI can display."""
    source = _SOURCE_OF.get(module_name, module_name)
    logger.exception("%s data source request failed (%s)", source, module_name)
    return HTTPException(
        status_code=502,
        detail={
            "error": f"{source} data source unavailable",
            "source": source,
            "reason": _safe_reason(exc),
        },
    )

# NOTE: every route below is declared with a plain `def`, not `async def`.
# The readers do blocking network I/O (requests -> INCOIS, ftplib -> IFREMER).
# Declaring them `async` would run that I/O directly on the event loop and
# freeze the whole YARA app — a glider fetch measured ~25s and blocked
# unrelated endpoints for the entire duration. With `def`, FastAPI runs each
# handler in a threadpool, so a slow or failing Argo/Glider source can never
# stall the Copernicus/OPeNDAP pipeline. The standalone module did the same.


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


def _call_reader(module_name: str, function_name: str):
    module = _reader(module_name)
    function = getattr(module, function_name, None)
    if function is None:
        raise HTTPException(
            status_code=503,
            detail=f"{module_name}.{function_name} is not available",
        )
    try:
        return _jsonable(function())
    except HTTPException:
        raise
    except Exception as exc:
        raise _upstream_failure(module_name, exc) from exc


@router.get("/health")
def health():
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
def floats():
    return _call_reader("argo_reader", "get_float_trajectories")


@router.get("/stats")
def stats():
    data = _call_reader("argo_reader", "get_float_trajectories")

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
def gliders(refresh: bool = False):
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
        # force_refresh bypasses the reader's own cache (same contract the
        # standalone module exposed as /api/gliders?refresh=true).
        result = function(force_refresh=refresh)
    except HTTPException:
        raise
    except Exception as exc:
        raise _upstream_failure("glider_reader", exc) from exc

    if isinstance(result, tuple) and len(result) == 3:
        trajectories, statuses, discovery = result
        return {
            "gliders": _jsonable(trajectories),
            "statuses": _jsonable(statuses),
            "discovery": _jsonable(discovery),
        }
    return _jsonable(result)


@router.get("/sources")
def sources():
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
