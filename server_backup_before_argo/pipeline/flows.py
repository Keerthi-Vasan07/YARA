"""
Prefect 3 Flows for ECV Ingestion Pipeline

Defines high-level flows for backfill and NRT ingestion.
"""

import logging
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from prefect import flow
from prefect.futures import wait
from prefect.logging import get_run_logger

from server.pipeline.config import get_config, VARIABLES

# Dask integration - optional
try:
    from prefect_dask import DaskTaskRunner
    HAS_DASK = True
except ImportError:
    HAS_DASK = False
    DaskTaskRunner = None
from server.pipeline.tasks import (
    download_and_convert,
    upload_to_azure,
    update_catalog,
    generate_date_range,
    get_missing_dates,
    cleanup_temp_files,
    notify_completion,
    build_zarr_store,
    get_zarr_status,
    check_zarr_needs_update,
    update_stac_collection,
    build_stac_catalog,
    update_zarr_stac,
)

logger = logging.getLogger(__name__)


def get_dask_task_runner() -> Any | None:
    """Get DaskTaskRunner if available and configured."""
    if not HAS_DASK:
        return None
    
    scheduler_address = os.environ.get("DASK_SCHEDULER_ADDRESS")
    if not scheduler_address:
        return None
    
    return DaskTaskRunner(address=scheduler_address)


@flow(
    name="ingest-date",
    description="Ingest a single date for a variable",
    retries=1,
)
def ingest_date(
    variable: str,
    date_str: str,
    force: bool = False,
) -> dict[str, Any] | None:
    """
    Ingest a single date for a single variable.
    
    Args:
        variable: Variable name
        date_str: Date in YYYY-MM-DD format
        force: Overwrite existing data
        
    Returns:
        Result dict or None if failed
    """
    result = download_and_convert(
        variable=variable,
        date_str=date_str,
        force=force,
    )
    
    if result and result.get("status") == "created":
        # Upload to Azure if enabled
        result = upload_to_azure(result)
        update_catalog([result])
        update_stac_collection(variable)
    
    return result


