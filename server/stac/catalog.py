"""
STAC Catalog builder for Ocean ECV COG and Zarr products.

Creates and maintains a static STAC catalog that describes all available
COG files and Zarr stores with proper metadata. The catalog is updated 
after each pipeline ingest operation.

STAC Structure:
    server/stac/
        catalog.json                         # Root catalog
        collections/{variable}.json          # COG collections (daily data)
        collections/zarr-{variable}.json     # Zarr collections (ARCO analytics)
        items/{variable}/{date}.json         # COG items per date
        items/zarr-{variable}/analytics.json # Zarr analytics item

Usage:
    # Rebuild entire catalog from filesystem
    from server.stac import build_catalog
    build_catalog()
    
    # Update single COG collection (fast, after pipeline ingest)
    from server.stac import update_collection_from_filesystem
    update_collection_from_filesystem("sst")
    
    # Update Zarr collection (after Zarr build)
    from server.stac import update_zarr_collection
    update_zarr_collection("sst")
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rasterio

logger = logging.getLogger(__name__)

# STAC version
STAC_VERSION = "1.0.0"

# Base directory for STAC files
STAC_DIR = Path(__file__).parent
PRODUCTS_DIR = Path(__file__).parent.parent / "products"
ZARR_DIR = Path(__file__).parent.parent / "zarr"

# Variable metadata (from datasets.json)
VARIABLE_METADATA = {
    "sst": {
        "title": "Sea Surface Temperature",
        "description": "OSTIA L4 gap-free daily SST from Copernicus Marine Service",
        "units": "°C",
        "license": "Copernicus Marine EULA",
        "providers": [
            {
                "name": "Copernicus Marine Service",
                "roles": ["producer", "licensor"],
                "url": "https://marine.copernicus.eu/",
            }
        ],
    },
    "sic": {
        "title": "Sea Ice Concentration",
        "description": "OSI SAF daily polar sea ice concentration (Arctic + Antarctic)",
        "units": "%",
        "license": "Copernicus Marine EULA",
        "providers": [
            {
                "name": "EUMETSAT OSI SAF",
                "roles": ["producer"],
                "url": "https://osi-saf.eumetsat.int/",
            },
            {
                "name": "Copernicus Marine Service",
                "roles": ["host", "licensor"],
                "url": "https://marine.copernicus.eu/",
            },
        ],
    },
    "sla": {
        "title": "Sea Level Anomaly",
        "description": "L4 gridded sea level anomaly from satellite altimetry",
        "units": "m",
        "license": "Copernicus Marine EULA",
        "providers": [
            {
                "name": "Copernicus Marine Service",
                "roles": ["producer", "licensor"],
                "url": "https://marine.copernicus.eu/",
            }
        ],
    },
    "chl": {
        "title": "Chlorophyll-a Concentration",
        "description": "L4 gap-free chlorophyll-a from ocean colour observations",
        "units": "mg/m³",
        "license": "Copernicus Marine EULA",
        "providers": [
            {
                "name": "Copernicus Marine Service",
                "roles": ["producer", "licensor"],
                "url": "https://marine.copernicus.eu/",
            }
        ],
    },
    "kd490": {
        "title": "Diffuse Attenuation Coefficient (Kd490)",
        "description": "L4 gap-free light attenuation at 490nm",
        "units": "m⁻¹",
        "license": "Copernicus Marine EULA",
        "providers": [
            {
                "name": "Copernicus Marine Service",
                "roles": ["producer", "licensor"],
                "url": "https://marine.copernicus.eu/",
            }
        ],
    },
    "rrs": {
        "title": "Ocean Colour RGB",
        "description": "Remote sensing reflectance RGB composite (Rrs 670/555/443nm)",
        "units": "sr⁻¹",
        "license": "Copernicus Marine EULA",
        "providers": [
            {
                "name": "Copernicus Marine Service",
                "roles": ["producer", "licensor"],
                "url": "https://marine.copernicus.eu/",
            }
        ],
    },
}


class StacCatalog:
    """In-memory STAC catalog for fast queries."""

    def __init__(self):
        self._collections: dict[str, dict] = {}
        self._items: dict[str, list[str]] = {}  # variable -> sorted date list
        self._loaded = False

    def load(self) -> None:
        """Load catalog from disk."""
        if self._loaded:
            return

        for var in VARIABLE_METADATA:
            collection_path = STAC_DIR / "collections" / f"{var}.json"
            if collection_path.exists():
                with open(collection_path) as f:
                    self._collections[var] = json.load(f)
                # Extract dates from collection's item links
                dates = []
                for link in self._collections[var].get("links", []):
                    if link.get("rel") == "item":
                        # Extract date from href like "../items/sst/2024-01-15.json"
                        date = Path(link["href"]).stem
                        dates.append(date)
                self._items[var] = sorted(dates)
        
        self._loaded = True

    def get_available_dates(self, variable: str) -> list[str]:
        """Get sorted list of available dates for a variable."""
        self.load()
        return self._items.get(variable, [])

    def get_temporal_extent(self, variable: str) -> tuple[str | None, str | None]:
        """Get (start_date, end_date) for a variable."""
        dates = self.get_available_dates(variable)
        if not dates:
            return None, None
        return dates[0], dates[-1]

    def get_collection(self, variable: str) -> dict | None:
        """Get full collection metadata."""
        self.load()
        return self._collections.get(variable)

    def reload(self) -> None:
        """Force reload from disk."""
        self._loaded = False
        self._collections.clear()
        self._items.clear()
        self.load()


# Singleton instance for fast queries
_catalog = StacCatalog()


def get_catalog() -> StacCatalog:
    """Get the singleton catalog instance."""
    return _catalog


def get_collection(variable: str) -> dict | None:
    """Get STAC collection for a variable."""
    return _catalog.get_collection(variable)


def get_item(variable: str, date: str) -> dict | None:
    """Get STAC item for a specific date."""
    item_path = STAC_DIR / "items" / variable / f"{date}.json"
    if not item_path.exists():
        return None
    with open(item_path) as f:
        return json.load(f)


def _get_cog_metadata(cog_path: Path) -> dict[str, Any]:
    """Extract metadata from a COG file."""
    with rasterio.open(cog_path) as ds:
        bounds = ds.bounds
        return {
            "bbox": [bounds.left, bounds.bottom, bounds.right, bounds.top],
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [bounds.left, bounds.bottom],
                    [bounds.right, bounds.bottom],
                    [bounds.right, bounds.top],
                    [bounds.left, bounds.top],
                    [bounds.left, bounds.bottom],
                ]],
            },
            "proj:epsg": ds.crs.to_epsg() if ds.crs else 4326,
            "proj:shape": [ds.height, ds.width],
            "proj:transform": list(ds.transform)[:6],
        }


def _create_item(variable: str, date: str, cog_path: Path) -> dict:
    """Create a STAC item for a COG file."""
    meta = _get_cog_metadata(cog_path)
    var_meta = VARIABLE_METADATA.get(variable, {})
    
    # Parse date for datetime
    dt = datetime.strptime(date, "%Y-%m-%d")
    dt_str = dt.replace(tzinfo=timezone.utc).isoformat()
    
    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "stac_extensions": [
            "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
        ],
        "id": f"{variable}-{date}",
        "geometry": meta["geometry"],
        "bbox": meta["bbox"],
        "properties": {
            "datetime": dt_str,
            "title": f"{var_meta.get('title', variable.upper())} - {date}",
            "description": f"{variable.upper()} data for {date}",
            "proj:epsg": meta["proj:epsg"],
            "proj:shape": meta["proj:shape"],
            "proj:transform": meta["proj:transform"],
        },
        "links": [
            {
                "rel": "collection",
                "href": f"../../collections/{variable}.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"../../collections/{variable}.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": "../../catalog.json",
                "type": "application/json",
            },
        ],
        "assets": {
            "data": {
                "href": f"../../products/{variable}/{date}.tif",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "title": f"{variable.upper()} COG",
                "roles": ["data"],
            },
            "tile": {
                "href": f"/api/tiles/{variable}/{date}/{{z}}/{{x}}/{{y}}.png",
                "type": "image/png",
                "title": "XYZ Tile Endpoint",
                "roles": ["visual"],
            },
        },
    }


def _create_collection(variable: str, dates: list[str], sample_cog: Path | None = None) -> dict:
    """Create a STAC collection for a variable."""
    var_meta = VARIABLE_METADATA.get(variable, {})
    
    # Get spatial extent from sample COG or use global
    if sample_cog and sample_cog.exists():
        meta = _get_cog_metadata(sample_cog)
        bbox = meta["bbox"]
    else:
        bbox = [-180, -90, 180, 90]
    
    # Temporal extent
    if dates:
        start_dt = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(dates[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        temporal = [[start_dt.isoformat(), end_dt.isoformat()]]
    else:
        temporal = [[None, None]]
    
    collection = {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [],
        "id": variable,
        "title": var_meta.get("title", variable.upper()),
        "description": var_meta.get("description", f"{variable.upper()} data"),
        "license": var_meta.get("license", "proprietary"),
        "providers": var_meta.get("providers", []),
        "extent": {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": temporal},
        },
        "summaries": {
            "datetime": {
                "minimum": dates[0] if dates else None,
                "maximum": dates[-1] if dates else None,
            },
        },
        "links": [
            {
                "rel": "self",
                "href": f"./collections/{variable}.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": "../catalog.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": "../catalog.json",
                "type": "application/json",
            },
        ],
    }
    
    # Add item links
    for date in dates:
        collection["links"].append({
            "rel": "item",
            "href": f"../items/{variable}/{date}.json",
            "type": "application/json",
            "title": date,
        })
    
    return collection


def _create_root_catalog(variables: list[str], zarr_variables: list[str] | None = None) -> dict:
    """Create the root STAC catalog."""
    links = [
        {
            "rel": "self",
            "href": "./catalog.json",
            "type": "application/json",
        },
        {
            "rel": "root",
            "href": "./catalog.json",
            "type": "application/json",
        },
    ]
    
    # Add COG collections
    for var in variables:
        links.append({
            "rel": "child",
            "href": f"./collections/{var}.json",
            "type": "application/json",
            "title": VARIABLE_METADATA.get(var, {}).get("title", var.upper()),
        })
    
    # Add Zarr/ARCO collections
    if zarr_variables:
        for var in zarr_variables:
            links.append({
                "rel": "child",
                "href": f"./collections/zarr-{var}.json",
                "type": "application/json",
                "title": f"{VARIABLE_METADATA.get(var, {}).get('title', var.upper())} (ARCO)",
            })
    
    return {
        "type": "Catalog",
        "stac_version": STAC_VERSION,
        "id": "ocean-ecv",
        "title": "Ocean Essential Climate Variables",
        "description": "STAC catalog for Copernicus Marine ECV data. Includes daily COG products and ARCO Zarr analytics stores with climatology, trends, and percentiles.",
        "links": links,
    }


# =============================================================================
# Zarr/ARCO STAC Functions
# =============================================================================

def _get_zarr_metadata(zarr_path: Path) -> dict[str, Any]:
    """Extract metadata from a Zarr store."""
    import zarr
    
    root = zarr.open_group(str(zarr_path), mode='r')
    attrs = dict(root.attrs)
    
    # Get coordinate bounds
    lat = root["lat"][:]
    lon = root["lon"][:]
    time_arr = root["time"][:]
    dates = attrs.get("dates", [])
    
    # Get available arrays (excluding coordinates)
    arrays = {}
    coord_names = {"lat", "lon", "time"}
    for name in root.keys():
        if name not in coord_names:
            arr = root[name]
            arrays[name] = {
                "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "chunks": list(arr.chunks) if hasattr(arr, 'chunks') else None,
            }
    
    # Calculate total size
    total_size = 0
    for name in root.array_keys():
        arr = root[name]
        nbytes = getattr(arr, 'nbytes_stored', None)
        if callable(nbytes):
            total_size += nbytes()
        elif nbytes is not None:
            total_size += nbytes
        elif hasattr(arr, 'nbytes'):
            total_size += arr.nbytes
    
    return {
        "bbox": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [float(lon.min()), float(lat.min())],
                [float(lon.max()), float(lat.min())],
                [float(lon.max()), float(lat.max())],
                [float(lon.min()), float(lat.max())],
                [float(lon.min()), float(lat.min())],
            ]],
        },
        "proj:epsg": 4326,
        "proj:shape": [len(lat), len(lon)],
        "n_timesteps": len(time_arr),
        "dates": dates,
        "arrays": arrays,
        "global_stats": attrs.get("global_stats", {}),
        "size_bytes": total_size,
        "created": attrs.get("created"),
    }


def _create_zarr_item(variable: str, zarr_path: Path) -> dict:
    """Create a STAC item for a Zarr store."""
    meta = _get_zarr_metadata(zarr_path)
    var_meta = VARIABLE_METADATA.get(variable, {})
    
    # Use first and last date for temporal extent
    dates = meta.get("dates", [])
    if dates:
        start_dt = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(dates[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        temporal = f"{start_dt.isoformat()}/{end_dt.isoformat()}"
    else:
        temporal = None
    
    # List of analytics arrays available
    analytics_arrays = list(meta.get("arrays", {}).keys())
    
    return {
        "type": "Feature",
        "stac_version": STAC_VERSION,
        "stac_extensions": [
            "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
            "https://stac-extensions.github.io/datacube/v2.2.0/schema.json",
        ],
        "id": f"zarr-{variable}-analytics",
        "geometry": meta["geometry"],
        "bbox": meta["bbox"],
        "properties": {
            "datetime": None,  # Use start/end instead
            "start_datetime": dates[0] + "T00:00:00Z" if dates else None,
            "end_datetime": dates[-1] + "T00:00:00Z" if dates else None,
            "title": f"{var_meta.get('title', variable.upper())} ARCO Analytics",
            "description": f"Analysis-Ready Cloud-Optimized (ARCO) Zarr store with climatology, trends, and percentiles for {variable.upper()}",
            "proj:epsg": meta["proj:epsg"],
            "proj:shape": meta["proj:shape"],
            "cube:dimensions": {
                "time": {
                    "type": "temporal",
                    "extent": [dates[0] if dates else None, dates[-1] if dates else None],
                    "values": dates,
                },
                "lat": {
                    "type": "spatial",
                    "axis": "y",
                    "extent": [meta["bbox"][1], meta["bbox"][3]],
                    "reference_system": 4326,
                },
                "lon": {
                    "type": "spatial",
                    "axis": "x",
                    "extent": [meta["bbox"][0], meta["bbox"][2]],
                    "reference_system": 4326,
                },
            },
            "cube:variables": {
                name: {
                    "dimensions": ["time", "lat", "lon"] if info["shape"] and len(info["shape"]) == 3 else ["lat", "lon"],
                    "type": "data",
                }
                for name, info in meta.get("arrays", {}).items()
            },
            "arco:n_timesteps": meta["n_timesteps"],
            "arco:analytics_arrays": analytics_arrays,
            "arco:global_stats": meta.get("global_stats", {}),
            "arco:size_bytes": meta.get("size_bytes", 0),
        },
        "links": [
            {
                "rel": "collection",
                "href": f"../../collections/zarr-{variable}.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": f"../../collections/zarr-{variable}.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": "../../catalog.json",
                "type": "application/json",
            },
        ],
        "assets": {
            "zarr": {
                "href": f"../../zarr/{variable}.zarr",
                "type": "application/vnd+zarr",
                "title": f"{variable.upper()} Zarr Store",
                "roles": ["data", "zarr"],
                "xarray:open_kwargs": {
                    "engine": "zarr",
                    "consolidated": False,
                },
            },
            "info": {
                "href": f"/api/zarr/{variable}/info",
                "type": "application/json",
                "title": "Zarr Info API",
                "roles": ["metadata"],
            },
            "timeseries": {
                "href": f"/api/zarr/{variable}/timeseries?lon={{lon}}&lat={{lat}}",
                "type": "application/json",
                "title": "Timeseries API",
                "roles": ["data"],
            },
            "stats": {
                "href": f"/api/zarr/{variable}/stats?lon_min={{west}}&lon_max={{east}}&lat_min={{south}}&lat_max={{north}}",
                "type": "application/json",
                "title": "Regional Stats API",
                "roles": ["data"],
            },
        },
    }


def _create_zarr_collection(variable: str, zarr_path: Path) -> dict:
    """Create a STAC collection for a Zarr store."""
    var_meta = VARIABLE_METADATA.get(variable, {})
    meta = _get_zarr_metadata(zarr_path)
    
    dates = meta.get("dates", [])
    
    # Temporal extent
    if dates:
        start_dt = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(dates[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        temporal = [[start_dt.isoformat(), end_dt.isoformat()]]
    else:
        temporal = [[None, None]]
    
    return {
        "type": "Collection",
        "stac_version": STAC_VERSION,
        "stac_extensions": [
            "https://stac-extensions.github.io/datacube/v2.2.0/schema.json",
        ],
        "id": f"zarr-{variable}",
        "title": f"{var_meta.get('title', variable.upper())} (ARCO)",
        "description": f"Analysis-Ready Cloud-Optimized (ARCO) Zarr store for {variable.upper()}. Contains time-indexed data, climatology (overall and monthly), percentiles (P10/P50/P90), and linear trends per pixel.",
        "license": var_meta.get("license", "proprietary"),
        "providers": var_meta.get("providers", []) + [
            {
                "name": "Ocean ECV Platform",
                "roles": ["processor", "host"],
                "description": "ARCO analytics computed from daily COG products",
            }
        ],
        "extent": {
            "spatial": {"bbox": [meta["bbox"]]},
            "temporal": {"interval": temporal},
        },
        "summaries": {
            "arco:analytics_arrays": list(meta.get("arrays", {}).keys()),
            "arco:n_timesteps": meta["n_timesteps"],
        },
        "links": [
            {
                "rel": "self",
                "href": f"./collections/zarr-{variable}.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": "../catalog.json",
                "type": "application/json",
            },
            {
                "rel": "parent",
                "href": "../catalog.json",
                "type": "application/json",
            },
            {
                "rel": "item",
                "href": f"../items/zarr-{variable}/analytics.json",
                "type": "application/json",
                "title": "Analytics Store",
            },
        ],
    }


def update_zarr_collection(variable: str) -> dict:
    """
    Update STAC collection for a Zarr store.
    
    Called after Zarr build to update the catalog. Fast operation.
    
    Returns the updated collection.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if not zarr_path.exists():
        logger.warning(f"Zarr store not found: {zarr_path}")
        return {}
    
    # Create items directory
    items_dir = STAC_DIR / "items" / f"zarr-{variable}"
    items_dir.mkdir(parents=True, exist_ok=True)
    
    # Create item
    item = _create_zarr_item(variable, zarr_path)
    with open(items_dir / "analytics.json", "w") as f:
        json.dump(item, f, indent=2)
    
    # Create collection
    collection = _create_zarr_collection(variable, zarr_path)
    
    collections_dir = STAC_DIR / "collections"
    collections_dir.mkdir(parents=True, exist_ok=True)
    
    with open(collections_dir / f"zarr-{variable}.json", "w") as f:
        json.dump(collection, f, indent=2)
    
    # Update root catalog to include this Zarr collection if not already present
    _update_root_catalog_with_zarr(variable)
    
    logger.info(f"Updated STAC collection for zarr-{variable}")
    
    # Reload in-memory catalog
    _catalog.reload()
    
    return collection


