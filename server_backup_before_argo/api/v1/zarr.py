"""
Zarr analytics endpoints for pre-computed metrics access.
"""

from pathlib import Path

import httpx
import numpy as np
from fastapi import APIRouter, HTTPException, Query
import zarr

from server.api.dependencies import ZARR_DIR, COG_PRODUCT_META, logger
from server.config import settings

router = APIRouter(prefix="/api/zarr", tags=["zarr"])


async def _fetch_stac_catalog() -> list[dict]:
    """
    Fetch datasets from remote STAC catalog.
    
    Reads the root catalog.json to find collections, then fetches
    each collection's metadata to build the datasets list.
    """
    stac_base_url = settings.get_stac_base_url()
    if not stac_base_url:
        return []
    
    # Parse base URL to separate path from query string (SAS token)
    from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
    
    parsed = urlparse(stac_base_url)
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    query_string = parsed.query  # SAS token
    
    def make_url(path: str) -> str:
        """Construct URL with query string (SAS token)."""
        full_path = f"{base_path.rstrip('/')}/{path.lstrip('/')}"
        if query_string:
            return f"{full_path}?{query_string}"
        return full_path
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch root catalog
            catalog_url = make_url("catalog.json")
            logger.debug(f"Fetching STAC catalog from {catalog_url[:80]}...")
            
            resp = await client.get(catalog_url)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch STAC catalog: {resp.status_code}")
                return []
            
            catalog = resp.json()
            
            # Find child collection links
            datasets = []
            collection_links = [
                link for link in catalog.get("links", [])
                if link.get("rel") == "child"
            ]
            
            for link in collection_links:
                href = link.get("href", "")
                # Resolve relative path to just the file path
                if href.startswith("./"):
                    rel_path = href[2:]
                elif href.startswith("../"):
                    rel_path = href.replace("../", "")
                elif href.startswith("http"):
                    # Absolute URL - use directly (add SAS if same host)
                    if query_string and parsed.netloc in href and "?" not in href:
                        collection_url = f"{href}?{query_string}"
                    else:
                        collection_url = href
                    rel_path = None
                else:
                    rel_path = href
                
                if rel_path:
                    collection_url = make_url(rel_path)
                
                try:
                    coll_resp = await client.get(collection_url)
                    if coll_resp.status_code != 200:
                        logger.debug(f"Skipping collection {href}: {coll_resp.status_code}")
                        continue
                    
                    collection = coll_resp.json()
                    
                    # Determine if this is a Zarr (ARCO) or COG collection
                    coll_id = collection.get("id", "")
                    is_zarr = coll_id.startswith("zarr-")
                    
                    # Extract temporal extent
                    extent = collection.get("extent", {})
                    temporal = extent.get("temporal", {}).get("interval", [[None, None]])
                    time_range = {
                        "start": temporal[0][0].split("T")[0] if temporal[0][0] else None,
                        "end": temporal[0][1].split("T")[0] if temporal[0][1] else None,
                    }
                    
                    # Get n_timesteps from summaries (set during catalog build)
                    summaries = collection.get("summaries", {})
                    
                    if is_zarr:
                        n_timesteps = summaries.get("arco:n_timesteps", 0)
                        n_arrays = len(summaries.get("arco:analytics_arrays", []))
                    else:
                        # For COG collections, n_timesteps is stored in summaries
                        n_timesteps = summaries.get("n_timesteps", 0)
                        n_arrays = 1
                    
                    datasets.append({
                        "id": coll_id.replace("zarr-", "") if is_zarr else coll_id,
                        "name": collection.get("title", coll_id.upper()),
                        "description": collection.get("description", ""),
                        "format": "zarr" if is_zarr else "cog",
                        "n_arrays": n_arrays,
                        "n_timesteps": n_timesteps,
                        "size_bytes": summaries.get("arco:size_bytes", 0) if is_zarr else 0,
                        "time_range": time_range,
                    })
                    
                except Exception as e:
                    logger.debug(f"Error fetching collection {href}: {e}")
                    continue
            
            return datasets
            
    except Exception as e:
        logger.error(f"Error fetching STAC catalog: {e}")
        return []


