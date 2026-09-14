"""Application configuration."""

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECV_", env_file=".env", extra="ignore")
    """Application settings loaded from environment."""
    
    # ARCO ERA5 Zarr store path
    zarr_path: str = "gs://gcp-public-data-arco-era5/co/single-level-reanalysis.zarr-v2"
    
    # Default bounding box: North Atlantic region
    default_lon_min: float = -32.0
    default_lon_max: float = 42.0
    default_lat_min: float = 50.0
    default_lat_max: float = 84.0
    
    # Sea-ice masking threshold
    ice_threshold: float = 0.15
    
    # CORS origins for frontend
    cors_origins: list[str] = [
        "https://keerthivasan.qzz.io",
        "https://www.keerthivasan.qzz.io",
        "https://yara-1-2tcg.onrender.com",
        "https://yara-h7wa.onrender.com",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5847",
        "http://127.0.0.1:5847",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @property
    def get_effective_cors_origins(self) -> list[str]:
        origins = list(self.cors_origins)
        env_origins = os.environ.get("CORS_ORIGINS") or os.environ.get("ECV_CORS_ORIGINS")
        if env_origins:
            raw = env_origins.strip()
            if raw.startswith("[") and raw.endswith("]"):
                try:
                    import json
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        for item in parsed:
                            item_str = str(item).strip().strip('"').strip("'").rstrip("/")
                            if item_str and item_str not in origins:
                                origins.append(item_str)
                except Exception:
                    pass
            else:
                for item in raw.split(","):
                    item_str = item.strip().strip('"').strip("'").rstrip("/")
                    if item_str and item_str not in origins:
                        origins.append(item_str)
        cleaned = []
        for o in origins:
            clean = str(o).strip().rstrip("/")
            if clean and clean not in cleaned:
                cleaned.append(clean)
        return cleaned

    
    # ==========================================================================
    # Data Storage Configuration
    # ==========================================================================
    
    # Storage mode: "local", "azure", "s3", or "gcs"
    products_source: Literal["local", "azure", "s3", "gcs"] = "local"
    
    # Local storage (when products_source="local")
    products_dir: str = "server/products"
    
    # Azure Blob Storage (when products_source="azure")
    azure_storage_account: str | None = None
    azure_storage_container: str = "products"
    azure_storage_sas_token: str | None = None
    azure_zarr_container: str = "zarr"  # Container for Zarr stores
    
    # AWS S3 (when products_source="s3")
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_prefix: str = ""  # Optional prefix within bucket
    # Authentication: uses AWS credentials from environment/IAM role
    # Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, or use IAM role
    s3_requester_pays: bool = False  # For requester-pays buckets
    
    # Google Cloud Storage (when products_source="gcs")
    gcs_bucket: str | None = None
    gcs_prefix: str = ""  # Optional prefix within bucket
    # Authentication: uses GOOGLE_APPLICATION_CREDENTIALS or default credentials
    
    # STAC Catalog URL (for remote catalog)
    # If set, the catalog will be fetched from this URL instead of local filesystem
    # Example: https://arco3dstore.blob.core.windows.net/stac/catalog.json
    # Example: https://my-bucket.s3.us-east-1.amazonaws.com/stac/catalog.json
    stac_catalog_url: str | None = None
    
    # Azure STAC container (for uploading STAC catalog)
    azure_stac_container: str = "stac"
    
    # COG path pattern within storage (supports {variable}, {date}, {year}, {month}, {day})
    cog_path_pattern: str = "{variable}/{date}.tif"
    
    def get_stac_base_url(self) -> str | None:
        """Get the base URL for STAC catalog (directory containing catalog.json) with SAS token."""
        base_url = None
        
        if self.stac_catalog_url:
            # Remove catalog.json from the end if present
            url = self.stac_catalog_url
            if url.endswith("/catalog.json"):
                base_url = url[:-13]
            elif url.endswith("catalog.json"):
                base_url = url[:-12]
            else:
                base_url = url
        elif self.products_source == "azure" and self.azure_storage_account:
            # Build from Azure settings
            base_url = f"https://{self.azure_storage_account}.blob.core.windows.net/{self.azure_stac_container}"
        
        if not base_url:
            return None
        
        # Append SAS token if URL is Azure blob storage and token is available
        if self.azure_storage_sas_token and "blob.core.windows.net" in base_url and "?" not in base_url:
            return f"{base_url}?{self.azure_storage_sas_token.lstrip('?')}"
        
        return base_url
    
    def get_cog_path(self, variable: str, date: str) -> str:
        """
        Get path/URL to COG file for tile rendering.
        
        Returns:
            - Local path for products_source="local"
            - GDAL vsicurl URL for products_source="azure"
            - GDAL vsis3 URL for products_source="s3"
        """
        # Parse date components
        year, month, day = date.split("-") if "-" in date else (date[:4], date[4:6], date[6:8])
        
        # Build relative path from pattern
        rel_path = self.cog_path_pattern.format(
            variable=variable,
            date=date,
            year=year,
            month=month,
            day=day
        )
        
        if self.products_source == "local":
            return str(Path(self.products_dir) / rel_path)
        
        elif self.products_source == "azure":
            if not self.azure_storage_account:
                raise ValueError("AZURE_STORAGE_ACCOUNT required when products_source=azure")
            
            # Configure GDAL Azure credentials (set once)
            if "AZURE_STORAGE_ACCOUNT" not in os.environ:
                os.environ["AZURE_STORAGE_ACCOUNT"] = self.azure_storage_account
            if self.azure_storage_sas_token and "AZURE_STORAGE_SAS_TOKEN" not in os.environ:
                os.environ["AZURE_STORAGE_SAS_TOKEN"] = self.azure_storage_sas_token
            
            # Use /vsiaz/ — GDAL's native Azure blob driver.
            # Much faster than /vsicurl/ because it reuses connections,
            # supports the Azure SDK, and integrates with GDAL's VSI cache.
            return f"/vsiaz/{self.azure_storage_container}/{rel_path}"
        
        elif self.products_source == "s3":
            if not self.s3_bucket:
                raise ValueError("S3_BUCKET required when products_source=s3")
            
            # Build S3 path with optional prefix
            s3_key = f"{self.s3_prefix}/{rel_path}".lstrip("/") if self.s3_prefix else rel_path
            
            # Use GDAL's vsis3 for efficient S3 access
            # Reads only needed byte ranges for COG tiles
            # Authentication via AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or IAM role
            return f"/vsis3/{self.s3_bucket}/{s3_key}"
        
        elif self.products_source == "gcs":
            if not self.gcs_bucket:
                raise ValueError("GCS_BUCKET required when products_source=gcs")
            
            # Build GCS path with optional prefix
            gcs_key = f"{self.gcs_prefix}/{rel_path}".lstrip("/") if self.gcs_prefix else rel_path
            
            # Use GDAL's vsigs for efficient GCS access
            # Reads only needed byte ranges for COG tiles
            # Authentication via GOOGLE_APPLICATION_CREDENTIALS or default credentials
            return f"/vsigs/{self.gcs_bucket}/{gcs_key}"
        
        raise ValueError(f"Unknown products_source: {self.products_source}")
    
    def get_zarr_store(self, variable: str):
        """
        Open a Zarr store for a variable.
        
        Returns:
            - zarr.Group from local filesystem or Azure blob storage
            - None if store doesn't exist
        """
        import zarr
        
        if self.products_source == "local":
            # Local Zarr store
            local_path = Path(__file__).parent / "zarr" / f"{variable}.zarr"
            if local_path.exists():
                return zarr.open_group(str(local_path), mode='r')
            return None
        
        elif self.products_source == "azure":
            if not self.azure_storage_account:
                return None
            
            try:
                import adlfs
                import fsspec
            except ImportError:
                raise ImportError("adlfs required for Azure Zarr: pip install adlfs")
            
            # Build Azure storage options
            storage_options = {
                "account_name": self.azure_storage_account,
            }
            if self.azure_storage_sas_token:
                storage_options["sas_token"] = self.azure_storage_sas_token
            
            # Open Zarr store from Azure using FsspecStore
            store_path = f"az://{self.azure_zarr_container}/{variable}.zarr"
            try:
                fs = fsspec.filesystem("az", **storage_options)
                store = zarr.storage.FsspecStore(fs=fs, path=f"{self.azure_zarr_container}/{variable}.zarr")
                return zarr.open_group(store, mode='r')
            except Exception:
                return None
        
        elif self.products_source == "s3":
            if not self.s3_bucket:
                return None
            
            try:
                import s3fs
                import fsspec
            except ImportError:
                raise ImportError("s3fs required for S3 Zarr: pip install s3fs")
            
            zarr_key = f"{self.s3_prefix}/{variable}.zarr".lstrip("/")
            try:
                fs = fsspec.filesystem("s3")
                store = zarr.storage.FsspecStore(fs=fs, path=f"{self.s3_bucket}/{zarr_key}")
                return zarr.open_group(store, mode='r')
            except Exception:
                return None
        
        elif self.products_source == "gcs":
            if not self.gcs_bucket:
                return None
            
            try:
                import gcsfs
                import fsspec
            except ImportError:
                raise ImportError("gcsfs required for GCS Zarr: pip install gcsfs")
            
            zarr_key = f"{self.gcs_prefix}/{variable}.zarr".lstrip("/")
            try:
                fs = fsspec.filesystem("gcs")
                store = zarr.storage.FsspecStore(fs=fs, path=f"{self.gcs_bucket}/{zarr_key}")
                return zarr.open_group(store, mode='r')
            except Exception:
                return None
        
        return None
    
    def list_zarr_variables(self) -> list[str]:
        """
        List available Zarr store variables.
        
        Returns list of variable names (e.g., ['sst', 'sic', 'sla']).
        """
        if self.products_source == "local":
            zarr_dir = Path(__file__).parent / "zarr"
            if not zarr_dir.exists():
                return []
            return sorted([p.stem for p in zarr_dir.glob("*.zarr") if p.is_dir()])
        
        elif self.products_source == "azure":
            try:
                from azure.storage.blob import ContainerClient
            except ImportError:
                return []
            
            if not self.azure_storage_account:
                return []
            
            try:
                account_url = f"https://{self.azure_storage_account}.blob.core.windows.net"
                if self.azure_storage_sas_token:
                    container_url = f"{account_url}/{self.azure_zarr_container}?{self.azure_storage_sas_token.lstrip('?')}"
                    container = ContainerClient.from_container_url(container_url)
                else:
                    container = ContainerClient(account_url, self.azure_zarr_container)
                
                # Find .zarr directories by looking for .zgroup files
                variables = set()
                for blob in container.list_blobs():
                    parts = blob.name.split("/")
                    if len(parts) >= 2 and parts[0].endswith(".zarr"):
                        variables.add(parts[0].replace(".zarr", ""))
                
                return sorted(variables)
            except Exception:
                return []
        
        return []

    def list_available_dates_from_stac(self, variable: str) -> list[str] | None:
        """
        Fetch available dates from remote STAC catalog.
        
        Returns list of dates or None if STAC is not configured or fetch fails.
        This method is synchronous and caches results.
        """
        stac_base = self.get_stac_base_url()
        if not stac_base:
            return None
        
        try:
            import httpx
        except ImportError:
            return None
        
        # Construct collection URL
        collection_url = f"{stac_base}/collections/{variable}.json"
        
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(collection_url)
                if resp.status_code != 200:
                    return None
                
                collection = resp.json()
                
                # Extract dates from summaries
                summaries = collection.get("summaries", {})
                
                # Try available_dates array first (best option)
                available_dates = summaries.get("available_dates", [])
                if available_dates:
                    return sorted(available_dates)
                
                # Try item links as fallback
                dates = []
                for link in collection.get("links", []):
                    if link.get("rel") == "item":
                        # Extract date from title or href
                        title = link.get("title", "")
                        if title and "-" in title:
                            dates.append(title)
                        else:
                            # Try href: ../items/sst/2024-01-15.json
                            href = link.get("href", "")
                            if href.endswith(".json"):
                                date = href.split("/")[-1].replace(".json", "")
                                if "-" in date:
                                    dates.append(date)
                
                if dates:
                    return sorted(dates)
                
                # Fallback: return None, caller should use other method
                return None
                
        except Exception:
            return None

    def list_available_dates(self, variable: str) -> list[str]:
        """
        List available dates for a variable.
        
        Tries STAC catalog first (fast), then falls back to storage listing.
        """
        # Try STAC catalog first (works with public access)
        stac_dates = self.list_available_dates_from_stac(variable)
        if stac_dates:
            return stac_dates
        
        if self.products_source == "local":
            var_dir = Path(self.products_dir) / variable
            if not var_dir.exists():
                return []
            return sorted([f.stem for f in var_dir.glob("*.tif")])
        
        elif self.products_source == "azure":
            # Import here to make azure-storage-blob optional
            try:
                from azure.storage.blob import ContainerClient
            except ImportError:
                raise ImportError("azure-storage-blob required: pip install azure-storage-blob")
            
            if not self.azure_storage_account:
                return []
            
            account_url = f"https://{self.azure_storage_account}.blob.core.windows.net"
            
            if self.azure_storage_sas_token:
                container_url = f"{account_url}/{self.azure_storage_container}?{self.azure_storage_sas_token.lstrip('?')}"
                container = ContainerClient.from_container_url(container_url)
            else:
                # Try anonymous access
                container = ContainerClient(account_url, self.azure_storage_container)
            
            prefix = f"{variable}/"
            dates = []
            for blob in container.list_blobs(name_starts_with=prefix):
                if blob.name.endswith(".tif"):
                    # Extract date from path like "sst/2024-01-15.tif"
                    filename = blob.name.split("/")[-1]
                    dates.append(filename.replace(".tif", ""))
            
            return sorted(dates)
        
        elif self.products_source == "s3":
            # Import here to make boto3 optional
            try:
                import boto3
            except ImportError:
                raise ImportError("boto3 required for S3: pip install boto3")
            
            if not self.s3_bucket:
                return []
            
            s3 = boto3.client("s3", region_name=self.s3_region)
            
            # Build prefix for listing
            prefix = f"{self.s3_prefix}/{variable}/".lstrip("/") if self.s3_prefix else f"{variable}/"
            
            dates = []
            paginator = s3.get_paginator("list_objects_v2")
            
            extra_args = {"Bucket": self.s3_bucket, "Prefix": prefix}
            if self.s3_requester_pays:
                extra_args["RequestPayer"] = "requester"
            
            for page in paginator.paginate(**extra_args):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".tif"):
                        filename = key.split("/")[-1]
                        dates.append(filename.replace(".tif", ""))
            
            return sorted(dates)
        
        elif self.products_source == "gcs":
            # Import here to make google-cloud-storage optional
            try:
                from google.cloud import storage
            except ImportError:
                raise ImportError("google-cloud-storage required for GCS: pip install google-cloud-storage")
            
            if not self.gcs_bucket:
                return []
            
            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket)
            
            # Build prefix for listing
            prefix = f"{self.gcs_prefix}/{variable}/".lstrip("/") if self.gcs_prefix else f"{variable}/"
            
            dates = []
            for blob in bucket.list_blobs(prefix=prefix):
                if blob.name.endswith(".tif"):
                    filename = blob.name.split("/")[-1]
                    dates.append(filename.replace(".tif", ""))
            
            return sorted(dates)
        
        return []


settings = Settings()
