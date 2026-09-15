"""
main.py - FastAPI app exposing production-ready remote GLORYS12V1 thetao data
with compact binary Float32 responses, date & coordinate subsetting, and caching.
Multi-variable support: thetao (remote+local), so/mlotst/ohc_0_700m (local Dec 2004 only).

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.glorys_service import get_service, _ENV_FILE, ALLOWED_VARIABLES, VARIABLE_META
from backend import opendap_service
from backend.opendap_service import ALLOWED_OPENDAP_VARIABLES

app = FastAPI(title="GLORYS 3D Remote Ocean Volume API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Allowed variable values for query param validation (Literal list for OpenAPI docs)
_VARIABLE_CHOICES = sorted(ALLOWED_VARIABLES)


def _validate_variable(variable: str) -> str:
    """Validate variable name; raise HTTP 400 on invalid input."""
    v = variable.strip().lower()
    if v not in ALLOWED_VARIABLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown variable '{variable}'. "
                f"Allowed values: {_VARIABLE_CHOICES}. "
                "Use 'thetao' for potential temperature (remote+local), "
                "'so' for salinity, 'mlotst' for mixed layer thickness, "
                "'ohc_0_700m' for ocean heat content 0–700m (all three require local Dec 2004 fixture)."
            ),
        )
    return v


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/glorys/health")
def glorys_health():
    """
    Returns service status including credentials configured, mode, and remote_configured flag.
    Does NOT test actual Copernicus connectivity — use /api/glorys/test for that.
    """
    try:
        service = get_service()
        return service.health()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GLORYS service health check failed: {e}")


@app.get("/api/glorys/debug")
def glorys_debug():
    """
    Full pipeline status: env file, credentials, mode, fixture, cache.
    NEVER returns actual credential values.
    """
    import os
    service = get_service()
    h = service.health()
    return {
        "pipeline_status": {
            "env_file_path": str(_ENV_FILE),
            "env_file_found": h["env_file_found"],
            "GLORYS_DATA_MODE_env": os.getenv("GLORYS_DATA_MODE", "(not set)"),
            "mode_active": h["mode"],
            "credentials_username_set": h["credentials_configured"],  # boolean only, no value
            "credentials_password_set": h["credentials_configured"],  # boolean only, no value
            "remote_configured": h["remote_configured"],
            "local_fixture_available": h["local_fixture_available"],
            "climate_fixture_available": h["climate_fixture_available"],
            "cache_entries": h["cache_entries"],
            "supported_variables": h["supported_variables"],
        },
        "diagnosis": (
            "REMOTE: credentials configured and mode=remote. "
            "Requests will fetch live Copernicus Marine GLORYS data."
            if h["remote_configured"]
            else (
                f"NOT REMOTE: mode={h['mode']}, credentials_configured={h['credentials_configured']}. "
                "Check .env file and ensure COPERNICUSMARINE_USERNAME + COPERNICUSMARINE_PASSWORD are set."
            )
        ),
    }


@app.get("/api/glorys/test")
def glorys_test():
    """
    Performs a REAL minimal Copernicus Marine connectivity test.
    Makes a tiny actual request: 2020-01-15, lon 80-82, lat 10-12, depth 0-100.
    Returns shape, min/max/hash — proves authentication and dataset access work.
    DO NOT mock or skip. This is a real network call.
    """
    try:
        service = get_service()
        result = service.test_copernicus_connectivity()
        if not result.get("success"):
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Copernicus Marine connectivity test FAILED",
                    "error": result.get("error", "Unknown error"),
                    "traceback": result.get("traceback", ""),
                }
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connectivity test error: {e}")


@app.get("/api/glorys/time-range")
def glorys_time_range(
    variable: str = Query("thetao", description="Ocean variable. Allowed: thetao, so, mlotst, ohc_0_700m"),
):
    """
    Returns the dataset date range for the given variable.
    Climate variables (so, mlotst, ohc_0_700m) always return Dec 2004 range.
    thetao returns the full remote GLORYS12V1 range.
    """
    variable = _validate_variable(variable)
    try:
        service = get_service()
        return service.time_range(variable=variable)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query GLORYS time range: {e}")


@app.get("/api/glorys/metadata")
def glorys_metadata(
    date: str = Query(..., description="Selected date in YYYY-MM-DD format"),
    variable: str = Query("thetao", description="Ocean variable. Allowed: thetao, so, mlotst, ohc_0_700m"),
):
    """
    Returns actual spatial, depth, and variable metadata for the specified date and variable.
    Includes unit, label, is_2d flag, and default colormap range.
    """
    variable = _validate_variable(variable)
    try:
        service = get_service()
        return service.metadata(date_str=date, variable=variable)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {e}")


@app.get("/api/glorys/volume")
async def glorys_volume(
    date: str = Query("2020-01-15", description="Selected date YYYY-MM-DD"),
    variable: str = Query("thetao", description="Ocean variable. Allowed: thetao, so, mlotst, ohc_0_700m, chl, composite"),
    # Support camelCase and snake_case
    lonMin: Optional[float] = Query(None),
    lonMax: Optional[float] = Query(None),
    latMin: Optional[float] = Query(None),
    latMax: Optional[float] = Query(None),
    depthMin: Optional[float] = Query(None),
    depthMax: Optional[float] = Query(None),
    lon_min: Optional[float] = Query(None),
    lon_max: Optional[float] = Query(None),
    lat_min: Optional[float] = Query(None),
    lat_max: Optional[float] = Query(None),
    depth_min: Optional[float] = Query(None),
    depth_max: Optional[float] = Query(None),
    lod: int = Query(1, ge=0, le=2, description="Level of Detail: 0=Coarse, 1=Balanced, 2=Fine"),
    stride_lat: Optional[int] = Query(None, ge=1),
    stride_lon: Optional[int] = Query(None, ge=1),
    stride_depth: Optional[int] = Query(None, ge=1),
):
    """
    Extracts the requested GLORYS volume subset and streams it as a compact binary packet:
        [4-byte uint32 big-endian JSON metadata length] + [UTF-8 JSON metadata] + [Float32 raw bytes]

    Features:
      - Non-blocking execution via asyncio.to_thread with a strict 6.0-second timeout.
      - Fast local NetCDF extraction when coordinates fall inside local dataset bounds.
      - Automatic physical climatology fallback on remote timeout or error to prevent UI hang.
    """
    variable = _validate_variable(variable)
    try:
        final_lon_min   = lonMin   if lonMin   is not None else lon_min
        final_lon_max   = lonMax   if lonMax   is not None else lon_max
        final_lat_min   = latMin   if latMin   is not None else lat_min
        final_lat_max   = latMax   if latMax   is not None else lat_max
        final_depth_min = depthMin if depthMin is not None else depth_min
        final_depth_max = depthMax if depthMax is not None else depth_max

        from backend.services.volume_service import extract_volume_safe

        binary_payload = await extract_volume_safe(
            min_lat=final_lat_min,
            max_lat=final_lat_max,
            min_lon=final_lon_min,
            max_lon=final_lon_max,
            date_str=date,
            depth_min=final_depth_min,
            depth_max=final_depth_max,
            lod=lod,
            stride_lat=stride_lat,
            stride_lon=stride_lon,
            stride_depth=stride_depth,
            variable=variable,
            timeout=6.0,
        )

        return Response(content=binary_payload, media_type="application/octet-stream")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        err_str = str(e)
        if "HTTP 501" in err_str:
            raise HTTPException(status_code=501, detail=err_str)
        raise HTTPException(status_code=503, detail=err_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build volume: {e}")


@app.get("/api/glorys/profile")
def glorys_profile(
    lat: float = Query(...),
    lon: float = Query(...),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    time_index: int = Query(0, ge=0),
    variable: str = Query("thetao", description="Ocean variable. Allowed: thetao, so (3D). mlotst/ohc_0_700m return informational message."),
):
    """
    Returns vertical profile for the grid point nearest to (lat, lon).
    Works for thetao and so (3D variables with depth axis).
    Returns an informational message for 2D depth-integrated variables (mlotst, ohc_0_700m).
    """
    variable = _validate_variable(variable)
    try:
        service = get_service()
        return service.profile(lat=lat, lon=lon, date_str=date, variable=variable)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build profile: {e}")


@app.get("/api/glorys/point")
@app.get("/api/probe")
def get_point_probe(
    lat: float = Query(..., description="Latitude (-90 to +90)"),
    lon: float = Query(..., description="Longitude (-180 to +180)"),
    depth: float = Query(0.5, description="Depth in meters"),
    date: str = Query("2026-06-23", description="Date YYYY-MM-DD"),
    variable: str = Query("thetao", description="Ocean variable"),
):
    """
    Point probe telemetry extraction strictly respecting NetCDF and global land masks.
    Returns status: 'TERRESTRIAL LANDMASS' and null parameters when querying continental land.
    """
    try:
        service = get_service()
        return service.point_probe(lat=lat, lon=lon, depth=depth, date_str=date, variable=variable)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract point probe: {e}")


@app.get("/api/ocean/vertical-column")
async def ocean_vertical_column(
    lat: float = Query(..., description="Latitude (-90 to +90)"),
    lon: float = Query(..., description="Longitude (-180 to +180)"),
    max_depth: float = Query(1000.0, ge=10.0, le=6000.0, description="Maximum profile depth in meters"),
):
    """
    3D Subsurface Column Profiling endpoint.
    Extracts standardized vertical depth profiles for:
      1. Temperature (°C)
      2. Salinity (PSU)
      3. Chlorophyll-a (mg/m³)
    Standardized vertical depth levels: [0, 5, 10, 25, 50, 75, 100, 150, 200, 300, 500, 750, 1000] m.
    """
    try:
        from backend.column_profile_service import fetch_vertical_profile
        data = await fetch_vertical_profile(lat=lat, lon=lon, max_depth=max_depth)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch subsurface vertical column: {e}")



@app.get("/api/glorys/info")
def glorys_info():
    """Backwards-compatibility endpoint."""
    try:
        service = get_service()
        time_info = service.time_range(variable="thetao")
        meta = service.metadata(date_str=time_info["end"], variable="thetao")
        return {
            "variable": "thetao",
            "long_name": "Sea water potential temperature",
            "units": "degrees_C",
            "dimensions": ["depth", "latitude", "longitude"],
            "shape": [meta["depth"]["count"], meta["latitude"]["count"], meta["longitude"]["count"]],
            "depth": meta["depth"]["values"],
            "n_depth": meta["depth"]["count"],
            "latitude_min": meta["latitude"]["min"],
            "latitude_max": meta["latitude"]["max"],
            "longitude_min": meta["longitude"]["min"],
            "longitude_max": meta["longitude"]["max"],
            "n_latitude": meta["latitude"]["count"],
            "n_longitude": meta["longitude"]["count"],
            "temperature_min": -2.5,
            "temperature_max": 35.0,
            "available_time": [time_info["end"]],
            "n_time": 1,
            "mode": time_info.get("mode", "remote"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read GLORYS info: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# OPeNDAP-sourced subsurface volume endpoint
# ─────────────────────────────────────────────────────────────────────────────

_OPENDAP_VARIABLE_CHOICES = sorted(ALLOWED_OPENDAP_VARIABLES)


@app.get("/api/v1/subsurface/volume")
async def subsurface_volume(
    variable: str = Query(
        "temperature",
        description=(
            "Derived variable to extract. "
            f"Allowed: {sorted(ALLOWED_OPENDAP_VARIABLES)}"
        ),
    ),
    lat_min: Optional[float] = Query(None, description="Minimum latitude"),
    lat_max: Optional[float] = Query(None, description="Maximum latitude"),
    lon_min: Optional[float] = Query(None, description="Minimum longitude"),
    lon_max: Optional[float] = Query(None, description="Maximum longitude"),
    depth_min: Optional[float] = Query(None, description="Minimum depth in metres"),
    depth_max: Optional[float] = Query(None, description="Maximum depth in metres"),
    downsample_stride: int = Query(
        1, ge=1, le=20,
        description="Spatial stride applied to lat/lon before loading (1 = full resolution)",
    ),
    opendap_url: Optional[str] = Query(None, description="Custom OPeNDAP primary/temperature dataset URL"),
    opendap_salt_url: Optional[str] = Query(None, description="Custom OPeNDAP salinity dataset URL"),
    opendap_ucur_url: Optional[str] = Query(None, description="Custom OPeNDAP u-current dataset URL"),
    opendap_vcur_url: Optional[str] = Query(None, description="Custom OPeNDAP v-current dataset URL"),
):
    """
    Extract a 3D ocean volume from a remote THREDDS OPeNDAP endpoint with non-blocking
    6.0s timeout and resilient synthetic fallback. Returns a compact binary packet.
    """
    variable = variable.strip().lower()
    if variable not in ALLOWED_OPENDAP_VARIABLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown variable '{variable}'. "
                f"Allowed values: {_OPENDAP_VARIABLE_CHOICES}."
            ),
        )

    try:
        from backend.services.volume_service import extract_volume_safe
        binary_payload = await extract_volume_safe(
            min_lat=lat_min,
            max_lat=lat_max,
            min_lon=lon_min,
            max_lon=lon_max,
            date_str="2026-06-23",
            depth_min=depth_min,
            depth_max=depth_max,
            lod=downsample_stride,
            variable=variable,
            timeout=6.0,
        )
        return Response(content=binary_payload, media_type="application/octet-stream")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Subsurface volume error: {e}")

