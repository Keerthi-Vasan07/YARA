"""
CLI for ECV Ingestion Pipeline

Usage:
    python -m server.pipeline.cli backfill --variable sst --start 2022-01-01 --end 2024-12-31
    python -m server.pipeline.cli nrt --variables sst,sic,sla
    python -m server.pipeline.cli zarr --variable sst [--force]
    python -m server.pipeline.cli zarr-all [--force]
    python -m server.pipeline.cli zarr-status
    python -m server.pipeline.cli full-pipeline [--lookback 3]
    python -m server.pipeline.cli stac-rebuild
    python -m server.pipeline.cli stac-sync
    python -m server.pipeline.cli deploy --schedule "0 */6 * * *"
"""

import argparse
import logging
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def cmd_backfill(args):
    """Run backfill for a variable."""
    from server.pipeline.flows import backfill_variable, backfill_all_variables
    
    if args.variable == "all":
        variables = args.variables.split(",") if args.variables else None
        result = backfill_all_variables(
            start_date=args.start,
            end_date=args.end,
            variables=variables,
            max_concurrent=args.concurrent,
        )
        for var, stats in result.items():
            logger.info(f"{var}: {stats['processed']} processed, {stats['failed']} failed")
    else:
        result = backfill_variable(
            variable=args.variable,
            start_date=args.start,
            end_date=args.end,
            max_concurrent=args.concurrent,
            skip_existing=not args.force,
            batch_size=args.batch_size,
            use_dask=args.use_dask,
        )
        logger.info(f"Result: {result}")


def cmd_nrt(args):
    """Run NRT ingestion."""
    from server.pipeline.flows import ingest_nrt
    
    variables = args.variables.split(",") if args.variables else None
    result = ingest_nrt(
        variables=variables,
        lookback_days=args.lookback,
    )
    for var, stats in result.items():
        logger.info(f"{var}: {stats['processed']} processed, {stats['failed']} failed")


def cmd_ingest(args):
    """Ingest a single date."""
    from server.pipeline.flows import ingest_date
    
    result = ingest_date(
        variable=args.variable,
        date_str=args.date,
        force=args.force,
    )
    logger.info(f"Result: {result}")


def cmd_deploy(args):
    """Create Prefect deployments."""
    from server.pipeline.deployments import create_deployments
    
    create_deployments(
        nrt_schedule=args.schedule,
    )
    logger.info("Deployments created")


def cmd_zarr(args):
    """Build Zarr store for a variable."""
    from server.pipeline.flows import build_zarr
    
    result = build_zarr(
        variable=args.variable,
        force_rebuild=args.force,
    )
    logger.info(f"Result: {result}")


def cmd_zarr_all(args):
    """Build Zarr stores for all variables."""
    from server.pipeline.flows import build_all_zarr
    
    variables = args.variables.split(",") if args.variables else None
    result = build_all_zarr(
        variables=variables,
        force_rebuild=args.force,
        skip_rgb=not args.include_rgb,
    )
    for var, stats in result.items():
        status = stats.get("status", "unknown")
        n_times = stats.get("n_times", 0)
        logger.info(f"{var}: {status} ({n_times} timesteps)")


def cmd_zarr_status(args):
    """Show status of all Zarr stores."""
    from server.pipeline.flows import get_zarr_status_all
    
    variables = args.variables.split(",") if args.variables else None
    result = get_zarr_status_all(variables=variables)
    
    print("\nZarr Store Status:")
    print("-" * 80)
    
    for var, status in result.items():
        if not status.get("exists"):
            print(f"  {var}: NOT FOUND")
            continue
        
        n_times = status.get("n_times", 0)
        date_range = status.get("date_range", [None, None])
        has_clim = "✓" if status.get("has_climatology") else "✗"
        has_monthly = "✓" if status.get("has_monthly_climatology") else "✗"
        has_perc = "✓" if status.get("has_percentiles") else "✗"
        has_trend = "✓" if status.get("has_trend") else "✗"
        
        range_str = f"{date_range[0]} to {date_range[1]}" if date_range[0] else "N/A"
        
        print(f"  {var}:")
        print(f"    Timesteps: {n_times}")
        print(f"    Date range: {range_str}")
        print(f"    Statistics: climatology={has_clim} monthly={has_monthly} percentiles={has_perc} trend={has_trend}")


def cmd_full_pipeline(args):
    """Run full pipeline: ingest + Zarr rebuild."""
    from server.pipeline.flows import ingest_and_build_zarr
    
    variables = args.variables.split(",") if args.variables else None
    result = ingest_and_build_zarr(
        variables=variables,
        lookback_days=args.lookback,
        force_zarr_rebuild=args.force_zarr,
    )
    
    # Print ingestion summary
    ingest_results = result.get("ingestion", {})
    total_new = sum(r.get("processed", 0) for r in ingest_results.values())
    logger.info(f"Ingestion: {total_new} new timesteps")
    
    # Print Zarr summary
    zarr_results = result.get("zarr", {})
    if zarr_results:
        success = sum(1 for r in zarr_results.values() if r.get("status") == "success")
        logger.info(f"Zarr: {success} rebuilt")