def _update_root_catalog_with_zarr(variable: str) -> None:
    """Add Zarr collection to root catalog if not already present."""
    catalog_path = STAC_DIR / "catalog.json"
    if not catalog_path.exists():
        return
    
    with open(catalog_path) as f:
        catalog = json.load(f)
    
    # Check if already present
    zarr_href = f"./collections/zarr-{variable}.json"
    for link in catalog.get("links", []):
        if link.get("href") == zarr_href:
            return  # Already present
    
    # Add new link
    catalog["links"].append({
        "rel": "child",
        "href": zarr_href,
        "type": "application/json",
        "title": f"{VARIABLE_METADATA.get(variable, {}).get('title', variable.upper())} (ARCO)",
    })
    
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)


def update_collection_from_filesystem(variable: str) -> dict:
    """
    Update a single collection from filesystem.
    
    Called after pipeline ingest to update the catalog. Fast operation
    that only scans one variable's directory.
    
    Returns the updated collection.
    """
    var_dir = PRODUCTS_DIR / variable
    if not var_dir.exists():
        logger.warning(f"Products directory not found: {var_dir}")
        return {}
    
    # Scan for COG files
    cog_files = sorted(var_dir.glob("*.tif"))
    dates = [f.stem for f in cog_files]
    
    if not dates:
        logger.warning(f"No COG files found in {var_dir}")
        return {}
    
    # Create items directory
    items_dir = STAC_DIR / "items" / variable
    items_dir.mkdir(parents=True, exist_ok=True)
    
    # Create/update items
    for cog in cog_files:
        date = cog.stem
        item = _create_item(variable, date, cog)
        item_path = items_dir / f"{date}.json"
        with open(item_path, "w") as f:
            json.dump(item, f, indent=2)
    
    # Create/update collection
    sample_cog = cog_files[0] if cog_files else None
    collection = _create_collection(variable, dates, sample_cog)
    
    collections_dir = STAC_DIR / "collections"
    collections_dir.mkdir(parents=True, exist_ok=True)
    
    with open(collections_dir / f"{variable}.json", "w") as f:
        json.dump(collection, f, indent=2)
    
    logger.info(f"Updated STAC collection for {variable}: {len(dates)} items")
    
    # Reload in-memory catalog
    _catalog.reload()
    
    return collection


