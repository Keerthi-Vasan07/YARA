"""
Point query endpoints for click-to-query functionality.
"""

from pathlib import Path

from fastapi import APIRouter, Query, HTTPException
import numpy as np
import rasterio

from server.config import settings
from server.api.dependencies import TILES_DIR, VARIABLE_METADATA

router = APIRouter(prefix="/api", tags=["point-query"])


@router.get("/sst/point")
async def get_sst_point(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    lon: float = Query(..., description="Longitude (-180 to 180)"),
    lat: float = Query(..., description="Latitude (-90 to 90)")
):
    """
    Get SST value at a specific point (click-to-query).
    
    Reads directly from COG file - no GeoJSON overhead.
    Returns SST in Celsius with metadata.
    """
    # Validate date format
    try:
        parts = date.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise HTTPException(400, f"Invalid date format: {date}. Use YYYY-MM-DD")
    except Exception:
        raise HTTPException(400, f"Invalid date format: {date}. Use YYYY-MM-DD")
    
    # Get COG path from config (handles local or Azure)
    cog_path = settings.get_cog_path("sst", date)
    
    # For local paths, try fallback to legacy tiles
    if settings.products_source == "local" and not Path(cog_path).exists():
        legacy_path = TILES_DIR / f"sst_{date}.tif"
        if legacy_path.exists():
            cog_path = str(legacy_path)
        else:
            raise HTTPException(404, f"No SST data for {date}")
    
    try:
        with rasterio.open(cog_path) as ds:
            bounds = ds.bounds
            
            if not (bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top):
                return {
                    "date": date,
                    "lon": lon,
                    "lat": lat,
                    "sst": None,
                    "unit": "°C",
                    "message": "Location outside data bounds"
                }
            
            # Get pixel coordinates
            row, col = ds.index(lon, lat)
            
            # Read the value (small window for efficiency)
            window = rasterio.windows.Window(col, row, 1, 1)
            data = ds.read(1, window=window)
            value = data[0, 0]
            
            # Check for nodata
            nodata = ds.nodata
            if nodata is not None and value == nodata:
                return {
                    "date": date,
                    "lon": lon,
                    "lat": lat,
                    "sst": None,
                    "unit": "°C",
                    "message": "No data at this location (land or missing)"
                }
            
            # Decode int16 if needed
            if ds.dtypes[0] == 'int16':
                sst_celsius = float(value) * 0.01
            else:
                sst_celsius = float(value)
            
            # Format nicely
            return {
                "date": date,
                "lon": round(lon, 4),
                "lat": round(lat, 4),
                "sst": round(sst_celsius, 2),
                "unit": "°C",
                "source": "Copernicus Marine Service",
                "dataset": "L4 Gap-filled OSTIA"
            }
            
    except Exception as e:
        raise HTTPException(500, f"Error reading SST data: {str(e)}")


@router.get("/{variable}/point")
async def get_variable_point(
    variable: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    lon: float = Query(..., description="Longitude (-180 to 180)"),
    lat: float = Query(..., description="Latitude (-90 to 90)")
):
    """
    Get value at a specific point for any variable (SST, SIC, SLA, CHL, Kd490).
    
    Reads directly from COG file - no GeoJSON overhead.
    Returns value with appropriate units and metadata.
    """
    # Check if variable is supported
    if variable not in VARIABLE_METADATA:
        raise HTTPException(400, f"Unsupported variable: {variable}. Supported: {list(VARIABLE_METADATA.keys())}")
    
    meta = VARIABLE_METADATA[variable]
    
    # Get COG path from config (handles local or Azure)
    cog_path = settings.get_cog_path(variable, date)
    
    # For local paths, try fallback to legacy tiles
    if settings.products_source == "local" and not Path(cog_path).exists():
        legacy_path = TILES_DIR / f"{variable}_{date}.tif"
        if legacy_path.exists():
            cog_path = str(legacy_path)
        else:
            raise HTTPException(404, f"No {variable.upper()} data for {date}")
    
    try:
        with rasterio.open(cog_path) as ds:
            # Check if point is within bounds
            bounds = ds.bounds
            if not (bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top):
                return {
                    "date": date,
                    "variable": variable,
                    "lon": lon,
                    "lat": lat,
                    "value": None,
                    "unit": meta["unit"],
                    "message": "Location outside data bounds"
                }
            
            # Get pixel coordinates
            row, col = ds.index(lon, lat)
            
            # Read the value (small window for efficiency)
            window = rasterio.windows.Window(col, row, 1, 1)
            data = ds.read(1, window=window)
            value = data[0, 0]
            
            # Check for nodata
            nodata = ds.nodata
            if nodata is not None and (value == nodata or np.isnan(value)):
                return {
                    "date": date,
                    "variable": variable,
                    "lon": lon,
                    "lat": lat,
                    "value": None,
                    "unit": meta["unit"],
                    "message": f"No {variable.upper()} data at this location"
                }
            
            # Apply scaling if needed (e.g., int16 SST)
            if meta["dtype_check"] and ds.dtypes[0] == meta["dtype_check"]:
                final_value = float(value) * meta["scale"]
            else:
                final_value = float(value)
            
            # For SIC, handle transparency threshold (≤15% = no ice)
            if variable == "sic" and final_value <= 15:
                return {
                    "date": date,
                    "variable": variable,
                    "lon": lon,
                    "lat": lat,
                    "value": None,
                    "unit": meta["unit"],
                    "message": "No significant ice at this location"
                }
            
            return {
                "date": date,
                "variable": variable,
                "lon": round(lon, 4),
                "lat": round(lat, 4),
                "value": round(final_value, 3),
                "unit": meta["unit"],
                "name": meta["name"],
                "source": meta["source"],
                "dataset": meta["dataset"]
            }
            
    except Exception as e:
        raise HTTPException(500, f"Error reading {variable.upper()} data: {str(e)}")
