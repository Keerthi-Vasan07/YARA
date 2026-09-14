"""
Pipeline Configuration

Central configuration for the ECV ingestion pipeline.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class VariableConfig:
    """Configuration for a single ECV variable."""
    name: str
    description: str = ""  # Human-readable description
    resolution: str = ""   # Spatial resolution (e.g., "0.05°", "4km")
    unit: str = ""
    dtype: str = "float32"  # Output dtype: float32, int16, uint8
    scale: float = 1.0  # Scale factor for int encoding
    nodata: float | int = float("nan")
    colormap: str = "viridis"
    # Copernicus Marine dataset IDs
    nrt_dataset_id: str | None = None
    rep_dataset_id: str | None = None
    # Variable names in source files
    data_variable: str = ""
    quality_variable: str | None = None
    # Processing options
    apply_qc_mask: bool = False
    qc_valid_values: list[int] = field(default_factory=list)
    log_scale: bool = False


# Variable configurations
VARIABLES: dict[str, VariableConfig] = {
    "sst": VariableConfig(
        name="Sea Surface Temperature",
        description="L4 gap-free SST from OSTIA",
        resolution="0.05°",
        unit="°C",
        dtype="int16",
        scale=0.01,  # 0.01°C precision
        nodata=-32768,
        colormap="thermal",
        nrt_dataset_id="METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
        rep_dataset_id="METOFFICE-GLO-SST-L4-REP-OBS-SST",
        data_variable="analysed_sst",
        quality_variable="analysis_error",
        apply_qc_mask=False,  # L4 already has land/ice masked
    ),
    "sic": VariableConfig(
        name="Sea Ice Concentration",
        description="Arctic + Antarctic SIC merged to global",
        resolution="0.1°",
        unit="%",
        dtype="uint8",
        scale=1.0,
        nodata=255,
        colormap="ice",
        # Arctic has L4, Antarctic only has L3
        nrt_dataset_id="cmems_obs-si_arc_phy_nrt_l4_P1D",
        rep_dataset_id="cmems_obs-si_arc_phy_my_l4_P1D",
        data_variable="ice_conc",
    ),
    "sla": VariableConfig(
        name="Sea Level Anomaly",
        description="DUACS L4 multi-altimeter gridded",
        resolution="0.25°",
        unit="m",
        dtype="int16",
        scale=0.001,  # 1mm precision
        nodata=-32768,
        colormap="balance",
        nrt_dataset_id="cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.25deg_P1D",
        rep_dataset_id="cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1D",
        data_variable="sla",
    ),
    "chl": VariableConfig(
        name="Chlorophyll-a Concentration",
        description="L4 gap-free multi-sensor CHL",
        resolution="4km",
        unit="mg/m³",
        dtype="float32",
        nodata=float("nan"),
        colormap="algae",
        log_scale=True,
        nrt_dataset_id="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
        rep_dataset_id="cmems_obs-oc_glo_bgc-plankton_my_l4-gapfree-multi-4km_P1D",
        data_variable="CHL",
    ),
    "kd490": VariableConfig(
        name="Diffuse Attenuation Coefficient",
        description="L4 gap-free light attenuation at 490nm",
        resolution="4km",
        unit="m⁻¹",
        dtype="float32",
        nodata=float("nan"),
        colormap="deep",
        log_scale=True,
        nrt_dataset_id="cmems_obs-oc_glo_bgc-transp_nrt_l4-gapfree-multi-4km_P1D",
        rep_dataset_id="cmems_obs-oc_glo_bgc-transp_my_l4-gapfree-multi-4km_P1D",
        data_variable="KD490",
    ),
    "rrs": VariableConfig(
        name="Remote Sensing Reflectance RGB",
        description="L3 Rrs at 443/555/670nm (has gaps)",
        resolution="4km",
        unit="sr⁻¹",
        dtype="uint8",  # RGBA output
        nodata=0,  # Alpha=0 for nodata
        colormap="rgb",  # Pre-composed RGB
        nrt_dataset_id="cmems_obs-oc_glo_bgc-reflectance_nrt_l3-multi-4km_P1D",
        rep_dataset_id="cmems_obs-oc_glo_bgc-reflectance_my_l3-multi-4km_P1D",
        data_variable="RRS443,RRS555,RRS670",  # Blue, Green, Red bands
    ),
}


@dataclass
class PipelineConfig:
    """Global pipeline configuration."""
    
    # Paths
    products_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("PRODUCTS_DIR", "server/products")
    ))
    zarr_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("ZARR_DIR", "server/zarr")
    ))
    scratch_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("SCRATCH_DIR", "/tmp/arco3d")
    ))
    
    # Aliases for tasks.py compatibility
    @property
    def cog_dir(self) -> Path:
        return self.products_dir
    
    @property
    def temp_dir(self) -> Path:
        return self.scratch_dir
    
    @property
    def catalog_file(self) -> Path:
        return self.products_dir / "catalog.json"
    
    # Database
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/arco3d"
    ))
    
    # Azure Storage (optional)
    azure_storage_account: str | None = field(default_factory=lambda: os.environ.get(
        "AZURE_STORAGE_ACCOUNT"
    ))
    azure_storage_container: str = field(default_factory=lambda: os.environ.get(
        "AZURE_STORAGE_CONTAINER", "products"
    ))
    azure_storage_sas_token: str | None = field(default_factory=lambda: os.environ.get(
        "AZURE_STORAGE_SAS_TOKEN"
    ))
    azure_upload_enabled: bool = field(default_factory=lambda: os.environ.get(
        "AZURE_UPLOAD_ENABLED", "false"
    ).lower() == "true")
    azure_zarr_container: str = field(default_factory=lambda: os.environ.get(
        "AZURE_STORAGE_ZARR_CONTAINER", "zarr"
    ))
    azure_stac_container: str = field(default_factory=lambda: os.environ.get(
        "AZURE_STORAGE_STAC_CONTAINER", "stac"
    ))
    
    # Dask configuration
    dask_scheduler: str | None = field(default_factory=lambda: os.environ.get(
        "DASK_SCHEDULER_ADDRESS"
    ))
    dask_n_workers: int = field(default_factory=lambda: int(os.environ.get(
        "DASK_N_WORKERS", "4"
    )))
    dask_threads_per_worker: int = field(default_factory=lambda: int(os.environ.get(
        "DASK_THREADS_PER_WORKER", "2"
    )))
    dask_memory_limit: str = field(default_factory=lambda: os.environ.get(
        "DASK_MEMORY_LIMIT", "6GB"
    ))
    
    # Download settings
    download_timeout: int = 900  # 15 minutes
    download_retries: int = 3
    download_retry_delay: int = 60  # seconds
    
    # Processing settings
    cog_blocksize: int = 512
    cog_compress: str = "deflate"
    overview_levels: list[int] = field(default_factory=lambda: [2, 4, 8, 16, 32])
    
    # Backfill settings
    backfill_batch_size: int = 30  # Days per batch
    backfill_concurrency: int = 4  # Parallel downloads
    
    # NRT settings
    nrt_lookback_days: int = 7  # Check last N days for gaps
    
    def get_variable_config(self, variable: str) -> VariableConfig:
        """Get configuration for a variable."""
        if variable not in VARIABLES:
            raise ValueError(f"Unknown variable: {variable}. Valid: {list(VARIABLES.keys())}")
        return VARIABLES[variable]
    
    def get_cog_path(self, variable: str, date: str) -> Path:
        """Get path for a COG file."""
        return self.products_dir / variable / f"{date}.tif"
    
    def get_zarr_path(self, variable: str) -> Path:
        """Get path for a Zarr store."""
        return self.zarr_dir / f"{variable}.zarr"
    
    def ensure_dirs(self):
        """Create required directories."""
        self.products_dir.mkdir(parents=True, exist_ok=True)
        self.zarr_dir.mkdir(parents=True, exist_ok=True)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        for var in VARIABLES:
            (self.products_dir / var).mkdir(exist_ok=True)


# Global singleton
_config: PipelineConfig | None = None


def get_config() -> PipelineConfig:
    """Get or create the global pipeline configuration."""
    global _config
    if _config is None:
        _config = PipelineConfig()
        _config.ensure_dirs()
    return _config


def get_variable_config(variable: str) -> VariableConfig:
    """Get configuration for a variable."""
    if variable not in VARIABLES:
        raise ValueError(f"Unknown variable: {variable}. Valid: {list(VARIABLES.keys())}")
    return VARIABLES[variable]
