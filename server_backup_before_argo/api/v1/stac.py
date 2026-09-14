"""
STAC catalog endpoints for OGC-compliant metadata access.
"""

import json

from fastapi import APIRouter, HTTPException, Query

from server.api.dependencies import STAC_DIR, HAS_STAC, logger

# Optional STAC helpers
try:
    from server.stac.catalog import get_collection, get_item, build_catalog
except ImportError:
    get_collection = None
    get_item = None
    build_catalog = None

router = APIRouter(prefix="/api/stac", tags=["stac"])


@router.get("")
async def get_stac_root():
    """
    Get root STAC catalog.
    
    Returns the landing page of the STAC catalog with links to collections.
    """
    catalog_path = STAC_DIR / "catalog.json"
    if not catalog_path.exists():
        return {
            "type": "Catalog",
            "stac_version": "1.0.0",
            "id": "ocean-ecv",
            "title": "Ocean Essential Climate Variables",
            "description": "STAC catalog not yet built. Run: python -m server.stac.catalog",
            "links": [],
        }
    
    with open(catalog_path) as f:
        return json.load(f)


@router.get("/collections")
async def list_stac_collections():
    """
    List all STAC collections.
    
    Each collection represents one ocean ECV variable (SST, SIC, SLA, etc.)
    """
    collections_dir = STAC_DIR / "collections"
    if not collections_dir.exists():
        return {"collections": []}
    
    collections = []
    for path in sorted(collections_dir.glob("*.json")):
        with open(path) as f:
            collections.append(json.load(f))
    
    return {"collections": collections}


@router.get("/collections/{variable}")
async def get_stac_collection(variable: str):
    """
    Get STAC collection for a specific variable.
    
    Returns collection metadata including temporal extent, providers,
    and links to all items (dates).
    """
    if HAS_STAC and get_collection:
        collection = get_collection(variable)
        if collection:
            return collection
    
    # Fallback to file
    collection_path = STAC_DIR / "collections" / f"{variable}.json"
    if not collection_path.exists():
        raise HTTPException(404, f"Collection not found: {variable}")
    
    with open(collection_path) as f:
        return json.load(f)


@router.get("/collections/{variable}/items")
async def list_stac_items(
    variable: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List STAC items for a collection (paginated).
    
    Each item represents one date's data with links to COG assets.
    """
    items_dir = STAC_DIR / "items" / variable
    if not items_dir.exists():
        raise HTTPException(404, f"Collection not found: {variable}")
    
    all_items = sorted(items_dir.glob("*.json"))
    total = len(all_items)
    
    # Paginate
    page_items = all_items[offset:offset + limit]
    
    items = []
    for path in page_items:
        with open(path) as f:
            items.append(json.load(f))
    
    return {
        "type": "FeatureCollection",
        "features": items,
        "numberMatched": total,
        "numberReturned": len(items),
    }


@router.get("/collections/{variable}/items/{item_id}")
async def get_stac_item(variable: str, item_id: str):
    """
    Get a specific STAC item by ID.
    
    The item_id is typically the date (YYYY-MM-DD).
    """
    # Try to extract date from item_id (could be "sst-2024-01-15" or "2024-01-15")
    date = item_id.replace(f"{variable}-", "")
    
    if HAS_STAC and get_item:
        item = get_item(variable, date)
        if item:
            return item
    
    # Fallback to file
    item_path = STAC_DIR / "items" / variable / f"{date}.json"
    if not item_path.exists():
        raise HTTPException(404, f"Item not found: {variable}/{item_id}")
    
    with open(item_path) as f:
        return json.load(f)


@router.post("/rebuild")
async def rebuild_stac_catalog():
    """
    Rebuild the STAC catalog from filesystem.
    
    Scans all COG directories and regenerates catalog, collections, and items.
    Useful after bulk data ingestion or if catalog gets out of sync.
    """
    if not HAS_STAC or not build_catalog:
        raise HTTPException(500, "STAC module not available")
    
    try:
        build_catalog()
        
        # Return summary
        collections_dir = STAC_DIR / "collections"
        collections = list(collections_dir.glob("*.json")) if collections_dir.exists() else []
        
        return {
            "status": "rebuilt",
            "collections": len(collections),
            "message": "STAC catalog rebuilt from filesystem",
        }
    except Exception as e:
        raise HTTPException(500, f"Rebuild failed: {str(e)}")
