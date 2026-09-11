"""
Tile endpoints for XYZ map tiles.
"""

import asyncio
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, Query, Response
from fastapi.responses import FileResponse
from PIL import Image
import rasterio
import rasterio.errors

from server.config import settings
from server.data_service import sst_service
from server.tile_server import render_tile, TRANSPARENT_TILE_PNG
from server.api.dependencies import TILES_DIR

router = APIRouter(prefix="/api/v1", tags=["tiles"])

# Thread pool executor for CPU/IO-bound tile rendering
_tile_executor = None


def _get_executor():
    """Lazily create a thread pool for tile rendering."""
    global _tile_executor
    if _tile_executor is None:
        from concurrent.futures import ThreadPoolExecutor
        _tile_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tile")
    return _tile_executor


def _wants_webp(accept: str | None) -> bool:
    """Check if the client Accept header includes image/webp."""
    return accept is not None and "image/webp" in accept


@router.get("/sst/image/{date}.png")
async def get_sst_image(
    date: str,
    resolution: int = Query(512, ge=128, le=2048, description="Image resolution")
):
    """
    Get SST data as a styled PNG image for overlay on map.
    
    Returns a georeferenced PNG with thermal colormap applied.
    """
    # Check for pre-generated tile
    tile_path = TILES_DIR / f"sst_{date}.tif"
    if tile_path.exists():
        return FileResponse(tile_path, media_type="image/tiff")
    
    # Generate on-the-fly
    png_bytes = await sst_service.get_sst_png(date, resolution)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/tiles/{variable}/{date}/{z}/{x}/{y}.png")
async def get_variable_tile(
    variable: str,
    date: str,
    z: int,
    x: int,
    y: int,
    vmin: float = Query(None, description="Minimum value for color scale"),
    vmax: float = Query(None, description="Maximum value for color scale"),
    threshold_min: float = Query(None, description="Mask values below this threshold (transparent)"),
    threshold_max: float = Query(None, description="Mask values above this threshold (transparent)"),
    accept: Optional[str] = Header(None),
):
    """
    Get XYZ tile for any variable from pre-generated COG.
    
    Supports: sst, sic, sla, chl, kd490, rrs
    Content-negotiation: returns WebP if Accept: image/webp, else PNG.
    
    Threshold masking: Use threshold_min and/or threshold_max to show only values
    within a specific range. Values outside the threshold become transparent.
    """
    # Get COG path from config (handles local or Azure)
    cog_path = settings.get_cog_path(variable, date)
    
    # For local paths, check existence
    if settings.products_source == "local" and not Path(cog_path).exists():
        return Response(
            content=TRANSPARENT_TILE_PNG,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"}
        )
    
    # Choose output format based on Accept header
    fmt = "webp" if _wants_webp(accept) else "png"
    
    # Render tile in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    try:
        tile_data = await loop.run_in_executor(
            _get_executor(),
            render_tile,
            cog_path, z, x, y, variable, 256, vmin, vmax, True, fmt,
            threshold_min, threshold_max,
        )
    except rasterio.errors.RasterioIOError:
        # Transient IO error — short cache so browser retries soon
        return Response(
            content=TRANSPARENT_TILE_PNG,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=60"}
        )
    
    if tile_data is None:
        # Tile outside COG bounds — stable, ok to cache longer
        return Response(
            content=TRANSPARENT_TILE_PNG,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    
    media = "image/webp" if fmt == "webp" else "image/png"
    return Response(
        content=tile_data,
        media_type=media,
        headers={"Cache-Control": "public, max-age=86400"}
    )


# ---------------------------------------------------------------------------
# TileJSON endpoint with LRU caching
# ---------------------------------------------------------------------------
@lru_cache(maxsize=256)
def _cached_tilejson(variable: str, date: str) -> dict:
    """Build TileJSON response (cached — COG bounds never change for a given date)."""
    from rasterio import open as rio_open
    
    cog_path = settings.get_cog_path(variable, date)
    
    if settings.products_source == "local" and not Path(cog_path).exists():
        return {"error": f"No tile for {variable} on {date}"}
    
    config = {}
    try:
        datasets_path = Path(__file__).parent.parent.parent / "datasets.json"
        with open(datasets_path) as f:
            config = json.load(f).get(variable, {})
    except Exception:
        pass
    
    try:
        with rio_open(cog_path) as ds:
            bounds = ds.bounds
            west, south, east, north = bounds.left, bounds.bottom, bounds.right, bounds.top
    except rasterio.errors.RasterioIOError:
        return {"error": f"No tile for {variable} on {date}"}
    
    var_name = config.get("name", variable.upper())
    
    return {
        "tilejson": "2.2.0",
        "name": f"{var_name} {date}",
        "description": f"{var_name} for {date}",
        "version": "1.0.0",
        "attribution": "Copernicus Marine Service",
        "tiles": [f"/api/v1/tiles/{variable}/{date}/{{z}}/{{x}}/{{y}}.png"],
        "bounds": [west, south, east, north],
        "minzoom": 0,
        "maxzoom": 8,
        "center": [(west + east) / 2, (south + north) / 2, 2]
    }


@router.get("/tiles/{variable}/tilejson/{date}.json")
async def get_variable_tilejson(variable: str, date: str):
    """Get TileJSON metadata for any variable and date (cached)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(), _cached_tilejson, variable, date)