def _list_azure_variables() -> list[dict]:
    """
    List variables from Azure blob storage by scanning blobs.
    
    Used as fallback when no STAC catalog is available.
    """
    try:
        from azure.storage.blob import ContainerClient
    except ImportError:
        logger.warning("azure-storage-blob not installed, cannot list Azure products")
        return []
    
    if not settings.azure_storage_account:
        return []
    
    try:
        account_url = f"https://{settings.azure_storage_account}.blob.core.windows.net"
        
        if settings.azure_storage_sas_token:
            container_url = f"{account_url}/{settings.azure_storage_container}?{settings.azure_storage_sas_token.lstrip('?')}"
            container = ContainerClient.from_container_url(container_url)
        else:
            container = ContainerClient(account_url, settings.azure_storage_container)
        
        # Group blobs by variable (first path segment)
        variable_data: dict[str, list[str]] = {}
        variable_sizes: dict[str, int] = {}
        
        for blob in container.list_blobs():
            parts = blob.name.split("/")
            if len(parts) >= 2 and parts[-1].endswith(".tif"):
                variable = parts[0]
                date = parts[-1].replace(".tif", "")
                
                if variable not in variable_data:
                    variable_data[variable] = []
                    variable_sizes[variable] = 0
                
                variable_data[variable].append(date)
                variable_sizes[variable] += blob.size or 0
        
        # Build dataset list
        datasets = []
        for variable, dates in sorted(variable_data.items()):
            dates = sorted(dates)
            meta = COG_PRODUCT_META.get(variable, {})
            
            datasets.append({
                "id": variable,
                "name": meta.get("name", variable.upper()),
                "description": meta.get("description", f"Copernicus Marine {variable.upper()}"),
                "format": "cog",
                "n_arrays": 1,
                "n_timesteps": len(dates),
                "size_bytes": variable_sizes[variable],
                "time_range": {
                    "start": dates[0] if dates else None,
                    "end": dates[-1] if dates else None,
                },
            })
        
        return datasets
    except Exception as e:
        logger.error(f"Error listing Azure products: {e}")
        return []


async def _fetch_stac_collection(variable: str) -> dict | None:
    """
    Fetch a single collection from the remote STAC catalog.
    
    Returns the collection dict or None if not found.
    """
    stac_base_url = settings.get_stac_base_url()
    if not stac_base_url:
        return None
    
    from urllib.parse import urlparse
    
    parsed = urlparse(stac_base_url)
    base_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    query_string = parsed.query
    
    def make_url(path: str) -> str:
        full_path = f"{base_path}/{path.lstrip('/')}"
        if query_string:
            return f"{full_path}?{query_string}"
        return full_path
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try fetching the collection directly
            collection_url = make_url(f"collections/{variable}.json")
            logger.debug(f"Fetching STAC collection: {collection_url[:80]}...")
            resp = await client.get(collection_url)
            if resp.status_code == 200:
                return resp.json()
            
            # Try zarr- prefix
            zarr_url = make_url(f"collections/zarr-{variable}.json")
            resp = await client.get(zarr_url)
            if resp.status_code == 200:
                return resp.json()
            
            return None
    except Exception as e:
        logger.error(f"Error fetching STAC collection {variable}: {e}")
        return None


async def _list_azure_cog_files(variable: str) -> list[dict]:
    """
    List COG files for a variable from Azure blob storage.
    
    Returns list of file info dicts with name, date, and size.
    """
    try:
        from azure.storage.blob import ContainerClient
    except ImportError:
        return []
    
    if not settings.azure_storage_account:
        return []
    
    try:
        account_url = f"https://{settings.azure_storage_account}.blob.core.windows.net"
        
        if settings.azure_storage_sas_token:
            container_url = f"{account_url}/{settings.azure_storage_container}?{settings.azure_storage_sas_token.lstrip('?')}"
            container = ContainerClient.from_container_url(container_url)
        else:
            container = ContainerClient(account_url, settings.azure_storage_container)
        
        files = []
        for blob in container.list_blobs(name_starts_with=f"{variable}/"):
            if blob.name.endswith(".tif"):
                date = blob.name.split("/")[-1].replace(".tif", "")
                files.append({
                    "name": blob.name,
                    "date": date,
                    "size": blob.size,
                })
        
        return sorted(files, key=lambda x: x["date"])
    except Exception as e:
        logger.error(f"Error listing Azure COG files for {variable}: {e}")
        return []


