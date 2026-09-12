"""
Prefect 3 Tasks for ECV Ingestion Pipeline

Defines individual tasks for downloading, processing, and cataloging data.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from prefect import task
from prefect.logging import get_run_logger

from server.pipeline.config import get_config, get_variable_config
from server.pipeline.downloaders import get_downloader

logger = logging.getLogger(__name__)


def _get_logger():
    """Get Prefect run logger if in task context, else standard logger."""
    try:
        return get_run_logger()
    except Exception:
        return logger


@task(
    name="upload-to-azure",
    description="Upload COG file to Azure Blob Storage",
    retries=3,
    retry_delay_seconds=[30, 60, 120],
    timeout_seconds=300,
)
def upload_to_azure(
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Upload a COG file to Azure Blob Storage.
    
    Args:
        result: Result dict from download_and_convert
        
    Returns:
        Result dict enriched with blob_url, or original if skipped/failed
    """
    if result is None:
        return None
    
    if result.get("status") == "skipped":
        return result
    
    try:
        log = _get_logger()
    except Exception:
        log = logger
    
    config = get_config()
    
    # Check if Azure upload is enabled
    if not config.azure_upload_enabled:
        log.debug("Azure upload disabled, skipping")
        return result
    
    if not config.azure_storage_account or not config.azure_storage_sas_token:
        log.warning("Azure storage not configured, skipping upload")
        return result
    
    try:
        from azure.storage.blob import BlobServiceClient
        
        local_path = Path(result["path"])
        if not local_path.exists():
            log.error(f"Local file not found: {local_path}")
            return result
        
        # Construct blob name: {variable}/{filename}
        variable = result.get("variable", "unknown")
        blob_name = f"{variable}/{local_path.name}"
        
        # Create blob service client
        account_url = f"https://{config.azure_storage_account}.blob.core.windows.net"
        blob_service = BlobServiceClient(
            account_url=account_url,
            credential=config.azure_storage_sas_token,
        )
        
        # Get container client
        container = blob_service.get_container_client(config.azure_storage_container)
        
        # Upload file
        blob_client = container.get_blob_client(blob_name)
        with open(local_path, "rb") as f:
            blob_client.upload_blob(f, overwrite=True)
        
        blob_url = f"{account_url}/{config.azure_storage_container}/{blob_name}"
        log.info(f"✓ Uploaded to Azure: {blob_name}")
        
        return {
            **result,
            "blob_url": blob_url,
            "uploaded": True,
        }
        
    except Exception as e:
        log.error(f"✗ Azure upload failed: {e}")
        return {
            **result,
            "uploaded": False,
            "upload_error": str(e),
        }


@task(
    name="upload-stac-to-azure",
    description="Upload STAC catalog files to Azure Blob Storage",
    retries=3,
    retry_delay_seconds=[30, 60, 120],
    timeout_seconds=300,
)
def upload_stac_to_azure(
    files: list[str] | None = None,
    sync_all: bool = False,
) -> dict[str, Any]:
    """
    Upload STAC catalog files to Azure Blob Storage.
    
    Args:
        files: List of relative paths (e.g., ["catalog.json", "collections/sst.json"])
               If None, uploads all changed files
        sync_all: Upload all STAC files (full sync)
        
    Returns:
        Result dict with upload stats
    """
    try:
        log = _get_logger()
    except Exception:
        log = logger
    
    config = get_config()
    
    # Check if Azure is configured
    if not config.azure_storage_account or not config.azure_storage_sas_token:
        log.debug("Azure storage not configured, skipping STAC upload")
        return {"status": "skipped", "reason": "Azure not configured"}
    
    if not config.azure_upload_enabled:
        log.debug("Azure upload disabled, skipping STAC upload")
        return {"status": "skipped", "reason": "Azure upload disabled"}
    
    try:
        from azure.storage.blob import BlobServiceClient
        from pathlib import Path
        
        stac_dir = Path(__file__).parent.parent / "stac"
        if not stac_dir.exists():
            return {"status": "skipped", "reason": "STAC directory not found"}
        
        # Determine which files to upload
        if sync_all:
            # Upload all JSON files in STAC directory
            files_to_upload = []
            for json_file in stac_dir.rglob("*.json"):
                rel_path = json_file.relative_to(stac_dir)
                files_to_upload.append(str(rel_path))
        elif files:
            files_to_upload = files
        else:
            # No files specified
            return {"status": "skipped", "reason": "No files specified"}
        
        # Create blob service client
        account_url = f"https://{config.azure_storage_account}.blob.core.windows.net"
        blob_service = BlobServiceClient(
            account_url=account_url,
            credential=config.azure_storage_sas_token,
        )
        
        # Get/create container client
        container = blob_service.get_container_client(config.azure_stac_container)
        
        # Create container if it doesn't exist
        try:
            container.create_container()
            log.info(f"Created STAC container: {config.azure_stac_container}")
        except Exception:
            pass  # Container already exists
        
        # Upload files
        uploaded = 0
        failed = 0
        
        for rel_path in files_to_upload:
            local_path = stac_dir / rel_path
            if not local_path.exists():
                log.warning(f"STAC file not found: {local_path}")
                failed += 1
                continue
            
            try:
                # Upload with JSON content type
                blob_client = container.get_blob_client(rel_path)
                with open(local_path, "rb") as f:
                    blob_client.upload_blob(
                        f, 
                        overwrite=True,
                        content_settings={"content_type": "application/json"},
                    )
                uploaded += 1
            except Exception as e:
                log.error(f"Failed to upload {rel_path}: {e}")
                failed += 1
        
        log.info(f"STAC upload: {uploaded} uploaded, {failed} failed")
        
        return {
            "status": "success" if failed == 0 else "partial",
            "uploaded": uploaded,
            "failed": failed,
            "container": config.azure_stac_container,
        }
        
    except Exception as e:
        log.error(f"STAC upload failed: {e}")
        return {"status": "failed", "error": str(e)}


