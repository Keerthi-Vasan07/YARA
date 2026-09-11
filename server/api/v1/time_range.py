"""
Time range endpoints for querying available data dates.
"""

from fastapi import APIRouter

from server.config import settings
from server.api.dependencies import (
    logger, HAS_DATABASE, HAS_STAC,
    get_cached_time_range, update_time_range_cache,
)

# Import STAC functions if available
if HAS_STAC:
    from server.stac.catalog import get_catalog

router = APIRouter(prefix="/api", tags=["time-range"])


def _build_time_range_response(cog_dates: list[str]) -> dict:
    """Build time range response from date list."""
    # Build years dict
    years = {}
    for date_str in cog_dates:
        try:
            parts = date_str.split("-")
            year = parts[0]
            month = parts[1]
            if year not in years:
                years[year] = []
            if month not in years[year]:
                years[year].append(month)
        except (ValueError, IndexError):
            continue
    
    # Sort months within each year
    for year in years:
        years[year] = sorted(years[year])
    
    return {
        "total_months": len(cog_dates),
        "start_date": cog_dates[0] if cog_dates else None,
        "end_date": cog_dates[-1] if cog_dates else None,
        "available_dates": cog_dates,
        "years": years
    }


@router.get("/time-range")
async def get_time_range():
    """Get available time range for SST data (fast: STAC cached)."""
    
    # Try STAC catalog first (fast path: <1ms from in-memory cache)
    if HAS_STAC:
        try:
            catalog = get_catalog()
            if catalog and "sst" in catalog.get("dates_by_variable", {}):
                cog_dates = sorted(catalog["dates_by_variable"]["sst"])
                return _build_time_range_response(cog_dates)
        except Exception:
            pass
    
    # Try database cache (fast path: <10ms)
    if HAS_DATABASE:
        cached = get_cached_time_range("sst")
        if cached:
            return _build_time_range_response(cached)
    
    # Get dates from configured source (local filesystem or Azure Blob)
    try:
        cog_dates = settings.list_available_dates("sst")
    except Exception as e:
        logger.warning(f"Error listing SST dates: {e}")
        cog_dates = []
    
    if not cog_dates:
        return {
            "total_months": 0,
            "start_date": None,
            "end_date": None,
            "available_dates": [],
            "years": {}
        }
    
    result = _build_time_range_response(cog_dates)
    
    # Update cache for next request
    if HAS_DATABASE and cog_dates:
        try:
            update_time_range_cache("sst", cog_dates)
        except Exception as e:
            logger.warning(f"Failed to update time range cache: {e}")
    
    return result


@router.get("/time-range/{variable}")
async def get_time_range_for_variable(variable: str):
    """Get available time range for a specific variable (fast: STAC cached)."""
    
    # Try STAC catalog first (fast path: <1ms from in-memory cache)
    if HAS_STAC:
        try:
            catalog = get_catalog()
            if catalog and variable in catalog.get("dates_by_variable", {}):
                cog_dates = sorted(catalog["dates_by_variable"][variable])
                result = _build_time_range_response(cog_dates)
                result["variable"] = variable
                return result
        except Exception:
            pass
    
    # Get dates from configured source (local filesystem or Azure Blob)
    try:
        cog_dates = settings.list_available_dates(variable)
    except Exception as e:
        logger.warning(f"Failed to list dates for {variable}: {e}")
        cog_dates = []
    
    if not cog_dates:
        if variable == "sst":
            from server.data_sources.noaa_oisst import NOAAOISSTSource
            try:
                meta = NOAAOISSTSource().get_metadata()
                # NOAA OISST v2.1 2026 dataset has daily records starting Jan 1 2026
                # Generate list of daily dates for 2026 dataset time size
                from datetime import datetime, timedelta
                n_days = meta.get("time", {}).get("size", 252)
                base_date = datetime(2026, 1, 1)
                noaa_dates = [(base_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_days)]
                result = _build_time_range_response(noaa_dates)
                result["variable"] = variable
                return result
            except Exception as e:
                logger.warning(f"Failed to fetch NOAA OISST dates: {e}")

        return {
            "variable": variable,
            "total_months": 0,
            "start_date": None,
            "end_date": None,
            "available_dates": [],
            "years": {}
        }
    
    result = _build_time_range_response(cog_dates)
    result["variable"] = variable
    return result
