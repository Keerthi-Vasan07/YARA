"""
FastAPI backend for Ocean ECV visualization web application.

Serves Copernicus Marine SST/CHL/SIC/SLA/Kd490 data to the CesiumJS frontend.
All endpoints are organized in server/api/v1/ modules.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .data_service import sst_service
from .api import v1_router

# Optional isolated Argo/Glider overlay. Failure here must never prevent
# the core YARA ocean application from starting.
try:
    from argo_glider.backend.routes import router as argo_glider_router
except Exception as exc:
    argo_glider_router = None
    logger_bootstrap = logging.getLogger(__name__)
    logger_bootstrap.warning("Argo/Glider overlay unavailable: %s", exc)

# Try to import database module (optional)
try:
    from .database import db, sync_products_from_filesystem
    HAS_DATABASE = True
except ImportError:
    HAS_DATABASE = False

logger = logging.getLogger(__name__)

# Ensure YARA application loggers emit at INFO level.
# Uvicorn captures Python's logging — this makes [YARA API/OPeNDAP/RASTER] messages visible.
logging.getLogger("server").setLevel(logging.INFO)
logging.getLogger("server.api").setLevel(logging.INFO)
logging.getLogger("server.data_sources").setLevel(logging.INFO)

# Directory for pre-computed COG tiles
PRODUCTS_DIR = Path(__file__).parent / "products"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup data service."""
    print("Initializing SST data service...")
    await sst_service.initialize()
    
    # Initialize database and sync products
    if HAS_DATABASE:
        try:
            db.init_sync()
            sync_products_from_filesystem(str(PRODUCTS_DIR), "sst")
            print("Database initialized and products synced.")
        except Exception as e:
            print(f"Database init failed (will use fallback): {e}")
    
    print("SST data service ready.")
    yield
    print("Shutting down SST data service...")
    await sst_service.shutdown()
    
    if HAS_DATABASE:
        db.close()


app = FastAPI(
    title="Ocean ECV Visualization API",
    description="API for serving Copernicus Marine Essential Climate Variables",
    version="0.3.0",
    lifespan=lifespan
)

def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    clean_origin = origin.strip().rstrip("/")
    if clean_origin in settings.get_effective_cors_origins:
        return True
    if clean_origin.startswith("https://") and clean_origin.endswith(".qzz.io"):
        return True
    return False

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_effective_cors_origins,
    allow_origin_regex=r"https://.*\.qzz\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Date-Matched",
        "X-Time-Matched",
        "X-Variable",
        "X-Dataset-Id",
        "X-Bounds-West",
        "X-Bounds-South",
        "X-Bounds-East",
        "X-Bounds-North",
        "X-Raster-Width",
        "X-Raster-Height",
        "Content-Type",
        "Content-Length",
        "Access-Control-Allow-Origin",
    ],
)

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get("origin")
    headers = dict(exc.headers or {})
    if is_origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )

@app.exception_handler(Exception)
async def custom_global_exception_handler(request: Request, exc: Exception):
    logger.exception("[YARA API ERROR] Unhandled exception on %s: %s", request.url.path, exc)
    origin = request.headers.get("origin")
    headers = {}
    if is_origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"},
        headers=headers,
    )

# Include all API v1 routes
app.include_router(v1_router)

if argo_glider_router is not None:
    app.include_router(argo_glider_router)

