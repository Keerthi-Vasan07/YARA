"""
Database module for ARCO Ocean ECV platform.

Uses PostgreSQL for metadata caching, product catalog, and future features.
Falls back to SQLite for local development without Docker.
"""

import os
import json
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, 
    Boolean, Text, JSON, Index, UniqueConstraint, select, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Database URL from environment or default to local postgres
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://arco:arco_dev_2026@localhost:53362/arco_ocean"
)

# For async operations
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# SQLAlchemy setup
Base = declarative_base()


class Product(Base):
    """A data product (SST, CHL, etc.) with its metadata."""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True)
    variable = Column(String(50), nullable=False)  # sst, chl, etc.
    date = Column(Date, nullable=False)
    stream = Column(String(20), default="l4")  # l3, l4, nrt, rep
    
    # File info
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)
    
    # Bounds
    west = Column(Float)
    south = Column(Float)
    east = Column(Float)
    north = Column(Float)
    
    # Statistics
    min_value = Column(Float)
    max_value = Column(Float)
    mean_value = Column(Float)
    valid_fraction = Column(Float)
    
    # Metadata
    source = Column(String(200))  # e.g., "Copernicus OSTIA L4"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('variable', 'date', 'stream', name='uix_product'),
        Index('ix_product_variable_date', 'variable', 'date'),
    )


class TimeRange(Base):
    """Cached time range metadata for fast API responses."""
    __tablename__ = "time_ranges"
    
    id = Column(Integer, primary_key=True)
    variable = Column(String(50), nullable=False, unique=True)
    
    # Range info
    start_date = Column(Date)
    end_date = Column(Date)
    total_dates = Column(Integer, default=0)
    
    # Cached JSON for quick retrieval
    available_dates = Column(JSON)  # List of date strings
    years = Column(JSON)  # Dict of year -> months
    
    # Cache management
    updated_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(200))  # Where the data came from


class Database:
    """Database connection manager."""
    
    def __init__(self, url: str = DATABASE_URL):
        self.url = url
        self.engine = None
        self.async_engine = None
        self.SessionLocal = None
        self.AsyncSessionLocal = None
        self._initialized = False
        self._init_failed = False
    
    def init_sync(self) -> bool:
        """Initialize synchronous database connection."""
        if self._init_failed:
            return False
        try:
            self.engine = create_engine(self.url, pool_pre_ping=True)
            self.SessionLocal = sessionmaker(bind=self.engine)
            
            # Create tables
            Base.metadata.create_all(self.engine)
            self._initialized = True
            logger.info(f"Database initialized: {self.url.split('@')[-1]}")
            return True
        except Exception as e:
            logger.warning(f"Database init failed: {e}")
            self._init_failed = True
            return False
    
    async def init_async(self) -> bool:
        """Initialize async database connection."""
        try:
            async_url = self.url.replace("postgresql://", "postgresql+asyncpg://")
            self.async_engine = create_async_engine(async_url, pool_pre_ping=True)
            self.AsyncSessionLocal = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables (sync for simplicity)
            if not self._initialized:
                self.init_sync()
            
            return True
        except Exception as e:
            logger.warning(f"Async database init failed: {e}")
            return False
    
    def get_session(self) -> Session:
        """Get a sync database session."""
        if not self.SessionLocal:
            if not self.init_sync():
                raise RuntimeError("Database not available")
        return self.SessionLocal()
    
    @asynccontextmanager
    async def get_async_session(self):
        """Get an async database session."""
        if not self.AsyncSessionLocal:
            await self.init_async()
        async with self.AsyncSessionLocal() as session:
            yield session
    
    def close(self):
        """Close database connections."""
        if self.engine:
            self.engine.dispose()


# Global database instance
db = Database()


def get_cached_time_range(variable: str = "sst") -> Optional[Dict[str, Any]]:
    """Get cached time range from database."""
    try:
        with db.get_session() as session:
            result = session.query(TimeRange).filter(
                TimeRange.variable == variable
            ).first()
            
            if result:
                return {
                    "start_date": result.start_date.isoformat() if result.start_date else None,
                    "end_date": result.end_date.isoformat() if result.end_date else None,
                    "total_months": result.total_dates,
                    "available_dates": result.available_dates or [],
                    "years": result.years or {},
                    "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                    "source": result.source,
                }
            return None
    except Exception as e:
        logger.warning(f"Failed to get cached time range: {e}")
        return None