def cmd_list_catalog(args):
    """List catalog contents."""
    import json
    from server.pipeline.config import get_config
    
    config = get_config()
    catalog_path = config.catalog_file
    
    if not catalog_path.exists():
        logger.info("No catalog found")
        return
    
    with open(catalog_path) as f:
        catalog = json.load(f)
    
    print(f"\nCatalog: {catalog_path}")
    print(f"Created: {catalog.get('created', 'unknown')}")
    print(f"Updated: {catalog.get('updated', 'unknown')}")
    print()
    
    for var, data in catalog.get("variables", {}).items():
        count = data.get("count", 0)
        entries = data.get("entries", {})
        if entries:
            dates = sorted(entries.keys())
            print(f"  {var}: {count} entries ({dates[0]} to {dates[-1]})")
        else:
            print(f"  {var}: {count} entries")


def cmd_stac_rebuild(args):
    """Rebuild STAC catalog from filesystem."""
    from server.pipeline.tasks import build_stac_catalog
    
    result = build_stac_catalog()
    
    if result.get("status") == "success":
        print(f"\nSTAC catalog rebuilt: {result.get('n_collections', 0)} collections")
        print(f"Collections: {', '.join(result.get('collections', []))}")
        
        azure_result = result.get("azure", {})
        if azure_result.get("status") == "success":
            print(f"Azure: {azure_result.get('uploaded', 0)} files synced to {azure_result.get('container')}")
        elif azure_result.get("status") == "skipped":
            print(f"Azure: skipped ({azure_result.get('reason', 'not configured')})")
    else:
        print(f"STAC rebuild failed: {result.get('error', 'unknown')}")


def cmd_stac_build_azure(args):
    """Build STAC catalog from Azure blob storage and upload to stac container."""
    from server.pipeline.config import get_config
    from server.stac.catalog import build_catalog_from_azure, upload_catalog_to_azure
    
    config = get_config()
    
    # Validate Azure configuration
    if not config.azure_storage_account:
        print("Error: AZURE_STORAGE_ACCOUNT not configured")
        return
    if not config.azure_storage_sas_token:
        print("Error: AZURE_STORAGE_SAS_TOKEN not configured")
        return
    
    print(f"Building STAC catalog from Azure: {config.azure_storage_account}/{config.azure_storage_container}")
    
    # Build catalog from Azure blob listing
    catalog_data = build_catalog_from_azure(
        storage_account=config.azure_storage_account,
        products_container=config.azure_storage_container,
        sas_token=config.azure_storage_sas_token,
    )
    
    n_collections = len(catalog_data.get("collections", {}))
    print(f"\nBuilt catalog with {n_collections} collections:")
    for var, coll in catalog_data.get("collections", {}).items():
        n_timesteps = coll.get("summaries", {}).get("n_timesteps", 0)
        print(f"  {var}: {n_timesteps} timesteps")
    
    # Upload to stac container
    print(f"\nUploading to: {config.azure_storage_account}/{config.azure_stac_container}")
    result = upload_catalog_to_azure(
        catalog_data=catalog_data,
        storage_account=config.azure_storage_account,
        stac_container=config.azure_stac_container,
        sas_token=config.azure_storage_sas_token,
    )
    
    print(f"Uploaded {result.get('uploaded', 0)} files")
    print("\nSTAC catalog URL:")
    print(f"  https://{config.azure_storage_account}.blob.core.windows.net/{config.azure_stac_container}/catalog.json")


def cmd_stac_sync(args):
    """Sync STAC catalog to Azure Blob Storage."""
    from server.pipeline.tasks import upload_stac_to_azure
    
    result = upload_stac_to_azure(sync_all=True)
    
    status = result.get("status", "unknown")
    if status == "success":
        print(f"\nSTAC synced to Azure:")
        print(f"  Container: {result.get('container')}")
        print(f"  Files uploaded: {result.get('uploaded', 0)}")
    elif status == "partial":
        print(f"\nSTAC partially synced to Azure:")
        print(f"  Uploaded: {result.get('uploaded', 0)}")
        print(f"  Failed: {result.get('failed', 0)}")
    elif status == "skipped":
        print(f"\nSTAC sync skipped: {result.get('reason', 'not configured')}")
        print("Set AZURE_UPLOAD_ENABLED=true and configure Azure storage.")
    else:
        print(f"\nSTAC sync failed: {result.get('error', 'unknown')}")


def cmd_status(args):
    """Show pipeline status."""
    from server.pipeline.config import get_config, VARIABLES
    
    config = get_config()
    
    print("\nPipeline Configuration:")
    print(f"  COG directory: {config.cog_dir}")
    print(f"  Catalog file: {config.catalog_file}")
    print(f"  Temp directory: {config.temp_dir}")
    print()
    
    print("Variables:")
    for name, var_config in VARIABLES.items():
        print(f"  {name}:")
        print(f"    Description: {var_config.description}")
        print(f"    Resolution: {var_config.resolution}")
        if var_config.nrt_dataset_id:
            print(f"    NRT: {var_config.nrt_dataset_id}")
        if var_config.rep_dataset_id:
            print(f"    REP: {var_config.rep_dataset_id}")


