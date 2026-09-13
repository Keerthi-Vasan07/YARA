"""
FastAPI backend for Ocean ECV visualization web application.

Serves Copernicus Marine SST/CHL/SIC/SLA/Kd490 data to the CesiumJS frontend.
All endpoints are organized in server/api/v1/ modules.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .data_service import sst_service
from .api import v1_router

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

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API v1 routes
app.include_router(v1_router)