@router.get("/catalog")
async def get_zarr_catalog():
    """
    List all available datasets in the catalog.
    
    Returns datasets from:
    1. Remote STAC catalog (if SST_STAC_CATALOG_URL is set)
    2. Azure blob storage scan (if products_source=azure, as fallback)
    3. Local filesystem (if products_source=local)
    """
    datasets = []
    
    # Try fetching from STAC catalog first
    stac_base_url = settings.get_stac_base_url()
    if stac_base_url:
        stac_datasets = await _fetch_stac_catalog()
        if stac_datasets:
            return {"datasets": stac_datasets, "source": "stac"}
    
    # Fallback: scan local Zarr directories
    if ZARR_DIR.exists():
        for zarr_path in sorted(ZARR_DIR.glob("*.zarr")):
            variable = zarr_path.stem
            try:
                root = zarr.open_group(str(zarr_path), mode='r')
                attrs = dict(root.attrs)
                
                time_arr = root["time"][:]
                n_timesteps = len(time_arr)
                
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
                
                datasets.append({
                    "id": variable,
                    "name": attrs.get("title", variable.upper()),
                    "description": attrs.get("source", "Ocean ECV variable"),
                    "format": "zarr",
                    "n_arrays": len(list(root.keys())),
                    "n_timesteps": n_timesteps,
                    "size_bytes": total_size,
                    "time_range": {
                        "start": str(time_arr[0]) if n_timesteps > 0 else None,
                        "end": str(time_arr[-1]) if n_timesteps > 0 else None,
                    },
                })
            except Exception as e:
                datasets.append({
                    "id": variable,
                    "name": variable.upper(),
                    "description": f"Error reading: {str(e)}",
                    "format": "zarr",
                    "n_arrays": 0,
                    "n_timesteps": 0,
                    "size_bytes": 0,
                    "time_range": None,
                })
    
    zarr_ids = {ds["id"] for ds in datasets}
    
    # Check storage source for COG products
    if settings.products_source == "azure":
        azure_datasets = _list_azure_variables()
        for ds in azure_datasets:
            if ds["id"] not in zarr_ids:
                datasets.append(ds)
    else:
        products_dir = Path(__file__).parent.parent.parent / "products"
        
        if products_dir.exists():
            for product_path in sorted(products_dir.iterdir()):
                if not product_path.is_dir():
                    continue
                variable = product_path.name
                if variable in zarr_ids:
                    continue
                
                cog_files = sorted(product_path.glob("*.tif"))
                if not cog_files:
                    continue
                
                dates = []
                total_size = 0
                for f in cog_files:
                    total_size += f.stat().st_size
                    try:
                        dates.append(f.stem)
                    except:
                        pass
                
                meta = COG_PRODUCT_META.get(variable, {})
                datasets.append({
                    "id": variable,
                    "name": meta.get("name", variable.upper()),
                    "description": meta.get("description", "COG product"),
                    "format": "cog",
                    "n_arrays": 1,
                    "n_timesteps": len(cog_files),
                    "size_bytes": total_size,
                    "time_range": {
                        "start": dates[0] if dates else None,
                        "end": dates[-1] if dates else None,
                    },
                })
    
    return {"datasets": datasets, "source": "fallback"}