def build_catalog() -> None:
    """
    Build complete STAC catalog from filesystem.
    
    Scans all variable directories and creates:
    - catalog.json (root)
    - collections/{variable}.json for each COG variable
    - collections/zarr-{variable}.json for each Zarr store
    - items/{variable}/{date}.json for each COG
    - items/zarr-{variable}/analytics.json for each Zarr
    """
    logger.info("Building STAC catalog from filesystem...")
    
    # Ensure directories exist
    (STAC_DIR / "collections").mkdir(parents=True, exist_ok=True)
    (STAC_DIR / "items").mkdir(parents=True, exist_ok=True)
    
    variables_with_data = []
    zarr_variables = []
    
    # Process COG products for each variable
    for variable in VARIABLE_METADATA:
        var_dir = PRODUCTS_DIR / variable
        if not var_dir.exists():
            logger.debug(f"Skipping {variable}: directory not found")
            continue
        
        cog_files = sorted(var_dir.glob("*.tif"))
        if not cog_files:
            logger.debug(f"Skipping {variable}: no COG files")
            continue
        
        variables_with_data.append(variable)
        
        # Create items
        items_dir = STAC_DIR / "items" / variable
        items_dir.mkdir(parents=True, exist_ok=True)
        
        dates = []
        for cog in cog_files:
            date = cog.stem
            dates.append(date)
            item = _create_item(variable, date, cog)
            with open(items_dir / f"{date}.json", "w") as f:
                json.dump(item, f, indent=2)
        
        # Create collection
        collection = _create_collection(variable, dates, cog_files[0])
        with open(STAC_DIR / "collections" / f"{variable}.json", "w") as f:
            json.dump(collection, f, indent=2)
        
        logger.info(f"  {variable}: {len(dates)} items")
    
    # Process Zarr stores
    if ZARR_DIR.exists():
        for zarr_path in sorted(ZARR_DIR.glob("*.zarr")):
            variable = zarr_path.stem
            
            try:
                # Create items directory
                items_dir = STAC_DIR / "items" / f"zarr-{variable}"
                items_dir.mkdir(parents=True, exist_ok=True)
                
                # Create item
                item = _create_zarr_item(variable, zarr_path)
                with open(items_dir / "analytics.json", "w") as f:
                    json.dump(item, f, indent=2)
                
                # Create collection
                collection = _create_zarr_collection(variable, zarr_path)
                with open(STAC_DIR / "collections" / f"zarr-{variable}.json", "w") as f:
                    json.dump(collection, f, indent=2)
                
                zarr_variables.append(variable)
                
                # Get timestep count for logging
                import zarr
                root = zarr.open_group(str(zarr_path), mode='r')
                n_times = len(root.attrs.get('dates', []))
                logger.info(f"  zarr-{variable}: {n_times} timesteps, analytics store")
                
            except Exception as e:
                logger.warning(f"Failed to process Zarr {variable}: {e}")
    
    # Create root catalog (includes both COG and Zarr collections)
    root_catalog = _create_root_catalog(variables_with_data, zarr_variables)
    with open(STAC_DIR / "catalog.json", "w") as f:
        json.dump(root_catalog, f, indent=2)
    
    total_collections = len(variables_with_data) + len(zarr_variables)
    logger.info(f"STAC catalog built: {len(variables_with_data)} COG + {len(zarr_variables)} Zarr = {total_collections} collections")
    
    # Reload in-memory catalog
    _catalog.reload()