def main():
    parser = argparse.ArgumentParser(
        description="ECV Ingestion Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Backfill command
    backfill = subparsers.add_parser("backfill", help="Backfill historical data")
    backfill.add_argument(
        "--variable", "-v",
        required=True,
        help="Variable to backfill (sst, sic, sla, chl, kd490, rrs, or 'all')",
    )
    backfill.add_argument(
        "--variables",
        help="Comma-separated list of variables (when --variable=all)",
    )
    backfill.add_argument(
        "--start", "-s",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    backfill.add_argument(
        "--end", "-e",
        default=date.today().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD, default: today)",
    )
    backfill.add_argument(
        "--concurrent", "-c",
        type=int,
        default=4,
        help="Max concurrent downloads (default: 4)",
    )
    backfill.add_argument(
        "--batch-size", "-b",
        type=int,
        default=30,
        help="Batch size for catalog updates (default: 30)",
    )
    backfill.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-download of existing data",
    )
    backfill.add_argument(
        "--use-dask",
        action="store_true",
        help="Use Dask cluster for distributed processing",
    )
    backfill.set_defaults(func=cmd_backfill)
    
    # NRT command
    nrt = subparsers.add_parser("nrt", help="Run Near Real-Time ingestion")
    nrt.add_argument(
        "--variables",
        help="Comma-separated list of variables (default: all)",
    )
    nrt.add_argument(
        "--lookback", "-l",
        type=int,
        default=3,
        help="Days to look back (default: 3)",
    )
    nrt.set_defaults(func=cmd_nrt)
    
    # Ingest command
    ingest = subparsers.add_parser("ingest", help="Ingest a single date")
    ingest.add_argument(
        "--variable", "-v",
        required=True,
        help="Variable name",
    )
    ingest.add_argument(
        "--date", "-d",
        required=True,
        help="Date (YYYY-MM-DD)",
    )
    ingest.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-download",
    )
    ingest.set_defaults(func=cmd_ingest)
    
    # Deploy command
    deploy = subparsers.add_parser("deploy", help="Create Prefect deployments")
    deploy.add_argument(
        "--schedule",
        default="0 */6 * * *",
        help="Cron schedule for NRT (default: every 6 hours)",
    )
    deploy.set_defaults(func=cmd_deploy)
    
    # Zarr build (single variable) command
    zarr = subparsers.add_parser("zarr", help="Build Zarr store for a variable")
    zarr.add_argument(
        "--variable", "-v",
        required=True,
        help="Variable to build (sst, sic, sla, chl, kd490, rrs)",
    )
    zarr.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force complete rebuild",
    )
    zarr.set_defaults(func=cmd_zarr)
    
    # Zarr build all command
    zarr_all = subparsers.add_parser("zarr-all", help="Build Zarr stores for all variables")
    zarr_all.add_argument(
        "--variables",
        help="Comma-separated list of variables (default: all)",
    )
    zarr_all.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force complete rebuild",
    )
    zarr_all.add_argument(
        "--include-rgb",
        action="store_true",
        help="Include rrs (RGB composite) which has no climatology",
    )
    zarr_all.set_defaults(func=cmd_zarr_all)
    
    # Zarr status command
    zarr_status = subparsers.add_parser("zarr-status", help="Show Zarr store status")
    zarr_status.add_argument(
        "--variables",
        help="Comma-separated list of variables (default: all)",
    )
    zarr_status.set_defaults(func=cmd_zarr_status)
    
    # Full pipeline command
    full_pipeline = subparsers.add_parser("full-pipeline", help="Run full pipeline: ingest + Zarr rebuild")
    full_pipeline.add_argument(
        "--variables",
        help="Comma-separated list of variables (default: all)",
    )
    full_pipeline.add_argument(
        "--lookback", "-l",
        type=int,
        default=3,
        help="Days to look back for NRT (default: 3)",
    )
    full_pipeline.add_argument(
        "--force-zarr",
        action="store_true",
        help="Force Zarr rebuild even if no new data",
    )
    full_pipeline.set_defaults(func=cmd_full_pipeline)
    
    # Catalog command
    catalog = subparsers.add_parser("catalog", help="Show catalog contents")
    catalog.set_defaults(func=cmd_list_catalog)
    
    # STAC rebuild command
    stac_rebuild = subparsers.add_parser("stac-rebuild", help="Rebuild STAC catalog from filesystem")
    stac_rebuild.set_defaults(func=cmd_stac_rebuild)
    
    # STAC sync command
    stac_sync = subparsers.add_parser("stac-sync", help="Sync STAC catalog to Azure Blob Storage")
    stac_sync.set_defaults(func=cmd_stac_sync)
    
    # STAC build from Azure command
    stac_build_azure = subparsers.add_parser(
        "stac-build-azure", 
        help="Build STAC catalog from Azure blob storage and upload to stac container"
    )
    stac_build_azure.set_defaults(func=cmd_stac_build_azure)
    
    # Status command
    status = subparsers.add_parser("status", help="Show pipeline status")
    status.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