@task(
    name="download-and-convert",
    description="Download and convert a single date for a variable",
    retries=3,
    retry_delay_seconds=[30, 60, 120],
    timeout_seconds=600,
)
def download_and_convert(
    variable: str,
    date_str: str,
    stream: str = "auto",
    force: bool = False,
) -> dict[str, Any] | None:
    """
    Download and convert data for a single date.
    
    Args:
        variable: Variable name (sst, sic, sla, chl, kd490, rrs)
        date_str: Date in YYYY-MM-DD format
        stream: Data stream - "nrt", "rep", or "auto"
        force: Overwrite existing files
        
    Returns:
        Result dict with path and stats, or None if failed/skipped
    """
    log = _get_logger()
    config = get_config()
    
    # Check if already exists
    cog_path = config.get_cog_path(variable, date_str)
    
    if cog_path.exists() and not force:
        log.info(f"Already exists: {cog_path}")
        return {"path": str(cog_path), "status": "skipped", "date": date_str, "variable": variable}
    
    # Download and convert
    downloader = get_downloader(variable)
    result = downloader.download_and_convert(date_str, stream=stream, force=force)
    
    if result:
        log.info(f"✓ {variable} {date_str}: {result['path']}")
        return {
            "path": result["path"],
            "stats": result["stats"],
            "status": "created",
            "date": date_str,
            "variable": variable,
        }
    else:
        log.warning(f"✗ {variable} {date_str}: failed")
        return None


@task(
    name="update-catalog",
    description="Update the data catalog with new entries",
    retries=2,
    retry_delay_seconds=10,
)
def update_catalog(
    results: list[dict[str, Any]],
    catalog_path: Path | None = None,
) -> int:
    """
    Update the catalog JSON with new COG entries.
    
    Args:
        results: List of result dicts from download_and_convert
        catalog_path: Path to catalog JSON file
        
    Returns:
        Number of entries added
    """
    log = _get_logger()
    config = get_config()
    
    if catalog_path is None:
        catalog_path = config.catalog_file
    else:
        catalog_path = Path(catalog_path)
    
    # Load existing catalog
    if catalog_path.exists():
        with open(catalog_path) as f:
            catalog = json.load(f)
    else:
        catalog = {
            "created": datetime.now().isoformat(),
            "variables": {},
        }
    
    added = 0
    for result in results:
        if result is None or result.get("status") == "skipped":
            continue
        
        variable = result.get("variable")
        date_str = result.get("date")
        
        if not variable or not date_str:
            continue
        
        if variable not in catalog["variables"]:
            catalog["variables"][variable] = {
                "entries": {},
                "count": 0,
            }
        
        catalog["variables"][variable]["entries"][date_str] = {
            "path": result["path"],
            "stats": result.get("stats", {}),
            "ingested_at": datetime.now().isoformat(),
        }
        catalog["variables"][variable]["count"] = len(
            catalog["variables"][variable]["entries"]
        )
        added += 1
    
    # Write catalog
    catalog["updated"] = datetime.now().isoformat()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)
    
    log.info(f"Updated catalog with {added} entries")
    return added


