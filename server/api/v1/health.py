"""
Health and status endpoints.
"""

from fastapi import APIRouter, HTTPException, Request

from server.data_service import sst_service

router = APIRouter(tags=["health"])


@router.get("/")
async def root():
    """API root - health check."""
    return {"status": "ok", "service": "ECV Visualization API", "version": "1.0.0"}


@router.get("/health")
async def health():
    """
    Health check endpoint for Kubernetes liveness probe.
    Returns 200 if the service is healthy.
    """
    return {"status": "healthy"}


@router.get("/health/cors")
async def health_cors(request: Request):
    """
    Diagnostic endpoint to verify client origin and active CORS configuration.
    """
    from server.config import settings
    origin = request.headers.get("origin")
    effective_origins = settings.get_effective_cors_origins
    is_allowed = (origin in effective_origins) if origin else None
    return {
        "status": "ok",
        "client_origin": origin,
        "is_allowed": is_allowed,
        "effective_cors_origins": effective_origins,
    }


@router.get("/ready")
async def ready():
    """
    Readiness check endpoint for Kubernetes readiness probe.
    Returns 200 if the service is ready to accept traffic.
    """
    # Check if data service is initialized
    if not sst_service._initialized:
        raise HTTPException(503, "Service not ready - data service initializing")
    return {"status": "ready"}


@router.get("/api/earthkit-status")
async def earthkit_status():
    """
    Check availability of ECMWF Earthkit components.
    
    Earthkit provides enhanced data processing capabilities aligned with
    ECMWF's preferred tooling for climate data.
    """
    from server.earthkit_integration import get_earthkit_status
    
    status = get_earthkit_status()
    all_available = all(status.values())
    
    return {
        "status": "full" if all_available else "partial" if any(status.values()) else "none",
        "components": status,
        "documentation": "https://earthkit.readthedocs.io/"
    }