@router.get("/{variable}/info")
async def get_zarr_info(variable: str):
    """
    Get dataset metadata and pre-computed statistics.
    
    Returns dataset info including global stats, available metrics,
    and coordinate ranges. Works for both Zarr stores and COG datasets.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    
    # Try local Zarr store first
    if zarr_path.exists():
        try:
            root = zarr.open_group(str(zarr_path), mode='r')
            
            # Get metadata from attrs
            attrs = dict(root.attrs)
            global_stats = attrs.get("global_stats", {})
            
            # List available arrays
            arrays = {}
            for name in root.keys():
                arr = root[name]
                arrays[name] = {
                    "shape": list(arr.shape),
                    "dtype": str(arr.dtype),
                    "chunks": list(arr.chunks) if hasattr(arr, 'chunks') else None,
                }
                # Add array attrs
                if hasattr(arr, 'attrs'):
                    arrays[name]["attrs"] = dict(arr.attrs)
            
            # Get coordinate bounds if available
            lat_arr = root["lat"][:]
            lon_arr = root["lon"][:]
            time_arr = root["time"][:]
            
            return {
                "variable": variable,
                "title": attrs.get("title", f"{variable.upper()} Zarr Store"),
                "source": attrs.get("source", "Unknown"),
                "format": "zarr",
                "created": attrs.get("created", None),
                "global_stats": global_stats,
                "arrays": arrays,
                "bounds": {
                    "lat": [float(lat_arr.min()), float(lat_arr.max())],
                    "lon": [float(lon_arr.min()), float(lon_arr.max())],
                },
                "time_range": {
                    "start": str(time_arr[0]) if len(time_arr) > 0 else None,
                    "end": str(time_arr[-1]) if len(time_arr) > 0 else None,
                    "count": len(time_arr),
                },
            }
        except Exception as e:
            raise HTTPException(500, f"Error reading Zarr store: {str(e)}")
    
    # Fallback: try STAC catalog for COG datasets
    collection = await _fetch_stac_collection(variable)
    if collection:
        summaries = collection.get("summaries", {})
        extent = collection.get("extent", {})
        temporal = extent.get("temporal", {}).get("interval", [[None, None]])[0]
        spatial = extent.get("spatial", {}).get("bbox", [[-180, -90, 180, 90]])[0]
        
        meta = COG_PRODUCT_META.get(variable, {})
        
        return {
            "variable": variable,
            "title": collection.get("title", meta.get("name", variable.upper())),
            "source": "Copernicus Marine Service",
            "format": "cog",
            "created": None,
            "global_stats": {},
            "arrays": {
                variable: {
                    "shape": None,
                    "dtype": meta.get("dtype", "float32"),
                    "chunks": None,
                }
            },
            "bounds": {
                "lat": [spatial[1], spatial[3]] if len(spatial) >= 4 else [-90, 90],
                "lon": [spatial[0], spatial[2]] if len(spatial) >= 4 else [-180, 180],
            },
            "time_range": {
                "start": temporal[0] if temporal else None,
                "end": temporal[1] if len(temporal) > 1 else None,
                "count": summaries.get("n_timesteps", 0),
            },
        }
    
    raise HTTPException(404, f"Dataset not found: {variable}")


@router.get("/{variable}/files")
async def get_zarr_files(variable: str):
    """
    Get the file tree structure of a dataset.
    
    Returns a hierarchical view of all files in the Zarr store or
    COG directory with sizes, for display in a file browser UI.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    
    # Try local Zarr store first
    if zarr_path.exists():
        def build_tree(path: Path, prefix: str = "") -> list:
            """Recursively build file tree with sizes."""
            items = []
            
            try:
                entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            except PermissionError:
                return items
            
            for entry in entries:
                rel_path = f"{prefix}{entry.name}" if prefix else entry.name
                
                if entry.is_dir():
                    # Directory - get total size of contents
                    dir_size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                    children = build_tree(entry, f"{rel_path}/")
                    items.append({
                        "name": entry.name,
                        "path": rel_path,
                        "type": "directory",
                        "size": dir_size,
                        "children": children,
                    })
                else:
                    # File
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    items.append({
                        "name": entry.name,
                        "path": rel_path,
                        "type": "file",
                        "size": size,
                    })
            
            return items
        
        tree = build_tree(zarr_path)
        total_size = sum(f.stat().st_size for f in zarr_path.rglob("*") if f.is_file())
        
        return {
            "variable": variable,
            "root": f"{variable}.zarr",
            "format": "zarr",
            "total_size": total_size,
            "tree": tree,
        }
    
    # Fallback: list COG files from Azure
    cog_files = await _list_azure_cog_files(variable)
    if cog_files:
        total_size = sum(f["size"] for f in cog_files)
        tree = [
            {
                "name": f["name"].split("/")[-1],
                "path": f["name"],
                "type": "file",
                "size": f["size"],
                "date": f["date"],
            }
            for f in cog_files
        ]
        
        return {
            "variable": variable,
            "root": f"{variable}/",
            "format": "cog",
            "total_size": total_size,
            "tree": tree,
        }
    
    raise HTTPException(404, f"Dataset not found: {variable}")