@task(
    name="generate-date-range",
    description="Generate list of dates to process",
)
def generate_date_range(
    start_date: str,
    end_date: str,
) -> list[str]:
    """
    Generate list of dates between start and end (inclusive).
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        List of date strings
    """
    from datetime import timedelta
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    return dates


@task(
    name="get-missing-dates",
    description="Find dates not yet in catalog",
)
def get_missing_dates(
    variable: str,
    dates: list[str],
    catalog_path: Path | None = None,
) -> list[str]:
    """
    Filter dates to only those not in catalog.
    
    Args:
        variable: Variable name
        dates: List of date strings to check
        catalog_path: Path to catalog JSON
        
    Returns:
        List of missing date strings
    """
    config = get_config()
    
    if catalog_path is None:
        catalog_path = config.catalog_file
    else:
        catalog_path = Path(catalog_path)
    
    if not catalog_path.exists():
        return dates
    
    with open(catalog_path) as f:
        catalog = json.load(f)
    
    existing = set()
    if variable in catalog.get("variables", {}):
        existing = set(catalog["variables"][variable].get("entries", {}).keys())
    
    missing = [d for d in dates if d not in existing]
    return missing


@task(
    name="cleanup-temp-files",
    description="Remove temporary files after processing",
)
def cleanup_temp_files(temp_dir: Path | None = None) -> int:
    """
    Clean up temporary download files.
    
    Args:
        temp_dir: Temp directory to clean (default: from config)
        
    Returns:
        Number of files removed
    """
    import shutil
    
    log = _get_logger()
    config = get_config()
    
    if temp_dir is None:
        temp_dir = config.temp_dir
    else:
        temp_dir = Path(temp_dir)
    
    if not temp_dir.exists():
        return 0
    
    count = 0
    for item in temp_dir.iterdir():
        if item.is_file():
            item.unlink()
            count += 1
        elif item.is_dir():
            shutil.rmtree(item)
            count += 1
    
    log.info(f"Cleaned up {count} temp items")
    return count


@task(
    name="notify-completion",
    description="Send notification on completion",
)
def notify_completion(
    variable: str,
    processed: int,
    failed: int,
    duration_seconds: float,
) -> None:
    """
    Log completion summary (could be extended to send webhooks, emails, etc.)
    
    Args:
        variable: Variable name
        processed: Number of dates processed
        failed: Number of dates failed
        duration_seconds: Total duration
    """
    log = _get_logger()
    
    hours = duration_seconds / 3600
    rate = processed / hours if hours > 0 else 0
    
    log.info(
        f"Completed {variable}: {processed} processed, {failed} failed, "
        f"{duration_seconds:.1f}s ({rate:.1f}/hour)"
    )


@task(
    name="build-zarr-store",
    description="Build or update Zarr store from COG files",
    retries=1,
    timeout_seconds=1800,  # 30 minutes
)
def build_zarr_store(
    variable: str,
    target_resolution: tuple[int, int] = (3600, 7200),
    force_rebuild: bool = False,
) -> dict[str, Any] | None:
    """
    Build or update Zarr store from COG files for a variable.
    
    Computes and stores:
    - Time-indexed data arrays
    - Overall climatology (mean, std)
    - Monthly climatology (mean, std for each calendar month)
    - Percentiles (P10, P50, P90) overall and per-month
    - Linear trend per pixel (units/year)
    
    Args:
        variable: Variable name (sst, sla, sic, chl, kd490, rrs)
        target_resolution: Target grid size (lat, lon)
        force_rebuild: Force complete rebuild (default: only update)
        
    Returns:
        Result dict with path and metadata, or None if failed
    """
    log = _get_logger()
    
    try:
        from server.zarr_builder import create_zarr_store
        
        log.info(f"Building Zarr store for {variable} (force={force_rebuild})")
        
        zarr_path = create_zarr_store(
            variable=variable,
            target_resolution=target_resolution,
            force_rebuild=force_rebuild,
        )
        
        # Get store info
        import zarr
        root = zarr.open_group(zarr_path, mode='r')
        n_times = root['time'].shape[0] if 'time' in root else 0
        dates = list(root.attrs.get('dates', []))
        
        log.info(f"✓ {variable}: Zarr store ready with {n_times} timesteps")
        
        return {
            "variable": variable,
            "path": str(zarr_path),
            "n_times": n_times,
            "date_range": [dates[0], dates[-1]] if dates else None,
            "status": "success",
        }
    except Exception as e:
        log.error(f"✗ {variable}: Zarr build failed: {e}")
        return None


