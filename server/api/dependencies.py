"""
Shared dependencies for API routes.

Contains common imports, constants, and utilities used across multiple endpoints.
"""

import logging
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
import zarr

from server.config import settings

logger = logging.getLogger(__name__)

# Directory for pre-computed COG tiles
PRODUCTS_DIR = Path(__file__).parent.parent / "products"
# Legacy tiles directory (ERA5 ARCO)
TILES_DIR = Path(__file__).parent.parent / "tiles"
# Zarr stores directory
ZARR_DIR = Path(__file__).parent.parent / "zarr"
# STAC catalog directory
STAC_DIR = Path(__file__).parent.parent / "stac"


def open_zarr_group(variable: str) -> zarr.Group | None:
    """
    Open a Zarr group for reading, from local or Azure.
    
    - products_source="local": reads from ZARR_DIR/{variable}.zarr
    - products_source="azure": reads from Azure Blob via fsspec/adlfs
    
    Returns:
        zarr.Group or None if not found
    """
    if settings.products_source == "azure" and settings.azure_storage_account:
        try:
            import adlfs  # noqa: F401
            
            container = getattr(settings, 'azure_zarr_container', 'zarr')
            if not container:
                import os
                container = os.environ.get('ARCO_AZURE_ZARR_CONTAINER', os.environ.get('AZURE_STORAGE_ZARR_CONTAINER', 'zarr'))
            
            sas_token = settings.azure_storage_sas_token
            if not sas_token:
                logger.warning(f"No SAS token for Azure Zarr read of {variable}")
                return None
            
            url = f"abfs://{container}/{variable}.zarr"
            storage_options = {
                "account_name": settings.azure_storage_account,
                "sas_token": sas_token.strip('"').lstrip('?'),
            }
            
            store = zarr.storage.FsspecStore.from_url(url, storage_options=storage_options)
            return zarr.open_group(store, mode='r')
        except Exception as e:
            logger.debug(f"Azure Zarr not available for {variable}: {e}")
            # Fall through to local
    
    # Local filesystem
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if zarr_path.exists():
        return zarr.open_group(str(zarr_path), mode='r')
    
    return None


# Try to import database module (optional)
try:
    from server.database import (
        db, get_cached_time_range, update_time_range_cache,
        sync_products_from_filesystem
    )
    HAS_DATABASE = True
except ImportError:
    HAS_DATABASE = False
    db = None
    get_cached_time_range = None
    update_time_range_cache = None
    sync_products_from_filesystem = None

# Try to import STAC module (optional)
try:
    from server.stac import get_collection, get_item
    from server.stac.catalog import get_catalog, build_catalog, STAC_DIR as _STAC_DIR
    HAS_STAC = True
    # Override STAC_DIR if available from catalog module
    STAC_DIR = _STAC_DIR
except ImportError:
    HAS_STAC = False
    get_collection = None
    get_item = None
    get_catalog = None
    build_catalog = None


# Variable metadata for point queries and subset downloads
# Includes CF-compliant attributes for NetCDF export
VARIABLE_METADATA = {
    "sst": {
        "name": "Sea Surface Temperature",
        "unit": "°C",
        "source": "Copernicus Marine Service",
        "dataset": "L4 Gap-filled OSTIA",
        "scale": 0.01,  # int16 to Celsius
        "dtype_check": "int16",
        # CF-compliant NetCDF attributes
        "cf_standard_name": "sea_surface_temperature",
        "cf_long_name": "Sea Surface Temperature",
        "cf_units": "degrees_Celsius",
        "csv_column": "sst_celsius",
    },
    "sic": {
        "name": "Sea Ice Concentration",
        "unit": "%",
        "source": "EUMETSAT OSI SAF / Copernicus Marine",
        "dataset": "Arctic + Antarctic merged",
        "scale": 1.0,  # Already in % (0-100)
        "dtype_check": None,
        "cf_standard_name": "sea_ice_area_fraction",
        "cf_long_name": "Sea Ice Concentration",
        "cf_units": "percent",
        "csv_column": "sic_percent",
    },
    "sla": {
        "name": "Sea Level Anomaly",
        "unit": "m",
        "source": "Copernicus Marine Service",
        "dataset": "L4 Altimetry",
        "scale": 0.001,  # int16 (mm) to meters
        "dtype_check": "int16",
        "cf_standard_name": "sea_surface_height_above_sea_level",
        "cf_long_name": "Sea Level Anomaly",
        "cf_units": "m",
        "csv_column": "sla_meters",
    },
    "chl": {
        "name": "Chlorophyll-a Concentration",
        "unit": "mg/m³",
        "source": "Copernicus Marine Ocean Colour",
        "dataset": "L4 Gap-free 4km",
        "scale": 1.0,  # float32, no scaling
        "dtype_check": "float32",
        "cf_standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water",
        "cf_long_name": "Chlorophyll-a Concentration",
        "cf_units": "mg m-3",
        "csv_column": "chl_mg_m3",
    },
    "kd490": {
        "name": "Diffuse Attenuation Coefficient",
        "unit": "m⁻¹",
        "source": "Copernicus Marine Ocean Colour",
        "dataset": "L4 Gap-free 4km",
        "scale": 1.0,  # float32, no scaling
        "dtype_check": "float32",
        "cf_standard_name": "volume_attenuation_coefficient_of_downwelling_radiative_flux_in_sea_water",
        "cf_long_name": "Diffuse Attenuation Coefficient at 490nm",
        "cf_units": "m-1",
        "csv_column": "kd490_m_inv",
    },
}

# Metadata for COG products (used in catalog)
COG_PRODUCT_META = {
    "chl": {
        "name": "Chlorophyll-a Concentration",
        "description": "Copernicus Marine L4 gap-free 4km",
        "source": "Copernicus Marine Service",
    },
    "kd490": {
        "name": "Diffuse Attenuation (Kd490)",
        "description": "Copernicus Marine L4 gap-free 4km",
        "source": "Copernicus Marine Service",
    },
    "rrs": {
        "name": "Ocean Colour RGB",
        "description": "Rrs 670/555/443nm false-color composite",
        "source": "Copernicus Marine Service",
    },
    "sic": {
        "name": "Sea Ice Concentration",
        "description": "OSI SAF daily polar sea ice",
        "source": "EUMETSAT OSI SAF",
    },
    "sla": {
        "name": "Sea Level Anomaly",
        "description": "Copernicus Marine L4 gridded",
        "source": "Copernicus Marine Service",
    },
}
