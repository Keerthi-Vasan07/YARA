"""
Timeseries endpoints for temporal data extraction.
"""

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query
import rasterio

from server.config import settings
from server.api.dependencies import logger

router = APIRouter(prefix="/api", tags=["timeseries"])


@router.get("/sst/timeseries")
async def get_sst_timeseries(
    lon: float = Query(..., description="Longitude (-180 to 180)"),
    lat: float = Query(..., description="Latitude (-90 to 90)"),
    limit: int = Query(24, ge=1, le=120, description="Maximum number of recent dates")
):
    """
    Get SST timeseries for a specific point across all available dates.
    
    Reads from all available COG files and returns temperature history.
    Limited to most recent dates for performance.
    """
    # Get all available dates from configured source
    try:
        all_dates = settings.list_available_dates("sst")
    except Exception as e:
        logger.warning(f"Error listing SST dates: {e}")
        all_dates = []
    
    # Take most recent dates
    recent_dates = sorted(all_dates, reverse=True)[:limit]
    
    if not recent_dates:
        return {
            "location": {"lon": lon, "lat": lat},
            "timeseries": [],
            "count": 0,
            "message": "No SST data available"
        }
    
    def read_point(date_str):
        """Read SST value at a specific point from a COG."""
        try:
            cog_path = settings.get_cog_path("sst", date_str)
            with rasterio.open(cog_path) as ds:
                bounds = ds.bounds
                if not (bounds.left <= lon <= bounds.right and bounds.bottom <= lat <= bounds.top):
                    return None
                
                row, col = ds.index(lon, lat)
                window = rasterio.windows.Window(col, row, 1, 1)
                data = ds.read(1, window=window)
                value = data[0, 0]
                
                nodata = ds.nodata
                if nodata is not None and value == nodata:
                    return None
                
                if ds.dtypes[0] == 'int16':
                    sst_celsius = float(value) * 0.01
                else:
                    sst_celsius = float(value)
                
                return {
                    "date": date_str,
                    "value": round(sst_celsius, 2)
                }
        except Exception:
            return None
    
    # Read all dates in parallel
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(read_point, recent_dates))
    
    timeseries = [r for r in results if r is not None]
    timeseries.sort(key=lambda x: x["date"])  # Sort chronologically
    
    # Calculate basic stats
    values = [p["value"] for p in timeseries]
    stats = None
    if values:
        stats = {
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "mean": round(sum(values) / len(values), 2),
        }
    
    return {
        "location": {"lon": round(lon, 4), "lat": round(lat, 4)},
        "timeseries": timeseries,
        "count": len(timeseries),
        "stats": stats
    }