@router.get("/{variable}/stats")
async def get_zarr_stats(
    variable: str,
    lon_min: float = Query(-180, description="West bound"),
    lon_max: float = Query(180, description="East bound"),
    lat_min: float = Query(-90, description="South bound"),
    lat_max: float = Query(90, description="North bound"),
):
    """
    Get statistics for a region from pre-computed Zarr metrics.
    
    Fast extraction using chunked Zarr arrays - computes regional
    mean, std, trend from the pre-calculated climatology arrays.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr store not found: {variable}")
    
    try:
        root = zarr.open_group(str(zarr_path), mode='r')
        
        # Get coordinate arrays
        lat = root["lat"][:]
        lon = root["lon"][:]
        
        # Create region mask
        lat_mask = (lat >= lat_min) & (lat <= lat_max)
        lon_mask = (lon >= lon_min) & (lon <= lon_max)
        
        lat_idx = np.where(lat_mask)[0]
        lon_idx = np.where(lon_mask)[0]
        
        if len(lat_idx) == 0 or len(lon_idx) == 0:
            return {
                "region": {"lon": [lon_min, lon_max], "lat": [lat_min, lat_max]},
                "error": "No data in specified region"
            }
        
        lat_slice = slice(lat_idx[0], lat_idx[-1] + 1)
        lon_slice = slice(lon_idx[0], lon_idx[-1] + 1)
        
        # Extract regional statistics from pre-computed arrays
        clim_mean = root["climatology_mean"][lat_slice, lon_slice]
        clim_std = root["climatology_std"][lat_slice, lon_slice]
        valid_count = root["valid_count"][lat_slice, lon_slice]
        trend = root["trend"][lat_slice, lon_slice]
        
        # Compute regional aggregates (nanmean to handle land pixels)
        with np.errstate(all='ignore'):
            return {
                "region": {
                    "lon": [lon_min, lon_max],
                    "lat": [lat_min, lat_max],
                    "pixels": int(np.sum(~np.isnan(clim_mean))),
                },
                "climatology": {
                    "mean": round(float(np.nanmean(clim_mean)), 2) if not np.all(np.isnan(clim_mean)) else None,
                    "std": round(float(np.nanmean(clim_std)), 2) if not np.all(np.isnan(clim_std)) else None,
                    "min": round(float(np.nanmin(clim_mean)), 2) if not np.all(np.isnan(clim_mean)) else None,
                    "max": round(float(np.nanmax(clim_mean)), 2) if not np.all(np.isnan(clim_mean)) else None,
                },
                "trend": {
                    "mean": round(float(np.nanmean(trend)), 4) if not np.all(np.isnan(trend)) else None,
                    "unit": "°C/year",
                },
                "coverage": {
                    "valid_pixels": int(np.sum(valid_count > 0)),
                    "total_pixels": int(valid_count.size),
                    "coverage_pct": round(100 * np.sum(valid_count > 0) / valid_count.size, 1),
                },
            }
    except Exception as e:
        raise HTTPException(500, f"Error computing stats: {str(e)}")


@router.get("/{variable}/timeseries")
async def get_zarr_timeseries(
    variable: str,
    lon: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
):
    """
    Extract time series for a specific point from Zarr store.
    
    Returns all available timestamps with values, plus climatology,
    monthly climatology, percentiles, and anomaly calculation for that pixel.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr store not found: {variable}")
    
    try:
        root = zarr.open_group(str(zarr_path), mode='r')
        
        # Get coordinates
        lat_arr = root["lat"][:]
        lon_arr = root["lon"][:]
        time_arr = root["time"][:]
        dates = root.attrs.get("dates", [])
        
        # Find nearest pixel
        lat_idx = int(np.argmin(np.abs(lat_arr - lat)))
        lon_idx = int(np.argmin(np.abs(lon_arr - lon)))
        
        # Extract time series
        data = root[variable][:, lat_idx, lon_idx]
        clim_mean = float(root["climatology_mean"][lat_idx, lon_idx])
        clim_std = float(root["climatology_std"][lat_idx, lon_idx])
        
        # Extract percentiles (if available)
        percentiles = {}
        if "percentile_10" in root:
            percentiles["p10"] = round(float(root["percentile_10"][lat_idx, lon_idx]), 2)
        if "percentile_50" in root:
            percentiles["p50"] = round(float(root["percentile_50"][lat_idx, lon_idx]), 2)
        if "percentile_90" in root:
            percentiles["p90"] = round(float(root["percentile_90"][lat_idx, lon_idx]), 2)
        
        # Extract monthly climatology (if available)
        monthly_climatology = None
        if "climatology_monthly_mean" in root:
            monthly_mean = root["climatology_monthly_mean"][:, lat_idx, lon_idx]
            monthly_std = root["climatology_monthly_std"][:, lat_idx, lon_idx] if "climatology_monthly_std" in root else [None] * 12
            monthly_p10 = root["monthly_percentile_10"][:, lat_idx, lon_idx] if "monthly_percentile_10" in root else [None] * 12
            monthly_p50 = root["monthly_percentile_50"][:, lat_idx, lon_idx] if "monthly_percentile_50" in root else [None] * 12
            monthly_p90 = root["monthly_percentile_90"][:, lat_idx, lon_idx] if "monthly_percentile_90" in root else [None] * 12
            
            monthly_climatology = []
            for m in range(12):
                entry = {
                    "month": m + 1,
                    "mean": round(float(monthly_mean[m]), 2) if not np.isnan(monthly_mean[m]) else None,
                }
                if monthly_std is not None and monthly_std[m] is not None and not np.isnan(monthly_std[m]):
                    entry["std"] = round(float(monthly_std[m]), 2)
                if monthly_p10 is not None and monthly_p10[m] is not None and not np.isnan(monthly_p10[m]):
                    entry["p10"] = round(float(monthly_p10[m]), 2)
                if monthly_p50 is not None and monthly_p50[m] is not None and not np.isnan(monthly_p50[m]):
                    entry["p50"] = round(float(monthly_p50[m]), 2)
                if monthly_p90 is not None and monthly_p90[m] is not None and not np.isnan(monthly_p90[m]):
                    entry["p90"] = round(float(monthly_p90[m]), 2)
                monthly_climatology.append(entry)
        
        # Extract trend (if available)
        trend = None
        if "trend" in root:
            trend_val = float(root["trend"][lat_idx, lon_idx])
            if not np.isnan(trend_val):
                trend = round(trend_val, 4)
        
        # Build response with monthly anomaly
        timeseries = []
        for i, t in enumerate(time_arr):
            val = data[i]
            if not np.isnan(val):
                # Get date string and month
                date_str = dates[i] if i < len(dates) else str(t)
                month = int(date_str.split('-')[1]) if '-' in date_str else None
                
                # Calculate anomaly using monthly climatology (if available) or overall mean
                if monthly_climatology and month:
                    monthly_clim = monthly_climatology[month - 1]["mean"]
                    anomaly = float(val) - monthly_clim if monthly_clim is not None else None
                else:
                    anomaly = float(val) - clim_mean if not np.isnan(clim_mean) else None
                
                timeseries.append({
                    "date": date_str,
                    "value": round(float(val), 2),
                    "anomaly": round(anomaly, 2) if anomaly is not None else None,
                })
        
        return {
            "location": {
                "lon": round(float(lon_arr[lon_idx]), 4),
                "lat": round(float(lat_arr[lat_idx]), 4),
                "requested": {"lon": lon, "lat": lat},
            },
            "climatology": {
                "mean": round(clim_mean, 2) if not np.isnan(clim_mean) else None,
                "std": round(clim_std, 2) if not np.isnan(clim_std) else None,
            },
            "percentiles": percentiles if percentiles else None,
            "monthly_climatology": monthly_climatology,
            "trend": trend,
            "timeseries": timeseries,
            "count": len(timeseries),
        }
    except Exception as e:
        raise HTTPException(500, f"Error extracting timeseries: {str(e)}")