@task(
    name="get-zarr-status",
    description="Get current status of a Zarr store",
)
def get_zarr_status(
    variable: str,
) -> dict[str, Any]:
    """
    Get status information about an existing Zarr store.
    
    Args:
        variable: Variable name
        
    Returns:
        Status dict with metadata
    """
    log = _get_logger()
    config = get_config()
    zarr_path = config.zarr_dir / f"{variable}.zarr"
    
    if not zarr_path.exists():
        return {
            "variable": variable,
            "exists": False,
            "n_times": 0,
        }
    
    try:
        import zarr
        root = zarr.open_group(zarr_path, mode='r')
        
        dates = list(root.attrs.get('dates', []))
        global_stats = root.attrs.get('global_stats', {})
        monthly_count = root.attrs.get('monthly_sample_count', [])
        
        # Check which statistics arrays exist
        has_climatology = 'climatology_mean' in root
        has_monthly = 'climatology_monthly_mean' in root
        has_percentiles = 'percentile_10' in root
        has_trend = 'trend' in root
        
        return {
            "variable": variable,
            "exists": True,
            "path": str(zarr_path),
            "n_times": len(dates),
            "date_range": [dates[0], dates[-1]] if dates else None,
            "has_climatology": has_climatology,
            "has_monthly_climatology": has_monthly,
            "has_percentiles": has_percentiles,
            "has_trend": has_trend,
            "monthly_sample_count": monthly_count,
            "global_mean": global_stats.get('temporal_mean'),
        }
    except Exception as e:
        log.warning(f"Failed to read Zarr status for {variable}: {e}")
        return {
            "variable": variable,
            "exists": True,
            "error": str(e),
        }


@task(
    name="check-zarr-needs-update",
    description="Check if Zarr store needs updating based on new COGs",
)
def check_zarr_needs_update(
    variable: str,
) -> bool:
    """
    Check if Zarr store needs updating based on available COGs.
    
    Args:
        variable: Variable name
        
    Returns:
        True if update needed, False otherwise
    """
    log = _get_logger()
    config = get_config()
    
    zarr_path = config.zarr_dir / f"{variable}.zarr"
    cog_dir = config.products_dir / variable
    
    # If Zarr doesn't exist, definitely needs build
    if not zarr_path.exists():
        log.info(f"{variable}: Zarr store does not exist, needs build")
        return True
    
    # Count COG files
    cog_files = list(cog_dir.glob("*.tif"))
    n_cogs = len(cog_files)
    
    if n_cogs == 0:
        log.info(f"{variable}: No COG files found")
        return False
    
    # Get Zarr timestep count
    try:
        import zarr
        root = zarr.open_group(zarr_path, mode='r')
        n_zarr = len(root.attrs.get('dates', []))
        
        if n_cogs > n_zarr:
            log.info(f"{variable}: {n_cogs} COGs vs {n_zarr} in Zarr, needs update")
            return True
        else:
            log.info(f"{variable}: Zarr is up to date ({n_zarr} timesteps)")
            return False
    except Exception as e:
        log.warning(f"Error checking Zarr: {e}")
        return True


