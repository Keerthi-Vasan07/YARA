"""
ARCO-3D ECV Ingestion Pipeline

Prefect 3 flows for ingesting ocean ECV data from Copernicus Marine Service.

Supported variables:
- SST (Sea Surface Temperature) - L4 OSTIA
- SIC (Sea Ice Concentration) - Arctic + Antarctic
- SLA (Sea Level Anomaly) - DUACS L4
- CHL (Chlorophyll-a) - L4 Gap-free
- Kd490 (Diffuse Attenuation) - L4 Gap-free
- Rrs (Remote Sensing Reflectance) - L3 RGB composite

Usage:
    # Single date ingestion
    python -m server.pipeline.cli ingest --variable sst --date 2024-01-15

    # Backfill date range
    python -m server.pipeline.cli backfill --variable sst --start 2022-01-01 --end 2024-12-31

    # NRT ingestion (all variables)
    python -m server.pipeline.cli nrt
"""

# Config imports (no Prefect dependency)
from server.pipeline.config import PipelineConfig, get_config, VARIABLES, get_variable_config
from server.pipeline.downloaders import get_downloader, DOWNLOADERS


def __getattr__(name: str):
    """Lazy import for Prefect-dependent modules."""
    _flow_exports = {
        "ingest_date",
        "backfill_variable",
        "backfill_all_variables",
        "ingest_nrt",
        "ingest_latest",
    }
    _task_exports = {
        "download_and_convert",
        "update_catalog",
        "generate_date_range",
        "get_missing_dates",
    }
    
    if name in _flow_exports:
        from server.pipeline.flows import (
            ingest_date,
            backfill_variable,
            backfill_all_variables,
            ingest_nrt,
            ingest_latest,
        )
        return locals()[name]
    
    if name in _task_exports:
        from server.pipeline.tasks import (
            download_and_convert,
            update_catalog,
            generate_date_range,
            get_missing_dates,
        )
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Config
    "PipelineConfig",
    "get_config",
    "get_variable_config",
    "VARIABLES",
    # Downloaders
    "get_downloader",
    "DOWNLOADERS",
    # Flows (lazy loaded)
    "ingest_date",
    "backfill_variable",
    "backfill_all_variables",
    "ingest_nrt",
    "ingest_latest",
    # Tasks (lazy loaded)
    "download_and_convert",
    "update_catalog",
    "generate_date_range",
    "get_missing_dates",
]