@router.get("/{variable}/climatology")
async def get_zarr_climatology(
    variable: str,
    lon: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    month: int = Query(None, ge=1, le=12, description="Optional: specific month (1-12)"),
):
    """
    Get climatology values for a point.
    
    Returns monthly climatology mean/std/percentiles for a specific point.
    Optionally filter to a specific month.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr store not found: {variable}")
    
    try:
        root = zarr.open_group(str(zarr_path), mode='r')
        
        # Get coordinates
        lat_arr = root["lat"][:]
        lon_arr = root["lon"][:]
        
        # Find nearest pixel
        lat_idx = int(np.argmin(np.abs(lat_arr - lat)))
        lon_idx = int(np.argmin(np.abs(lon_arr - lon)))
        
        # Get overall climatology
        clim_mean = float(root["climatology_mean"][lat_idx, lon_idx])
        clim_std = float(root["climatology_std"][lat_idx, lon_idx])
        
        response = {
            "location": {
                "lon": round(float(lon_arr[lon_idx]), 4),
                "lat": round(float(lat_arr[lat_idx]), 4),
            },
            "overall": {
                "mean": round(clim_mean, 2) if not np.isnan(clim_mean) else None,
                "std": round(clim_std, 2) if not np.isnan(clim_std) else None,
            },
        }
        
        # Get monthly climatology if available
        if "climatology_monthly_mean" in root:
            monthly_mean = root["climatology_monthly_mean"][:, lat_idx, lon_idx]
            monthly_std = root["climatology_monthly_std"][:, lat_idx, lon_idx] if "climatology_monthly_std" in root else [None] * 12
            monthly_p10 = root["monthly_percentile_10"][:, lat_idx, lon_idx] if "monthly_percentile_10" in root else [None] * 12
            monthly_p50 = root["monthly_percentile_50"][:, lat_idx, lon_idx] if "monthly_percentile_50" in root else [None] * 12  
            monthly_p90 = root["monthly_percentile_90"][:, lat_idx, lon_idx] if "monthly_percentile_90" in root else [None] * 12
            
            if month:
                # Return specific month
                m_idx = month - 1
                response["month"] = month
                response["monthly"] = {
                    "mean": round(float(monthly_mean[m_idx]), 2) if not np.isnan(monthly_mean[m_idx]) else None,
                    "std": round(float(monthly_std[m_idx]), 2) if monthly_std[m_idx] is not None and not np.isnan(monthly_std[m_idx]) else None,
                    "p10": round(float(monthly_p10[m_idx]), 2) if monthly_p10[m_idx] is not None and not np.isnan(monthly_p10[m_idx]) else None,
                    "p50": round(float(monthly_p50[m_idx]), 2) if monthly_p50[m_idx] is not None and not np.isnan(monthly_p50[m_idx]) else None,
                    "p90": round(float(monthly_p90[m_idx]), 2) if monthly_p90[m_idx] is not None and not np.isnan(monthly_p90[m_idx]) else None,
                }
            else:
                # Return all months
                months = []
                for m in range(12):
                    entry = {
                        "month": m + 1,
                        "mean": round(float(monthly_mean[m]), 2) if not np.isnan(monthly_mean[m]) else None,
                    }
                    if monthly_std is not None and monthly_std[m] is not None and not np.isnan(monthly_std[m]):
                        entry["std"] = round(float(monthly_std[m]), 2)
                    if monthly_p10 is not None and monthly_p10[m] is not None and not np.isnan(monthly_p10[m]):
                        entry["p10"] = round(float(monthly_p10[m]), 2)
                    if monthly_p50 is not None and monthly_p50[m] is not None and not np.isnan(monthly_p50[m]):
                        entry["p50"] = round(float(monthly_p50[m]), 2)
                    if monthly_p90 is not None and monthly_p90[m] is not None and not np.isnan(monthly_p90[m]):
                        entry["p90"] = round(float(monthly_p90[m]), 2)
                    months.append(entry)
                response["monthly"] = months
        
        return response
    except Exception as e:
        raise HTTPException(500, f"Error extracting climatology: {str(e)}")


@router.get("/{variable}/percentiles")
async def get_zarr_percentiles(
    variable: str,
    lon: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    date: str = Query(None, description="Optional: date (YYYY-MM-DD) to compare current value against percentiles"),
):
    """
    Get percentile values for a point.
    
    Returns P10, P50, P90 for the point. If a date is provided, also returns
    the percentile rank of that date's value.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr store not found: {variable}")
    
    try:
        root = zarr.open_group(str(zarr_path), mode='r')
        
        # Get coordinates
        lat_arr = root["lat"][:]
        lon_arr = root["lon"][:]
        
        # Find nearest pixel
        lat_idx = int(np.argmin(np.abs(lat_arr - lat)))
        lon_idx = int(np.argmin(np.abs(lon_arr - lon)))
        
        response = {
            "location": {
                "lon": round(float(lon_arr[lon_idx]), 4),
                "lat": round(float(lat_arr[lat_idx]), 4),
            },
        }
        
        # Get overall percentiles
        if "percentile_10" in root:
            p10 = float(root["percentile_10"][lat_idx, lon_idx])
            p50 = float(root["percentile_50"][lat_idx, lon_idx])
            p90 = float(root["percentile_90"][lat_idx, lon_idx])
            
            response["percentiles"] = {
                "p10": round(p10, 2) if not np.isnan(p10) else None,
                "p50": round(p50, 2) if not np.isnan(p50) else None,
                "p90": round(p90, 2) if not np.isnan(p90) else None,
            }
        
        # If date provided, calculate percentile rank
        if date:
            dates = root.attrs.get("dates", [])
            if date in dates:
                date_idx = dates.index(date)
                current_value = float(root[variable][date_idx, lat_idx, lon_idx])
                
                if not np.isnan(current_value):
                    # Get all historical values for this pixel
                    all_values = root[variable][:, lat_idx, lon_idx]
                    valid_values = all_values[~np.isnan(all_values)]
                    
                    # Calculate percentile rank
                    rank = np.sum(valid_values <= current_value) / len(valid_values) * 100
                    
                    response["current"] = {
                        "date": date,
                        "value": round(current_value, 2),
                        "percentile_rank": round(rank, 1),
                    }
                    
                    # Get month and compare to monthly percentiles
                    month = int(date.split('-')[1])
                    if "monthly_percentile_10" in root:
                        mp10 = float(root["monthly_percentile_10"][month - 1, lat_idx, lon_idx])
                        mp50 = float(root["monthly_percentile_50"][month - 1, lat_idx, lon_idx])
                        mp90 = float(root["monthly_percentile_90"][month - 1, lat_idx, lon_idx])
                        
                        response["current"]["monthly_percentiles"] = {
                            "month": month,
                            "p10": round(mp10, 2) if not np.isnan(mp10) else None,
                            "p50": round(mp50, 2) if not np.isnan(mp50) else None,
                            "p90": round(mp90, 2) if not np.isnan(mp90) else None,
                        }
        
        return response
    except Exception as e:
        raise HTTPException(500, f"Error extracting percentiles: {str(e)}")


