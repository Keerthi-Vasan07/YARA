"""
OPeNDAP SST API endpoints.

Provides date-based SST image generation from NOAA OISST v2.1 via OPeNDAP.
"""

import os
import logging
from io import BytesIO
from threading import Lock
from typing import Dict

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image

from server.data_sources.noaa_oisst import (
    NOAAOISSTSource,
    RateLimitError,
    DateNotAvailableError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/opendap/sst",
    tags=["OPeNDAP SST"],
)

source = NOAAOISSTSource()

# --- PNG Cache (date-keyed) ---
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "cache", "noaa_oisst",
)
os.makedirs(CACHE_DIR, exist_ok=True)

_png_cache: Dict[str, bytes] = {}  # date_str -> PNG bytes
_png_cache_lock = Lock()


# ─── Health / Metadata / Latest (unchanged) ───────────────────────────────────

@router.get("/health")
def health():
    try:
        available = source.is_available()
        return {
            "status": "online" if available else "offline",
            "source": "NOAA OISST v2.1",
            "protocol": "OPeNDAP",
            "variable": "sst",
        }
    except RateLimitError:
        return {
            "status": "rate_limited",
            "source": "NOAA OISST v2.1",
            "protocol": "OPeNDAP",
            "variable": "sst",
            "message": "NOAA rate limit active. Try again later.",
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/metadata")
def metadata():
    try:
        return source.get_metadata()
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "300"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to read OPeNDAP metadata: {exc}",
        )


@router.get("/latest")
def latest():
    try:
        return source.get_latest()
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "300"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to retrieve latest SST: {exc}",
        )


# ─── SST PNG rendering (shared by date-based and latest endpoints) ─────────

def _render_sst_png(data: dict) -> bytes:
    """
    Render an SST data dict to a transparent RGBA PNG.

    Geographic orientation:
        left   = -180°E
        right  = +180°E
        bottom = -90°S
        top    = +90°N

    Transparent pixels for land/missing values.
    """
    values = np.asarray(data["values"], dtype=np.float32)
    valid = np.isfinite(values) & (values != data["missing_value"])

    # SST display range
    vmin, vmax = -2.0, 35.0
    normalized = np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0)

    # Scientific color ramp: deep blue → cyan → green → yellow → red
    stops = np.array([
        [0.0,   0.0,   80.0],
        [0.0,   180.0, 255.0],
        [0.0,   220.0, 120.0],
        [255.0, 220.0, 0.0],
        [255.0, 60.0,  0.0],
    ], dtype=np.float32)

    positions = np.linspace(0.0, 1.0, len(stops))

    rgb = np.zeros((*values.shape, 3), dtype=np.float32)
    for channel in range(3):
        rgb[..., channel] = np.interp(normalized, positions, stops[:, channel])

    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])

    # NOAA OISST latitude: row 0 = -89.875 (south), last row = +89.875 (north)
    # Flip so north is at top of image
    rgba = np.flipud(rgba)

    # NOAA OISST longitude: col 0 = 0°E, col 720 = 180°E
    # Roll by width//2 so the image spans -180° to +180°
    width = rgba.shape[1]
    rgba = np.roll(rgba, width // 2, axis=1)

    image = Image.fromarray(rgba, mode="RGBA")
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _get_or_render_png(date_str: str) -> bytes:
    """
    Get cached PNG or render a new one for the given date.
    Checks memory → disk → generate from NOAA.
    """
    # Memory cache
    with _png_cache_lock:
        if date_str in _png_cache:
            logger.info(f"[SST] PNG cache HIT (memory): {date_str}")
            return _png_cache[date_str]

    # Disk cache
    png_file = os.path.join(CACHE_DIR, f"sst_{date_str}.png")
    if os.path.exists(png_file):
        try:
            with open(png_file, "rb") as f:
                png_bytes = f.read()
            with _png_cache_lock:
                _png_cache[date_str] = png_bytes
            logger.info(f"[SST] PNG cache HIT (disk): {date_str}")
            return png_bytes
        except Exception as e:
            logger.warning(f"[SST] Failed to read cached PNG for {date_str}: {e}")

    # Generate from NOAA data
    logger.info(f"[SST] PNG cache MISS: Generating SST PNG for {date_str}...")
    data = source.get_by_date(date_str)
    png_bytes = _render_sst_png(data)

    # Cache in memory
    with _png_cache_lock:
        _png_cache[date_str] = png_bytes

    # Cache on disk
    try:
        with open(png_file, "wb") as f:
            f.write(png_bytes)
        logger.info(f"[SST] Saved PNG for {date_str} to disk cache.")
    except Exception as e:
        logger.warning(f"[SST] Failed to write PNG to disk cache: {e}")

    return png_bytes


# ─── Date-based SST PNG endpoint ──────────────────────────────────────────────

@router.get("/{date}.png")
def sst_date_png(date: str):
    """
    Return SST image for a specific date as a transparent PNG.

    Path parameter:
        date: YYYY-MM-DD format (e.g., 2026-07-01)

    Returns:
        PNG image with transparent land/missing pixels.

    Error responses:
        404: Date not available in dataset
        429: NOAA rate limited (Retry-After header included)
        502: Backend/data processing error
    """
    # Validate date format
    if len(date) != 10 or date[4] != '-' or date[7] != '-':
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date}'. Expected YYYY-MM-DD.",
        )

    try:
        png_bytes = _get_or_render_png(date)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "300"},
        )
    except DateNotAvailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"[SST] Failed to generate PNG for {date}: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to generate SST image for {date}: {exc}",
        )


# ─── Legacy latest.png endpoint ──────────────────────────────────────────────

@router.get("/latest.png")
def latest_png():
    """
    Return the latest available SST as a transparent PNG.
    Convenience endpoint — determines most recent date and delegates.
    """
    try:
        # Determine latest date from dataset
        from datetime import datetime, timedelta
        try:
            dataset = source._open(2026)
            n_times = len(dataset["time"])
            base = datetime(2026, 1, 1)
            latest_date = (base + timedelta(days=n_times - 1)).strftime("%Y-%m-%d")
        except RateLimitError:
            raise
        except Exception:
            latest_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        png_bytes = _get_or_render_png(latest_date)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "300"},
        )
    except DateNotAvailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"[SST] Failed to generate latest PNG: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to generate SST image: {exc}",
        )