def build_catalog_from_azure(
    storage_account: str,
    products_container: str,
    sas_token: str | None = None,
) -> dict[str, list[dict]]:
    """
    Build STAC catalog from Azure blob storage listing.
    
    Creates a minimal STAC catalog (collections only, no per-file items)
    by scanning the products container in Azure.
    
    Args:
        storage_account: Azure storage account name
        products_container: Container name for COG products
        sas_token: SAS token for authentication
        
    Returns:
        Dict with catalog.json and collections as JSON dicts (ready to upload)
    """
    try:
        from azure.storage.blob import ContainerClient
    except ImportError:
        raise ImportError("azure-storage-blob required: pip install azure-storage-blob")
    
    logger.info(f"Building STAC catalog from Azure: {storage_account}/{products_container}")
    
    account_url = f"https://{storage_account}.blob.core.windows.net"
    
    if sas_token:
        container_url = f"{account_url}/{products_container}?{sas_token.lstrip('?')}"
        container = ContainerClient.from_container_url(container_url)
    else:
        container = ContainerClient(account_url, products_container)
    
    # Group blobs by variable
    variable_data: dict[str, dict] = {}
    
    for blob in container.list_blobs():
        parts = blob.name.split("/")
        if len(parts) >= 2 and parts[-1].endswith(".tif"):
            variable = parts[0]
            date = parts[-1].replace(".tif", "")
            
            if variable not in variable_data:
                variable_data[variable] = {
                    "dates": [],
                    "size_bytes": 0,
                }
            
            variable_data[variable]["dates"].append(date)
            variable_data[variable]["size_bytes"] += blob.size or 0
    
    # Sort dates
    for var in variable_data:
        variable_data[var]["dates"].sort()
    
    # Build collections
    collections = {}
    for variable, data in sorted(variable_data.items()):
        dates = data["dates"]
        var_meta = VARIABLE_METADATA.get(variable, {})
        
        # Temporal extent
        if dates:
            start_dt = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(dates[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            temporal = [[start_dt.isoformat(), end_dt.isoformat()]]
        else:
            temporal = [[None, None]]
        
        collection = {
            "type": "Collection",
            "stac_version": STAC_VERSION,
            "stac_extensions": [],
            "id": variable,
            "title": var_meta.get("title", variable.upper()),
            "description": var_meta.get("description", f"{variable.upper()} data from Copernicus Marine Service"),
            "license": var_meta.get("license", "Copernicus Marine EULA"),
            "providers": var_meta.get("providers", [
                {
                    "name": "Copernicus Marine Service",
                    "roles": ["producer", "licensor"],
                    "url": "https://marine.copernicus.eu/",
                }
            ]),
            "extent": {
                "spatial": {"bbox": [[-180, -90, 180, 90]]},
                "temporal": {"interval": temporal},
            },
            "summaries": {
                "datetime": {
                    "minimum": dates[0] if dates else None,
                    "maximum": dates[-1] if dates else None,
                },
                "n_timesteps": len(dates),
            },
            "links": [
                {
                    "rel": "self",
                    "href": f"./collections/{variable}.json",
                    "type": "application/json",
                },
                {
                    "rel": "root",
                    "href": "../catalog.json",
                    "type": "application/json",
                },
                {
                    "rel": "parent",
                    "href": "../catalog.json",
                    "type": "application/json",
                },
            ],
            # Add item link template (for XYZ tile access)
            "assets": {
                "tiles": {
                    "href": f"/api/tiles/{variable}/{{date}}/{{z}}/{{x}}/{{y}}.png",
                    "type": "image/png",
                    "title": "XYZ Tile Endpoint",
                    "roles": ["visual"],
                    "templated": True,
                },
            },
        }
        
        collections[variable] = collection
        logger.info(f"  {variable}: {len(dates)} dates")
    
    # Build root catalog
    root_catalog = {
        "type": "Catalog",
        "stac_version": STAC_VERSION,
        "id": "ocean-ecv",
        "title": "Ocean Essential Climate Variables",
        "description": "STAC catalog for Copernicus Marine ECV data stored in Azure Blob Storage. Includes daily COG products for SST, SIC, SLA, CHL, Kd490, and RRS.",
        "links": [
            {
                "rel": "self",
                "href": "./catalog.json",
                "type": "application/json",
            },
            {
                "rel": "root",
                "href": "./catalog.json",
                "type": "application/json",
            },
        ],
    }
    
    # Add child links for each collection
    for variable in sorted(collections.keys()):
        var_meta = VARIABLE_METADATA.get(variable, {})
        root_catalog["links"].append({
            "rel": "child",
            "href": f"./collections/{variable}.json",
            "type": "application/json",
            "title": var_meta.get("title", variable.upper()),
        })
    
    logger.info(f"Built STAC catalog: {len(collections)} collections")
    
    return {
        "catalog": root_catalog,
        "collections": collections,
    }


def upload_catalog_to_azure(
    catalog_data: dict,
    storage_account: str,
    stac_container: str,
    sas_token: str,
) -> dict[str, int]:
    """
    Upload STAC catalog to Azure Blob Storage.
    
    Args:
        catalog_data: Output from build_catalog_from_azure()
        storage_account: Azure storage account name
        stac_container: Container for STAC catalog
        sas_token: SAS token with write permissions
        
    Returns:
        Dict with upload stats
    """
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        raise ImportError("azure-storage-blob required: pip install azure-storage-blob")
    
    logger.info(f"Uploading STAC catalog to Azure: {storage_account}/{stac_container}")
    
    account_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service = BlobServiceClient(
        account_url=account_url,
        credential=sas_token,
    )
    
    container = blob_service.get_container_client(stac_container)
    
    # Create container if needed
    try:
        container.create_container()
        logger.info(f"Created container: {stac_container}")
    except Exception:
        pass  # Already exists
    
    uploaded = 0
    
    # Upload root catalog
    catalog_json = json.dumps(catalog_data["catalog"], indent=2)
    container.upload_blob("catalog.json", catalog_json, overwrite=True)
    uploaded += 1
    
    # Upload collections
    for variable, collection in catalog_data["collections"].items():
        collection_json = json.dumps(collection, indent=2)
        container.upload_blob(f"collections/{variable}.json", collection_json, overwrite=True)
        uploaded += 1
    
    logger.info(f"Uploaded {uploaded} STAC files to Azure")
    
    return {"uploaded": uploaded, "status": "success"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_catalog()
