"""
Prefect 3 Deployments for ECV Ingestion Pipeline

Creates deployments for scheduled and on-demand execution.
"""

import logging
from datetime import timedelta

from prefect.client.schemas.schedules import CronSchedule

from server.pipeline.flows import (
    ingest_nrt,
    backfill_variable,
    backfill_all_variables,
    ingest_latest,
    build_zarr,
    build_all_zarr,
    ingest_and_build_zarr,
    get_zarr_status_all,
)
from server.pipeline.config import VARIABLES

logger = logging.getLogger(__name__)


def create_deployments(
    nrt_schedule: str = "0 */6 * * *",
    full_pipeline_schedule: str = "0 4 * * *",
    zarr_weekly_schedule: str = "0 2 * * 0",
) -> None:
    """
    Create Prefect deployments.
    
    Args:
        nrt_schedule: Cron schedule for NRT ingestion (default: every 6 hours)
        full_pipeline_schedule: Cron for full pipeline (default: 4 AM daily)
        zarr_weekly_schedule: Cron for weekly Zarr rebuild (default: Sunday 2 AM)
    """
    
    # NRT deployment - runs every 6 hours
    ingest_nrt.serve(
        name="nrt-ingestion",
        description="Near Real-Time ingestion for all variables (last 3 days)",
        schedules=[CronSchedule(cron=nrt_schedule)],
        parameters={
            "variables": list(VARIABLES.keys()),
            "lookback_days": 3,
        },
        tags=["nrt", "scheduled"],
    )
    
    # Full pipeline (ingest + zarr) - runs daily at 4 AM
    ingest_and_build_zarr.serve(
        name="full-pipeline-daily",
        description="Full pipeline: NRT ingestion + Zarr rebuild with statistics",
        schedules=[CronSchedule(cron=full_pipeline_schedule)],
        parameters={
            "variables": list(VARIABLES.keys()),
            "lookback_days": 3,
            "force_zarr_rebuild": False,
        },
        tags=["nrt", "zarr", "scheduled", "full-pipeline"],
    )
    
    # Weekly Zarr full rebuild - runs Sunday 2 AM
    build_all_zarr.serve(
        name="zarr-rebuild-weekly",
        description="Weekly full Zarr rebuild with all statistics (forced)",
        schedules=[CronSchedule(cron=zarr_weekly_schedule)],
        parameters={
            "variables": list(VARIABLES.keys()),
            "force_rebuild": True,
            "skip_rgb": True,
        },
        tags=["zarr", "scheduled", "weekly"],
    )


def serve_all() -> None:
    """
    Serve all deployments (blocking).
    
    This starts the Prefect worker and serves all flows.
    """
    from prefect import serve as prefect_serve
    
    # Create deployment specs
    
    # NRT Ingestion - runs every 6 hours
    nrt_deployment = ingest_nrt.to_deployment(
        name="nrt-ingestion",
        description="Near Real-Time ingestion for all variables",
        schedules=[CronSchedule(cron="0 */6 * * *")],
        parameters={
            "variables": list(VARIABLES.keys()),
            "lookback_days": 3,
        },
        tags=["nrt", "scheduled"],
    )
    
    latest_deployment = ingest_latest.to_deployment(
        name="latest-ingestion",
        description="Ingest the most recent day",
        tags=["nrt", "manual"],
    )
    
    backfill_deployment = backfill_variable.to_deployment(
        name="backfill-variable",
        description="Backfill a single variable over a date range",
        tags=["backfill", "manual"],
    )
    
    backfill_all_deployment = backfill_all_variables.to_deployment(
        name="backfill-all",
        description="Backfill all variables over a date range",
        tags=["backfill", "manual"],
    )
    
    # Zarr Building Deployments
    
    # Main scheduled flow: Ingest + Build Zarr (daily at 4 AM)
    full_pipeline_deployment = ingest_and_build_zarr.to_deployment(
        name="full-pipeline-daily",
        description="Full pipeline: ingest NRT data and rebuild Zarr stores with statistics",
        schedules=[CronSchedule(cron="0 4 * * *")],  # 4 AM daily
        parameters={
            "variables": list(VARIABLES.keys()),
            "lookback_days": 3,
            "force_zarr_rebuild": False,
        },
        tags=["nrt", "zarr", "scheduled", "full-pipeline"],
    )
    
    # Weekly Zarr rebuild with forced recalculation (Sundays at 2 AM)
    zarr_weekly_deployment = build_all_zarr.to_deployment(
        name="zarr-rebuild-weekly",
        description="Weekly full Zarr rebuild with all statistics (forced)",
        schedules=[CronSchedule(cron="0 2 * * 0")],  # Sunday 2 AM
        parameters={
            "variables": list(VARIABLES.keys()),
            "force_rebuild": True,
            "skip_rgb": True,
        },
        tags=["zarr", "scheduled", "weekly"],
    )
    
    # Manual Zarr build for single variable
    zarr_single_deployment = build_zarr.to_deployment(
        name="build-zarr-variable",
        description="Build/update Zarr store for a single variable with climatology and stats",
        tags=["zarr", "manual"],
    )
    
    # Manual Zarr status check
    zarr_status_deployment = get_zarr_status_all.to_deployment(
        name="zarr-status",
        description="Check status of all Zarr stores",
        tags=["zarr", "status", "manual"],
    )
    
    # Serve all deployments
    prefect_serve(
        # Ingestion deployments
        nrt_deployment,
        latest_deployment,
        backfill_deployment,
        backfill_all_deployment,
        # Zarr building deployments
        full_pipeline_deployment,
        zarr_weekly_deployment,
        zarr_single_deployment,
        zarr_status_deployment,
    )


if __name__ == "__main__":
    """Run as: python -m server.pipeline.deployments"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage Prefect deployments")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start serving deployments (blocking)",
    )
    parser.add_argument(
        "--schedule",
        default="0 */6 * * *",
        help="NRT cron schedule (default: every 6 hours)",
    )
    
    args = parser.parse_args()
    
    if args.serve:
        serve_all()
    else:
        create_deployments(nrt_schedule=args.schedule)