@router.get("/{variable}/slice")
async def get_zarr_slice(
    variable: str,
    time_idx: int = Query(0, description="Time index"),
    lon_min: float = Query(-180),
    lon_max: float = Query(180),
    lat_min: float = Query(-90),
    lat_max: float = Query(90),
    downsample: int = Query(1, ge=1, le=100, description="Downsample factor"),
):
    """
    Get a 2D slice of data as JSON grid.
    
    For browser-based visualization without tile rendering.
    Supports spatial subsetting and downsampling for performance.
    """
    zarr_path = ZARR_DIR / f"{variable}.zarr"
    if not zarr_path.exists():
        raise HTTPException(404, f"Zarr store not found: {variable}")
    
    try:
        root = zarr.open_group(str(zarr_path), mode='r')
        
        lat = root["lat"][:]
        lon = root["lon"][:]
        
        # Spatial subset indices
        lat_mask = (lat >= lat_min) & (lat <= lat_max)
        lon_mask = (lon >= lon_min) & (lon <= lon_max)
        
        lat_idx = np.where(lat_mask)[0]
        lon_idx = np.where(lon_mask)[0]
        
        if len(lat_idx) == 0 or len(lon_idx) == 0:
            return {"error": "No data in region"}
        
        lat_slice = slice(lat_idx[0], lat_idx[-1] + 1, downsample)
        lon_slice = slice(lon_idx[0], lon_idx[-1] + 1, downsample)
        
        # Extract data
        data = root[variable][time_idx, lat_slice, lon_slice]
        lat_subset = lat[lat_slice]
        lon_subset = lon[lon_slice]
        
        # Convert to list (JSON-serializable), replacing NaN with null
        data_list = np.where(np.isnan(data), None, np.round(data, 2)).tolist()
        
        return {
            "time_idx": time_idx,
            "shape": list(data.shape),
            "lat": lat_subset.tolist(),
            "lon": lon_subset.tolist(),
            "data": data_list,
            "bounds": {
                "lat": [float(lat_subset.min()), float(lat_subset.max())],
                "lon": [float(lon_subset.min()), float(lon_subset.max())],
            },
        }
    except Exception as e:
        raise HTTPException(500, f"Error reading slice: {str(e)}")