@task(
    name="update-stac-collection",
    description="Update STAC collection for a variable from filesystem",
)
def update_stac_collection(
    variable: str,
) -> dict[str, Any]:
    """
    Update STAC collection after data ingestion.
    
    Scans the variable's COG directory and updates:
    - Collection metadata (temporal extent, item count)
    - Individual item files for each COG
    
    Then uploads to Azure Blob Storage if configured.
    
    Args:
        variable: Variable name
        
    Returns:
        Collection summary
    """
    log = _get_logger()
    
    try:
        from server.stac import update_collection_from_filesystem
        from server.stac.catalog import STAC_DIR
        
        collection = update_collection_from_filesystem(variable)
        
        if collection:
            # Extract summary from collection
            extent = collection.get("extent", {})
            temporal = extent.get("temporal", {}).get("interval", [[None, None]])[0]
            item_links = [l for l in collection.get("links", []) if l.get("rel") == "item"]
            n_items = len(item_links)
            
            log.info(f"STAC: {variable} updated with {n_items} items")
            
            # Collect files to upload to Azure
            files_to_upload = [
                "catalog.json",
                f"collections/{variable}.json",
            ]
            # Add all item files
            items_dir = STAC_DIR / "items" / variable
            if items_dir.exists():
                for item_file in items_dir.glob("*.json"):
                    files_to_upload.append(f"items/{variable}/{item_file.name}")
            
            # Upload to Azure
            azure_result = upload_stac_to_azure(files=files_to_upload)
            
            return {
                "variable": variable,
                "n_items": n_items,
                "start_date": temporal[0] if temporal else None,
                "end_date": temporal[1] if temporal else None,
                "status": "updated",
                "azure": azure_result,
            }
        else:
            log.warning(f"STAC: {variable} update returned empty")
            return {"variable": variable, "status": "empty"}
            
    except Exception as e:
        log.error(f"STAC update failed for {variable}: {e}")
        return {"variable": variable, "status": "failed", "error": str(e)}


@task(
    name="build-stac-catalog",
    description="Build complete STAC catalog from all COG products",
)
def build_stac_catalog() -> dict[str, Any]:
    """
    Build the complete STAC catalog from filesystem.
    
    Scans all variable directories and creates/updates:
    - Root catalog.json
    - Collections for each variable
    - Items for each COG file
    
    Then uploads entire catalog to Azure Blob Storage if configured.
    
    Returns:
        Summary of catalog build
    """
    log = _get_logger()
    
    try:
        from server.stac import build_catalog
        
        build_catalog()
        
        # Get summary
        from server.stac.catalog import STAC_DIR, VARIABLE_METADATA
        
        collections = list((STAC_DIR / "collections").glob("*.json"))
        
        # Full sync to Azure
        azure_result = upload_stac_to_azure(sync_all=True)
        
        summary = {
            "n_collections": len(collections),
            "collections": [c.stem for c in collections],
            "status": "success",
            "azure": azure_result,
        }
        
        log.info(f"STAC catalog built: {len(collections)} collections")
        return summary
        
    except Exception as e:
        log.error(f"STAC catalog build failed: {e}")
        return {"status": "failed", "error": str(e)}


@task(
    name="update-zarr-stac",
    description="Update STAC collection for a Zarr store",
)
def update_zarr_stac(
    variable: str,
) -> dict[str, Any]:
    """
    Update STAC collection for a Zarr store after build.
    
    Creates/updates:
    - Collection metadata (temporal extent, analytics arrays)
    - Single analytics item with Zarr asset links
    
    Then uploads to Azure Blob Storage if configured.
    
    Args:
        variable: Variable name
        
    Returns:
        Collection summary
    """
    log = _get_logger()
    
    try:
        from server.stac import update_zarr_collection
        
        collection = update_zarr_collection(variable)
        
        if collection:
            # Extract summary from collection
            extent = collection.get("extent", {})
            temporal = extent.get("temporal", {}).get("interval", [[None, None]])[0]
            summaries = collection.get("summaries", {})
            
            log.info(f"STAC: zarr-{variable} updated")
            
            # Upload Zarr STAC files to Azure
            files_to_upload = [
                "catalog.json",
                f"collections/zarr-{variable}.json",
                f"items/zarr-{variable}/analytics.json",
            ]
            azure_result = upload_stac_to_azure(files=files_to_upload)
            
            return {
                "variable": variable,
                "collection_id": f"zarr-{variable}",
                "start_date": temporal[0] if temporal else None,
                "end_date": temporal[1] if temporal else None,
                "n_timesteps": summaries.get("arco:n_timesteps"),
                "status": "updated",
                "azure": azure_result,
            }
        else:
            log.warning(f"STAC: zarr-{variable} update returned empty")
            return {"variable": variable, "status": "empty"}
            
    except Exception as e:
        log.error(f"STAC update failed for zarr-{variable}: {e}")
        return {"variable": variable, "status": "failed", "error": str(e)}