def update_time_range_cache(
    variable: str,
    available_dates: List[str],
    source: str = "local"
) -> bool:
    """Update the time range cache in database."""
    try:
        with db.get_session() as session:
            # Build years dict
            years = {}
            for date_str in available_dates:
                try:
                    year = date_str[:4]
                    month = int(date_str[5:7])
                    if year not in years:
                        years[year] = []
                    if month not in years[year]:
                        years[year].append(month)
                except (ValueError, IndexError):
                    continue
            
            # Sort months
            for year in years:
                years[year] = sorted(years[year])
            
            # Parse dates
            start_date = None
            end_date = None
            if available_dates:
                try:
                    start_date = datetime.strptime(available_dates[0], "%Y-%m-%d").date()
                    end_date = datetime.strptime(available_dates[-1], "%Y-%m-%d").date()
                except ValueError:
                    pass
            
            # Upsert
            existing = session.query(TimeRange).filter(
                TimeRange.variable == variable
            ).first()
            
            if existing:
                existing.start_date = start_date
                existing.end_date = end_date
                existing.total_dates = len(available_dates)
                existing.available_dates = available_dates
                existing.years = years
                existing.updated_at = datetime.utcnow()
                existing.source = source
            else:
                new_range = TimeRange(
                    variable=variable,
                    start_date=start_date,
                    end_date=end_date,
                    total_dates=len(available_dates),
                    available_dates=available_dates,
                    years=years,
                    source=source,
                )
                session.add(new_range)
            
            session.commit()
            logger.info(f"Updated time range cache for {variable}: {len(available_dates)} dates")
            return True
    except Exception as e:
        logger.error(f"Failed to update time range cache: {e}")
        return False


def register_product(
    variable: str,
    date_str: str,
    file_path: str,
    stats: Dict[str, Any],
    stream: str = "l4",
    source: str = None
) -> bool:
    """Register a product in the database."""
    try:
        with db.get_session() as session:
            product_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Check if exists
            existing = session.query(Product).filter(
                Product.variable == variable,
                Product.date == product_date,
                Product.stream == stream
            ).first()
            
            bounds = stats.get("bounds", [-180, -90, 180, 90])
            
            if existing:
                existing.file_path = file_path
                existing.file_size_bytes = stats.get("file_size")
                existing.west = bounds[0]
                existing.south = bounds[1]
                existing.east = bounds[2]
                existing.north = bounds[3]
                existing.min_value = stats.get("min")
                existing.max_value = stats.get("max")
                existing.mean_value = stats.get("mean")
                existing.valid_fraction = stats.get("valid_fraction")
                existing.source = source
            else:
                product = Product(
                    variable=variable,
                    date=product_date,
                    stream=stream,
                    file_path=file_path,
                    file_size_bytes=stats.get("file_size"),
                    west=bounds[0],
                    south=bounds[1],
                    east=bounds[2],
                    north=bounds[3],
                    min_value=stats.get("min"),
                    max_value=stats.get("max"),
                    mean_value=stats.get("mean"),
                    valid_fraction=stats.get("valid_fraction"),
                    source=source,
                )
                session.add(product)
            
            session.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to register product: {e}")
        return False


def get_available_products(variable: str = "sst") -> List[Dict[str, Any]]:
    """Get all available products for a variable."""
    try:
        with db.get_session() as session:
            products = session.query(Product).filter(
                Product.variable == variable
            ).order_by(Product.date).all()
            
            return [
                {
                    "date": p.date.isoformat(),
                    "stream": p.stream,
                    "file_path": p.file_path,
                    "bounds": [p.west, p.south, p.east, p.north],
                    "stats": {
                        "min": p.min_value,
                        "max": p.max_value,
                        "mean": p.mean_value,
                        "valid_fraction": p.valid_fraction,
                    },
                    "source": p.source,
                }
                for p in products
            ]
    except Exception as e:
        logger.warning(f"Failed to get products: {e}")
        return []


def sync_products_from_filesystem(products_dir: str, variable: str = "sst"):
    """Scan filesystem and sync COG products to database."""
    from pathlib import Path
    import rasterio
    
    product_path = Path(products_dir) / variable
    if not product_path.exists():
        return
    
    cog_files = list(product_path.glob("*.tif"))
    logger.info(f"Syncing {len(cog_files)} {variable} products to database")
    
    for cog in cog_files:
        date_str = cog.stem
        
        # Read stats from COG
        try:
            with rasterio.open(cog) as src:
                stats = {
                    "bounds": list(src.bounds),
                    "file_size": cog.stat().st_size,
                }
                
                # Read a sample to get value range
                data = src.read(1)
                nodata = src.nodata
                if nodata is not None:
                    valid = data != nodata
                else:
                    valid = ~(data == 0)
                
                if valid.any():
                    # Handle int16 encoded SST
                    if src.dtypes[0] == 'int16' and variable == 'sst':
                        valid_data = data[valid].astype(float) * 0.01
                    else:
                        valid_data = data[valid].astype(float)
                    
                    stats["min"] = float(valid_data.min())
                    stats["max"] = float(valid_data.max())
                    stats["mean"] = float(valid_data.mean())
                    stats["valid_fraction"] = float(valid.sum() / data.size)
            
            register_product(
                variable=variable,
                date_str=date_str,
                file_path=str(cog),
                stats=stats,
                stream="l4",
                source="Copernicus Marine"
            )
        except Exception as e:
            logger.warning(f"Failed to process {cog}: {e}")
    
    # Update time range cache
    products = get_available_products(variable)
    if products:
        dates = sorted([p["date"] for p in products])
        update_time_range_cache(variable, dates, source="database")