def _backfill_with_dask(
    variable: str,
    dates: list[str],
    all_dates: list[str],
    max_concurrent: int,
    skip_existing: bool,
    batch_size: int,
    start_time: float,
) -> dict[str, Any]:
    """
    Backfill using Dask distributed cluster.
    
    This is a subflow that uses DaskTaskRunner for distributed processing.
    """
    from prefect_dask import DaskTaskRunner
    
    log = get_run_logger()
    scheduler = os.environ.get("DASK_SCHEDULER_ADDRESS", "tcp://localhost:8786")
    
    @flow(
        name="backfill-dask-batch",
        task_runner=DaskTaskRunner(address=scheduler),
    )
    def process_batch_dask(batch_dates: list[str], var: str, force: bool) -> list[dict]:
        """Process a batch of dates on Dask cluster."""
        batch_log = get_run_logger()
        
        # Submit all tasks to Dask
        futures = []
        for date_str in batch_dates:
            future = download_and_convert.submit(
                variable=var,
                date_str=date_str,
                force=force,
            )
            futures.append(future)
        
        # Wait for all
        wait(futures)
        
        # Collect results
        results = []
        for future in futures:
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                batch_log.error(f"Task failed: {e}")
        
        return results
    
    # Process in batches
    processed = 0
    failed = 0
    
    for batch_start in range(0, len(dates), batch_size):
        batch = dates[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        log.info(f"Processing batch {batch_num}: {len(batch)} dates on Dask cluster")
        
        # Run batch on Dask
        batch_results = process_batch_dask(
            batch_dates=batch,
            var=variable,
            force=not skip_existing,
        )
        
        # Upload results to Azure and update catalog
        upload_results = []
        for result in batch_results:
            if result.get("status") == "created":
                result = upload_to_azure(result)
                upload_results.append(result)
                processed += 1
            elif result.get("status") != "skipped":
                failed += 1
        
        if upload_results:
            update_catalog(upload_results)
        
        log.info(f"Batch {batch_num} complete: {len(upload_results)} created, running total: {processed}")
    
    # Update STAC collection
    if processed > 0:
        update_stac_collection(variable)
    
    duration = time.time() - start_time
    notify_completion(variable, processed, failed, duration)
    
    return {
        "variable": variable,
        "processed": processed,
        "failed": failed,
        "skipped": len(all_dates) - len(dates),
        "duration_seconds": duration,
        "mode": "dask",
    }


@flow(
    name="backfill-variable",
    description="Backfill a variable over a date range",
    persist_result=True,
)
def backfill_variable(
    variable: str,
    start_date: str,
    end_date: str,
    max_concurrent: int = 4,
    skip_existing: bool = True,
    batch_size: int = 30,
    use_dask: bool = False,
) -> dict[str, Any]:
    """
    Backfill a variable over a date range.
    
    Args:
        variable: Variable name
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_concurrent: Max concurrent downloads
        skip_existing: Skip dates already in catalog
        batch_size: Number of dates per batch (for catalog updates)
        use_dask: Use Dask cluster for distributed processing
        
    Returns:
        Summary dict with stats
    """
    log = get_run_logger()
    start_time = time.time()
    
    # Generate date range
    all_dates = generate_date_range(start_date, end_date)
    log.info(f"Total dates in range: {len(all_dates)}")
    
    # Filter to missing dates
    if skip_existing:
        dates = get_missing_dates(variable, all_dates)
        log.info(f"Missing dates to process: {len(dates)}")
    else:
        dates = all_dates
    
    if not dates:
        log.info("No dates to process")
        return {
            "variable": variable,
            "processed": 0,
            "failed": 0,
            "skipped": len(all_dates),
            "duration_seconds": 0,
        }
    
    # Use Dask if requested and available
    if use_dask:
        task_runner = get_dask_task_runner()
        if task_runner:
            log.info(f"Using Dask cluster: {os.environ.get('DASK_SCHEDULER_ADDRESS')}")
            return _backfill_with_dask(
                variable=variable,
                dates=dates,
                all_dates=all_dates,
                max_concurrent=max_concurrent,
                skip_existing=skip_existing,
                batch_size=batch_size,
                start_time=start_time,
            )
        else:
            log.warning("Dask requested but not available, falling back to local")
    
    # Process in batches (local mode)
    processed = 0
    failed = 0
    
    for batch_start in range(0, len(dates), batch_size):
        batch = dates[batch_start:batch_start + batch_size]
        log.info(f"Processing batch {batch_start // batch_size + 1}: {len(batch)} dates")
        
        # Submit tasks concurrently
        futures = []
        for date_str in batch:
            future = download_and_convert.submit(
                variable=variable,
                date_str=date_str,
                force=not skip_existing,
            )
            futures.append(future)
            
            # Limit concurrency
            if len(futures) >= max_concurrent:
                # Wait for some to complete
                wait(futures[:max_concurrent // 2])
        
        # Wait for batch to complete
        wait(futures)
        
        # Collect results
        batch_results = []
        for future in futures:
            try:
                result = future.result()
                if result:
                    if result.get("status") == "created":
                        # Upload to Azure if enabled
                        result = upload_to_azure(result)
                        processed += 1
                        batch_results.append(result)
                    elif result.get("status") == "skipped":
                        pass  # Already counted
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Task failed: {e}")
                failed += 1
        
        # Update catalog with batch results
        if batch_results:
            update_catalog(batch_results)
        
        log.info(f"Batch complete: {len(batch_results)} created, running total: {processed}")
    
    # Update STAC collection with all new items
    if processed > 0:
        update_stac_collection(variable)
    
    duration = time.time() - start_time
    
    # Notify completion
    notify_completion(variable, processed, failed, duration)
    
    return {
        "variable": variable,
        "processed": processed,
        "failed": failed,
        "skipped": len(all_dates) - len(dates),
        "duration_seconds": duration,
    }


@flow(
    name="backfill-all-variables",
    description="Backfill all variables over a date range",
)
def backfill_all_variables(
    start_date: str,
    end_date: str,
    variables: list[str] | None = None,
    max_concurrent: int = 4,
) -> dict[str, dict[str, Any]]:
    """
    Backfill multiple variables over a date range.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        variables: List of variables (default: all)
        max_concurrent: Max concurrent downloads per variable
        
    Returns:
        Dict mapping variable name to summary
    """
    log = get_run_logger()
    
    if variables is None:
        variables = list(VARIABLES.keys())
    
    results = {}
    for variable in variables:
        log.info(f"Starting backfill for {variable}")
        result = backfill_variable(
            variable=variable,
            start_date=start_date,
            end_date=end_date,
            max_concurrent=max_concurrent,
        )
        results[variable] = result
    
    # Cleanup temp files
    cleanup_temp_files()
    
    return results


@flow(
    name="ingest-nrt",
    description="Ingest Near Real-Time data for all variables",
)
def ingest_nrt(
    variables: list[str] | None = None,
    lookback_days: int = 3,
) -> dict[str, dict[str, Any]]:
    """
    Ingest near real-time data (last N days).
    
    Args:
        variables: List of variables (default: all)
        lookback_days: Number of days to look back
        
    Returns:
        Dict mapping variable name to summary
    """
    log = get_run_logger()
    
    if variables is None:
        variables = list(VARIABLES.keys())
    
    # Calculate date range
    end = date.today() - timedelta(days=1)  # Yesterday (today may not be ready)
    start = end - timedelta(days=lookback_days - 1)
    
    start_date = start.strftime("%Y-%m-%d")
    end_date = end.strftime("%Y-%m-%d")
    
    log.info(f"NRT ingestion: {start_date} to {end_date} for {len(variables)} variables")
    
    results = {}
    for variable in variables:
        log.info(f"Processing NRT for {variable}")
        
        # Get dates to process
        all_dates = generate_date_range(start_date, end_date)
        dates = get_missing_dates(variable, all_dates)
        
        if not dates:
            log.info(f"No new dates for {variable}")
            results[variable] = {"processed": 0, "failed": 0}
            continue
        
        # Process each date
        batch_results = []
        failed = 0
        
        for date_str in dates:
            result = download_and_convert(
                variable=variable,
                date_str=date_str,
            )
            if result and result.get("status") == "created":
                # Upload to Azure if enabled
                result = upload_to_azure(result)
                batch_results.append(result)
            elif result is None:
                failed += 1
        
        # Update catalog
        if batch_results:
            update_catalog(batch_results)
            update_stac_collection(variable)
        
        results[variable] = {
            "processed": len(batch_results),
            "failed": failed,
        }
    
    # Cleanup temp files
    cleanup_temp_files()
    
    return results


@flow(
    name="ingest-latest",
    description="Ingest the most recent available data",
)
def ingest_latest(
    variables: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Ingest the most recent available data (simplified NRT).
    
    Args:
        variables: List of variables (default: all)
        
    Returns:
        Dict mapping variable name to result
    """
    return ingest_nrt(variables=variables, lookback_days=1)


# =============================================================================
# Zarr Building Flows
# =============================================================================

@flow(
    name="build-zarr",
    description="Build or update Zarr store for a single variable",
    persist_result=True,
)
def build_zarr(
    variable: str,
    force_rebuild: bool = False,
    target_resolution: tuple[int, int] = (3600, 7200),
) -> dict[str, Any]:
    """
    Build or update Zarr store for a single variable.
    
    This computes and stores:
    - Time-indexed data arrays
    - Overall climatology (mean, std)
    - Monthly climatology (mean, std for each calendar month)
    - Percentiles (P10, P50, P90) overall and per-month
    - Linear trend per pixel (units/year)
    
    Args:
        variable: Variable name (sst, sla, sic, chl, kd490, rrs)
        force_rebuild: Force complete rebuild
        target_resolution: Target grid size (lat, lon)
        
    Returns:
        Result dict with status and metadata
    """
    log = get_run_logger()
    start_time = time.time()
    
    # Check if update is needed
    if not force_rebuild:
        needs_update = check_zarr_needs_update(variable)
        if not needs_update:
            log.info(f"{variable}: Zarr store is up to date, skipping")
            status = get_zarr_status(variable)
            return {
                "variable": variable,
                "status": "skipped",
                "message": "Already up to date",
                **status,
            }
    
    # Build/update the Zarr store
    result = build_zarr_store(
        variable=variable,
        target_resolution=target_resolution,
        force_rebuild=force_rebuild,
    )
    
    duration = time.time() - start_time
    
    if result:
        log.info(f"✓ {variable}: Zarr build completed in {duration:.1f}s")
        
        # Update STAC catalog with Zarr metadata
        stac_result = update_zarr_stac(variable)
        log.info(f"  STAC: {stac_result.get('status', 'unknown')}")
        
        return {
            **result,
            "duration_seconds": duration,
            "stac": stac_result,
        }
    else:
        log.error(f"✗ {variable}: Zarr build failed after {duration:.1f}s")
        return {
            "variable": variable,
            "status": "failed",
            "duration_seconds": duration,
        }


@flow(
    name="build-all-zarr",
    description="Build or update Zarr stores for all variables",
)
def build_all_zarr(
    variables: list[str] | None = None,
    force_rebuild: bool = False,
    skip_rgb: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Build or update Zarr stores for multiple variables.
    
    Args:
        variables: List of variables (default: all physical variables)
        force_rebuild: Force complete rebuild for all
        skip_rgb: Skip RGB composite (rrs) - no climatology computed
        
    Returns:
        Dict mapping variable name to result
    """
    log = get_run_logger()
    start_time = time.time()
    
    if variables is None:
        variables = list(VARIABLES.keys())
    
    # Optionally skip RGB (no climatology for color composites)
    if skip_rgb and "rrs" in variables:
        variables = [v for v in variables if v != "rrs"]
        log.info("Skipping rrs (RGB composite) - no climatology computed")
    
    results = {}
    for variable in variables:
        log.info(f"Processing {variable}...")
        result = build_zarr(
            variable=variable,
            force_rebuild=force_rebuild,
        )
        results[variable] = result
    
    total_duration = time.time() - start_time
    
    # Summary
    success = sum(1 for r in results.values() if r.get("status") == "success")
    skipped = sum(1 for r in results.values() if r.get("status") == "skipped")
    failed = len(results) - success - skipped
    
    log.info(
        f"Zarr build complete: {success} built, {skipped} skipped, "
        f"{failed} failed in {total_duration:.1f}s"
    )
    
    return results


@flow(
    name="ingest-and-build-zarr",
    description="Full pipeline: ingest latest data and rebuild Zarr stores",
)
def ingest_and_build_zarr(
    variables: list[str] | None = None,
    lookback_days: int = 3,
    force_zarr_rebuild: bool = False,
) -> dict[str, Any]:
    """
    Full pipeline: ingest new data and update Zarr stores.
    
    This is the main workflow for scheduled execution:
    1. Ingest latest NRT data (last N days)
    2. Rebuild Zarr stores with new data
    
    Args:
        variables: List of variables (default: all)
        lookback_days: Days to look back for NRT ingestion
        force_zarr_rebuild: Force complete Zarr rebuild
        
    Returns:
        Combined results from ingestion and Zarr build
    """
    log = get_run_logger()
    
    if variables is None:
        variables = list(VARIABLES.keys())
    
    # Step 1: Ingest new data
    log.info(f"Step 1: Ingesting NRT data (last {lookback_days} days)")
    ingest_results = ingest_nrt(
        variables=variables,
        lookback_days=lookback_days,
    )
    
    # Count how many new dates were ingested
    total_new = sum(r.get("processed", 0) for r in ingest_results.values())
    log.info(f"Ingested {total_new} new timesteps across all variables")
    
    # Step 2: Build/update Zarr stores
    # Only rebuild if we have new data or force flag is set
    zarr_results = {}
    if total_new > 0 or force_zarr_rebuild:
        log.info("Step 2: Building Zarr stores")
        zarr_results = build_all_zarr(
            variables=variables,
            force_rebuild=force_zarr_rebuild,
        )
    else:
        log.info("Step 2: No new data, skipping Zarr rebuild")
    
    # Cleanup
    cleanup_temp_files()
    
    return {
        "ingestion": ingest_results,
        "zarr": zarr_results,
    }


@flow(
    name="get-zarr-status-all",
    description="Get status of all Zarr stores",
)
def get_zarr_status_all(
    variables: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Get status of all Zarr stores.
    
    Args:
        variables: List of variables to check (default: all)
        
    Returns:
        Dict mapping variable name to status
    """
    if variables is None:
        variables = list(VARIABLES.keys())
    
    results = {}
    for variable in variables:
        results[variable] = get_zarr_status(variable)
    
    return results


# Export all flows
__all__ = [
    "ingest_date",
    "backfill_variable",
    "backfill_all_variables",
    "ingest_nrt",
    "ingest_latest",
    # Zarr building flows
    "build_zarr",
    "build_all_zarr",
    "ingest_and_build_zarr",
    "get_zarr_status_all",
]
