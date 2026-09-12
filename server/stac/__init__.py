"""
STAC (SpatioTemporal Asset Catalog) module for Ocean ECV data.

Provides standards-compliant metadata for all COG and Zarr products, enabling:
- Fast time-range queries via collection temporal extents
- Interoperability with STAC tools (stac-browser, pystac, etc.)
- Self-describing data with asset links, spatial bounds, and metadata
- ARCO (Analysis-Ready Cloud-Optimized) Zarr store discovery
"""

from .catalog import (
    StacCatalog,
    build_catalog,
    get_collection,
    get_item,
    update_collection_from_filesystem,
    update_zarr_collection,
)

__all__ = [
    "StacCatalog",
    "build_catalog",
    "get_collection",
    "get_item",
    "update_collection_from_filesystem",
    "update_zarr_collection",
]
