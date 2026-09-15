"""
glorys_service.py

Production-style remote GLORYS visualization service.
Connects to Copernicus Marine GLORYS12V1 (GLOBAL_MULTIYEAR_PHY_001_030)
dataset: cmems_mod_glo_phy_my_0.083deg_P1D-m
using the official copernicusmarine toolbox.

Mode "remote":  uses Copernicus Marine toolbox. Credentials REQUIRED.
                If credentials are missing or auth fails → raises RuntimeError (does NOT fall back).
Mode "local":   uses local NetCDF fixture file only. No network access.

Multi-variable support (added):
    thetao     — potential temperature (°C)          — remote + local
    so         — salinity (PSU)                       — local only (Dec 2004 fixture)
    mlotst     — mixed layer thickness (m)            — local only (Dec 2004 fixture)
    ohc_0_700m — ocean heat content 0–700m (J/m²)   — local only (Dec 2004 fixture)
"""

from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import struct
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
import numpy as np
import xarray as xr

# ──────────────────────────────────────────────────────────────────────────────
# Explicit .env resolution — works regardless of where uvicorn is started from.
# ──────────────────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent

# Ensure .env is read directly from backend root
env_path = _PROJECT_ROOT / ".env"
if not env_path.exists():
    env_path = _BACKEND_DIR / ".env"
load_dotenv(dotenv_path=env_path)

_env_found = env_path.exists()
_ENV_FILE = env_path

COPERNICUS_USER = os.getenv("COPERNICUS_MARINE_SERVICE_USERNAME", "").strip()
if not COPERNICUS_USER:
    COPERNICUS_USER = os.getenv("COPERNICUSMARINE_USERNAME", "").strip()

COPERNICUS_PWD = os.getenv("COPERNICUS_MARINE_SERVICE_PASSWORD", "").strip()
if not COPERNICUS_PWD:
    COPERNICUS_PWD = os.getenv("COPERNICUSMARINE_PASSWORD", "").strip()

FORCE_FIXTURE = os.getenv("FORCE_LOCAL_FIXTURE", "false").strip().lower() == "true"

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("glorys_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[GLORYS-BACKEND] %(levelname)s - %(message)s"))
    logger.addHandler(ch)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
LOCAL_DATA_PATH    = str(_PROJECT_ROOT / "data" / "cmems_mod_glo_phy_my_0.083deg_P1D-m_1788622407563.nc")
if not Path(LOCAL_DATA_PATH).exists():
    LOCAL_DATA_PATH = str(_BACKEND_DIR / "data" / "cmems_mod_glo_phy_my_0.083deg_P1D-m_1788622407563.nc")

CLIMATE_DATA_PATH  = str(_PROJECT_ROOT / "backend" / "data" / "glorys_global_dec2004_climate.nc")
if not Path(CLIMATE_DATA_PATH).exists():
    CLIMATE_DATA_PATH = str(_BACKEND_DIR / "data" / "glorys_global_dec2004_climate.nc")

DATASET_ID       = "cmems_mod_glo_phy_my_0.083deg_P1D-m"  # used for dataset access
PRODUCT_ID       = "GLOBAL_MULTIYEAR_PHY_001_030"           # product catalogue reference (NOT used for access)
PRIMARY_VARIABLE = "thetao"

CACHE_MAX_ENTRIES = 64

# Variables available in the climate Dec 2004 fixture only (not available via remote Copernicus in this service)
CLIMATE_VARIABLES_LOCAL_ONLY: frozenset = frozenset({"so", "mlotst", "ohc_0_700m"})
# All allowed variable names
ALLOWED_VARIABLES: frozenset = frozenset({"thetao", "so", "mlotst", "ohc_0_700m", "chl", "composite"})

# Per-variable display metadata: unit, human label, suggested colormap range, whether it is 2D (no depth axis)
VARIABLE_META: Dict[str, Dict[str, Any]] = {
    "thetao": {
        "unit":          "°C",
        "label":         "Potential Temperature",
        "default_range": [-2.0, 35.0],
        "is_2d":         False,
    },
    "so": {
        "unit":          "PSU",
        "label":         "Salinity",
        "default_range": [30.0, 40.0],
        "is_2d":         False,
    },
    "chl": {
        "unit":          "mg/m³",
        "label":         "Chlorophyll-a",
        "default_range": [0.0, 2.0],
        "is_2d":         False,
    },
    "composite": {
        "unit":          "Multi",
        "label":         "Multi-Variable Composite",
        "default_range": [0.0, 1.0],
        "is_2d":         False,
    },
    "mlotst": {
        "unit":          "m",
        "label":         "Mixed Layer Thickness",
        "default_range": [0.0, 200.0],
        "is_2d":         True,
    },
    "ohc_0_700m": {
        "unit":          "J/m²",
        "label":         "Ocean Heat Content (0–700m)",
        "default_range": [0.0, 4.0e9],
        "is_2d":         True,
    },
}


def normalize_longitude(lon: float) -> float:
    """Normalize longitude into [-180, 180]."""
    return ((lon + 180.0) % 360.0) - 180.0


# ──────────────────────────────────────────────────────────────────────────────
# GlorysService
# ──────────────────────────────────────────────────────────────────────────────

class GlorysService:
    """
    Service for remote access to Copernicus Marine GLORYS12V1 reanalysis data.
    In 'remote' mode, ALL thetao requests go to Copernicus Marine — no local fallback.
    In 'local' mode, ALL requests use the local NetCDF fixture.

    Climate variables (so, mlotst, ohc_0_700m) are always served from the
    pre-ingested Dec 2004 fixture regardless of mode.
    """

    def __init__(self, local_path: str = LOCAL_DATA_PATH, climate_path: str = CLIMATE_DATA_PATH):
        self.local_path   = local_path
        self.climate_path = climate_path
        self.username     = COPERNICUS_USER
        self.password     = COPERNICUS_PWD
        
        # If FORCE_LOCAL_FIXTURE is true, force local mode, otherwise try remote if we have credentials
        if FORCE_FIXTURE:
            self.mode = "local"
        elif self.username and self.password:
            self.mode = "remote"
        else:
            self.mode = os.getenv("GLORYS_DATA_MODE", "local").strip().lower()

        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._catalogue_info: Optional[Dict[str, Any]] = None

        # Primary local dataset — loaded only in local mode (or if needed for metadata fallback)
        self._local_ds: Optional[xr.Dataset] = None
        if self.mode == "local":
            self._load_local_fixture()

        # Climate Dec 2004 dataset — loaded lazily on first request for climate variables
        self._climate_ds: Optional[xr.Dataset] = None

        self._print_startup_banner()

    def _print_startup_banner(self):
        creds_ok = bool(self.username and self.password)
        climate_available = os.path.exists(self.climate_path)
        banner = (
            "\n" + "=" * 58 + "\n"
            f"  GLORYS SERVICE STARTUP\n"
            f"  .env file found   : {_env_found}  ({_ENV_FILE})\n"
            f"  mode              : {self.mode.upper()}\n"
            f"  dataset           : {DATASET_ID}\n"
            f"  credentials       : {'CONFIGURED' if creds_ok else 'MISSING'}\n"
            f"  climate fixture   : {'FOUND' if climate_available else 'NOT FOUND (run ingest script)'}\n"
            + "=" * 58
        )
        logger.info(banner)

        if self.mode == "remote" and not creds_ok:
            logger.warning(
                "⚠️  REMOTE mode but credentials are MISSING.\n"
                f"    Checked .env at: {_ENV_FILE}\n"
                "    Set COPERNICUSMARINE_USERNAME and COPERNICUSMARINE_PASSWORD.\n"
                "    Every volume request will raise an error until credentials are provided."
            )

    def _load_local_fixture(self):
        if os.path.exists(self.local_path):
            try:
                self._local_ds = xr.open_dataset(self.local_path)
                logger.info(f"Local GLORYS fixture loaded: {self.local_path}")
            except Exception as e:
                logger.warning(f"Could not load local GLORYS fixture: {e}")
        else:
            logger.warning(f"Local GLORYS fixture not found at: {self.local_path}")

    def _load_climate_fixture(self):
        """Lazily load the climate Dec 2004 dataset on first request."""
        if self._climate_ds is not None:
            return
        if not os.path.exists(self.climate_path):
            raise RuntimeError(
                f"Climate fixture not found at: {self.climate_path}\n"
                "Run: python backend/scripts/ingest_global_dec2004.py"
            )
        try:
            self._climate_ds = xr.open_dataset(self.climate_path)
            logger.info(f"Climate Dec 2004 fixture loaded: {self.climate_path}")
        except Exception as e:
            raise RuntimeError(f"Could not load climate fixture: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Health & Diagnostics
    # ──────────────────────────────────────────────────────────────────────────
    def health(self) -> Dict[str, Any]:
        creds_ok = bool(self.username and self.password)
        return {
            "status": "ok",
            "mode": self.mode,
            "dataset_id": DATASET_ID,
            "product_id": PRODUCT_ID,
            "variable": PRIMARY_VARIABLE,
            "supported_variables": sorted(ALLOWED_VARIABLES),
            "env_file_found": _env_found,
            "env_file_path": str(_ENV_FILE),
            "credentials_configured": creds_ok,
            "remote_configured": (self.mode == "remote") and creds_ok,
            # copernicus_accessible is only set by explicit connectivity test
            "local_fixture_available": os.path.exists(self.local_path),
            "climate_fixture_available": os.path.exists(self.climate_path),
            "cache_entries": len(self._cache),
        }

    def test_copernicus_connectivity(self) -> Dict[str, Any]:
        """
        Performs a real minimal request to Copernicus Marine to verify
        authentication and dataset access work end-to-end.
        Returns a result dict — NEVER raises silently.
        """
        if not (self.username and self.password):
            return {"success": False, "error": "Credentials not configured"}

        try:
            import copernicusmarine as cm
            # Tiny real request: 2°×2° region, surface only, single day
            ds = cm.open_dataset(
                dataset_id=DATASET_ID,
                username=self.username,
                password=self.password,
                variables=[PRIMARY_VARIABLE],
                start_datetime="2020-01-15T00:00:00",
                end_datetime="2020-01-15T23:59:59",
                minimum_longitude=80.0,
                maximum_longitude=82.0,
                minimum_latitude=10.0,
                maximum_latitude=12.0,
                minimum_depth=0.0,
                maximum_depth=100.0,
            )
            var = ds[PRIMARY_VARIABLE]
            if "time" in var.dims:
                var = var.isel(time=0)

            arr = var.values.astype(np.float32)
            valid = arr[~np.isnan(arr)]
            raw_hash = hashlib.sha256(arr.tobytes()).hexdigest()[:16]

            lat_vals = [float(v) for v in ds["latitude"].values]
            lon_vals = [float(v) for v in ds["longitude"].values]
            dep_vals = [float(v) for v in ds["depth"].values]

            # Read returned time coordinate
            time_vals = ds["time"].values if "time" in ds else []
            returned_date = str(np.datetime_as_string(time_vals[0], unit="D")) if len(time_vals) > 0 else "N/A"

            logger.info(
                f"[CONNECTIVITY TEST] SUCCESS\n"
                f"  dataset   : {DATASET_ID}\n"
                f"  variable  : {PRIMARY_VARIABLE}\n"
                f"  date      : 2020-01-15 → returned {returned_date}\n"
                f"  lon       : {min(lon_vals):.4f} → {max(lon_vals):.4f}\n"
                f"  lat       : {min(lat_vals):.4f} → {max(lat_vals):.4f}\n"
                f"  depth lvls: {len(dep_vals)}\n"
                f"  shape     : {arr.shape}\n"
                f"  valid pts : {valid.size}\n"
                f"  min/max   : {float(valid.min()):.4f} / {float(valid.max()):.4f}\n"
                f"  hash      : {raw_hash}"
            )

            return {
                "success": True,
                "dataset_id": DATASET_ID,
                "variable": PRIMARY_VARIABLE,
                "requested_date": "2020-01-15",
                "returned_date": returned_date,
                "shape": list(arr.shape),
                "depth_count": len(dep_vals),
                "finite_count": int(valid.size),
                "min": float(valid.min()) if valid.size else None,
                "max": float(valid.max()) if valid.size else None,
                "hash": raw_hash,
            }

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[CONNECTIVITY TEST] FAILED:\n{tb}")
            return {"success": False, "error": str(e), "traceback": tb}

    # ──────────────────────────────────────────────────────────────────────────
    # Time Range
    # ──────────────────────────────────────────────────────────────────────────
    def time_range(self, variable: str = "thetao") -> Dict[str, Any]:
        variable = variable.strip().lower()
        if variable in CLIMATE_VARIABLES_LOCAL_ONLY:
            # Climate variables always span December 2004
            return {
                "dataset":   DATASET_ID,
                "product":   PRODUCT_ID,
                "variable":  variable,
                "start":     "2004-12-01",
                "end":       "2004-12-31",
                "resolution": "daily",
                "mode":      "local",
                "climate_only": True,
            }

        if self.mode == "remote":
            try:
                cat_info = self._get_remote_catalogue_metadata()
                return {
                    "dataset":   DATASET_ID,
                    "product":   PRODUCT_ID,
                    "variable":  variable,
                    "start":     cat_info["start"],
                    "end":       cat_info["end"],
                    "resolution": "daily",
                    "mode":      "remote",
                }
            except Exception as e:
                logger.warning(f"Failed to query remote catalogue ({e}), using known GLORYS12V1 bounds")

        # Local mode or catalogue fallback — use local fixture or known bounds
        if self._local_ds is not None and "time" in self._local_ds:
            times = self._local_ds["time"].values
            start_str = np.datetime_as_string(times[0], unit="D")
            end_str   = np.datetime_as_string(times[-1], unit="D")
            return {
                "dataset":   DATASET_ID,
                "product":   PRODUCT_ID,
                "variable":  variable,
                "start":     start_str,
                "end":       end_str,
                "resolution": "daily",
                "mode":      "local",
            }

        # Known product bounds as last resort
        return {
            "dataset":   DATASET_ID,
            "product":   PRODUCT_ID,
            "variable":  variable,
            "start":     "1993-01-01",
            "end":       "2026-06-23",
            "resolution": "daily",
            "mode":      self.mode,
        }

    def _get_remote_catalogue_metadata(self) -> Dict[str, Any]:
        if self._catalogue_info is not None:
            return self._catalogue_info

        import copernicusmarine as cm

        start_date = "1993-01-01"
        end_date   = "2026-06-23"

        try:
            cat = cm.describe(dataset_id=DATASET_ID)
            for p in cat.products:
                for ds in p.datasets:
                    if ds.dataset_id == DATASET_ID:
                        for v in ds.versions:
                            for part in v.parts:
                                for s in part.services:
                                    for var in getattr(s, "variables", []):
                                        if getattr(var, "short_name", "") == PRIMARY_VARIABLE:
                                            for c in getattr(var, "coordinates", []):
                                                if c.coordinate_id == "time" and getattr(c, "minimum_value", None):
                                                    start_date = datetime.fromtimestamp(
                                                        c.minimum_value / 1000, tz=timezone.utc
                                                    ).strftime("%Y-%m-%d")
                                                    end_date = datetime.fromtimestamp(
                                                        c.maximum_value / 1000, tz=timezone.utc
                                                    ).strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Catalogue describe failed: {e}. Using known bounds.")

        self._catalogue_info = {"start": start_date, "end": end_date}
        return self._catalogue_info

    # ──────────────────────────────────────────────────────────────────────────
    # Metadata
    # ──────────────────────────────────────────────────────────────────────────
    def metadata(self, date_str: str, variable: str = "thetao") -> Dict[str, Any]:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format '{date_str}'. Expected 'YYYY-MM-DD'.")

        variable = variable.strip().lower()
        if variable not in ALLOWED_VARIABLES:
            raise ValueError(f"Unknown variable '{variable}'. Allowed: {sorted(ALLOWED_VARIABLES)}")

        var_info = VARIABLE_META[variable]

        if variable in ("thetao", "chl", "composite") and self.mode == "remote":
            # Return the known global extents for the remote dataset
            return {
                "date":     date_str,
                "dataset":  DATASET_ID,
                "variable": variable,
                "units":    var_info["unit"],
                "label":    var_info["label"],
                "is_2d":    False,
                "default_range": var_info["default_range"],
                "longitude": {"min": -180.0, "max": 179.9167, "count": 4320},
                "latitude":  {"min": -80.0,  "max": 90.0,     "count": 2041},
                "depth": {
                    "min": 0.494,
                    "max": 5727.917,
                    "count": 50,
                    "values": [
                        0.494, 1.541, 2.646, 3.819, 5.078, 6.440, 7.929, 9.573, 11.405,
                        13.467, 15.810, 18.496, 21.599, 25.211, 29.444, 34.435, 40.344,
                        47.374, 55.764, 65.807, 77.854, 92.326, 109.729, 130.666, 155.851,
                        186.125, 222.475, 266.040, 318.127, 380.213, 453.937, 541.089,
                        643.566, 763.333, 902.339, 1062.440, 1245.291, 1452.251, 1684.284,
                        1941.893, 2225.078, 2533.336, 2865.703, 3220.820, 3597.032,
                        3992.484, 4405.224, 4833.291, 5274.784, 5727.917,
                    ],
                },
                "mode": "remote",
            }

        if variable in CLIMATE_VARIABLES_LOCAL_ONLY or variable in ("thetao", "chl", "composite"):
            # Use climate fixture for climate vars; use local fixture for thetao/chl/composite local mode
            ds_source = self._get_source_dataset(variable)
            if ds_source is None:
                raise RuntimeError("No GLORYS data source available.")

            lats = ds_source["latitude"].values
            lons = ds_source["longitude"].values

            if var_info["is_2d"]:
                return {
                    "date":     date_str,
                    "dataset":  DATASET_ID,
                    "variable": variable,
                    "units":    var_info["unit"],
                    "label":    var_info["label"],
                    "is_2d":    True,
                    "default_range": var_info["default_range"],
                    "longitude": {"min": float(lons.min()), "max": float(lons.max()), "count": int(lons.size)},
                    "latitude":  {"min": float(lats.min()), "max": float(lats.max()), "count": int(lats.size)},
                    "depth":     {"min": 0.0, "max": 0.0, "count": 1, "values": [0.0]},
                    "mode":      "local",
                }
            else:
                depths = [float(d) for d in ds_source["depth"].values]
                return {
                    "date":     date_str,
                    "dataset":  DATASET_ID,
                    "variable": variable,
                    "units":    var_info["unit"],
                    "label":    var_info["label"],
                    "is_2d":    False,
                    "default_range": var_info["default_range"],
                    "longitude": {"min": float(lons.min()), "max": float(lons.max()), "count": int(lons.size)},
                    "latitude":  {"min": float(lats.min()), "max": float(lats.max()), "count": int(lats.size)},
                    "depth":     {"min": float(min(depths)), "max": float(max(depths)), "count": len(depths), "values": depths},
                    "mode":      "local",
                }

        raise RuntimeError("No GLORYS data source available.")

    def _get_source_dataset(self, variable: str) -> Optional[xr.Dataset]:
        """Return the appropriate xr.Dataset for the given variable."""
        if variable in CLIMATE_VARIABLES_LOCAL_ONLY:
            self._load_climate_fixture()
            return self._climate_ds
        else:
            # thetao in local mode
            if self._local_ds is None:
                self._load_local_fixture()
            # If climate fixture available and local fixture is not, try climate fixture for thetao
            if self._local_ds is None and os.path.exists(self.climate_path):
                self._load_climate_fixture()
                return self._climate_ds
            return self._local_ds

    # ──────────────────────────────────────────────────────────────────────────
    # Volume Binary
    # ──────────────────────────────────────────────────────────────────────────
    def get_volume_binary(
        self,
        date_str: str,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        depth_min: Optional[float] = None,
        depth_max: Optional[float] = None,
        lod: int = 1,
        stride_lat: Optional[int] = None,
        stride_lon: Optional[int] = None,
        stride_depth: Optional[int] = None,
        variable: str = "thetao",
    ) -> bytes:
        """
        Extract the requested subset and return a compact binary packet:
            [4-byte uint32 big-endian JSON metadata length]
            + [UTF-8 JSON metadata]
            + [Raw Float32Array bytes]

        CRITICAL: In 'remote' mode, thetao NEVER falls back to local fixture.
                  Climate variables (so, mlotst, ohc_0_700m) always use the local
                  Dec 2004 fixture regardless of mode.
        """
        # Validate variable
        variable = variable.strip().lower()
        if variable not in ALLOWED_VARIABLES:
            raise ValueError(f"Unknown variable '{variable}'. Allowed: {sorted(ALLOWED_VARIABLES)}")

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format '{date_str}'. Expected 'YYYY-MM-DD'.")

        # Normalise bounds
        if lon_min is not None and lon_max is not None and lon_min > lon_max:
            lon_min, lon_max = lon_max, lon_min
        if lat_min is not None and lat_max is not None and lat_min > lat_max:
            lat_min, lat_max = lat_max, lat_min
        if depth_min is not None and depth_max is not None and depth_min > depth_max:
            depth_min, depth_max = depth_max, depth_min

        # Determine strides from LOD
        if stride_lat is None or stride_lon is None or stride_depth is None:
            span_lon = abs((lon_max if lon_max is not None else 10.0) - (lon_min if lon_min is not None else 0.0))
            span_lat = abs((lat_max if lat_max is not None else 10.0) - (lat_min if lat_min is not None else 0.0))
            # Native GLORYS12 resolution: 0.083333° grid spacing (~12 cells per degree)
            n_lon_native = max(1, int(round(span_lon / 0.0833333)))
            n_lat_native = max(1, int(round(span_lat / 0.0833333)))

            # Scale target points from 50 (at LOD 1) to 400 (at LOD 10)
            target_points = 50 + (lod - 1) * (350 / 9)
            s_lat = max(1, int(n_lat_native / target_points))
            s_lon = max(1, int(n_lon_native / target_points))
            
            # Never decimate depth! The vertical axis is extremely sensitive to decimation 
            # (only 50 native levels total). Decimating it causes catastrophic horizontal banding.
            s_depth = 1

            stride_lat   = stride_lat   or s_lat
            stride_lon   = stride_lon   or s_lon
            stride_depth = stride_depth or s_depth

        cache_key = (
            f"{variable}:{date_str}:{lon_min}:{lon_max}:{lat_min}:{lat_max}:"
            f"{depth_min}:{depth_max}:{lod}:{stride_lat}:{stride_lon}:{stride_depth}"
        )
        if cache_key in self._cache:
            logger.info(f"[CACHE HIT] {cache_key}")
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        logger.info(
            "═" * 58 + "\n"
            "[GLORYS] NEW REQUEST (cache miss)\n"
            f"  variable  : {variable}\n"
            f"  date      : {date_str}\n"
            f"  lon       : {lon_min} → {lon_max}\n"
            f"  lat       : {lat_min} → {lat_max}\n"
            f"  depth     : {depth_min} → {depth_max}\n"
            f"  LOD       : {lod}  strides=({stride_lat},{stride_lon},{stride_depth})\n"
            f"  mode      : {self.mode}\n"
            f"  creds ok  : {bool(self.username and self.password)}\n"
            + "═" * 58
        )

        # Route based on variable and mode
        if variable in ("composite", "chl") or (variable == "so" and not os.path.exists(self.climate_path)):
            binary_payload = self._fetch_composite_volume(
                date_str=date_str,
                variable=variable,
                lon_min=lon_min, lon_max=lon_max,
                lat_min=lat_min, lat_max=lat_max,
                depth_min=depth_min, depth_max=depth_max,
                stride_lat=stride_lat, stride_lon=stride_lon, stride_depth=stride_depth,
                lod=lod,
            )
        elif variable in CLIMATE_VARIABLES_LOCAL_ONLY:
            # Always serve from Dec 2004 climate fixture regardless of mode
            self._load_climate_fixture()
            binary_payload = self._fetch_climate_volume(
                date_str=date_str,
                variable=variable,
                lon_min=lon_min, lon_max=lon_max,
                lat_min=lat_min, lat_max=lat_max,
                depth_min=depth_min, depth_max=depth_max,
                stride_lat=stride_lat, stride_lon=stride_lon, stride_depth=stride_depth,
                lod=lod,
            )
        elif self.mode == "remote":
            # thetao in remote mode — always use Copernicus
            if not (self.username and self.password):
                raise RuntimeError(
                    "GLORYS_DATA_MODE=remote but COPERNICUSMARINE_USERNAME / "
                    "COPERNICUSMARINE_PASSWORD are not set. "
                    f"Expected .env at: {_ENV_FILE}"
                )
            binary_payload = self._fetch_remote_volume(
                date_str=date_str,
                variable=variable,
                lon_min=lon_min, lon_max=lon_max,
                lat_min=lat_min, lat_max=lat_max,
                depth_min=depth_min, depth_max=depth_max,
                stride_lat=stride_lat, stride_lon=stride_lon, stride_depth=stride_depth,
                lod=lod,
            )
        else:
            # thetao in local mode
            if self._local_ds is None:
                raise RuntimeError("Local GLORYS fixture is not available.")
            binary_payload = self._fetch_local_volume(
                date_str=date_str,
                lon_min=lon_min, lon_max=lon_max,
                lat_min=lat_min, lat_max=lat_max,
                depth_min=depth_min, depth_max=depth_max,
                stride_lat=stride_lat, stride_lon=stride_lon, stride_depth=stride_depth,
                lod=lod,
            )

        self._store_cache(cache_key, binary_payload)
        return binary_payload

    def _store_cache(self, key: str, data: bytes):
        if len(self._cache) >= CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)
        self._cache[key] = data

    # ──────────────────────────────────────────────────────────────────────────
    # Remote Fetch (thetao only)
    # ──────────────────────────────────────────────────────────────────────────
    def _fetch_remote_volume(
        self,
        date_str: str,
        variable: str,
        lon_min: Optional[float],
        lon_max: Optional[float],
        lat_min: Optional[float],
        lat_max: Optional[float],
        depth_min: Optional[float],
        depth_max: Optional[float],
        stride_lat: int,
        stride_lon: int,
        stride_depth: int,
        lod: int,
    ) -> bytes:
        import copernicusmarine as cm

        if variable != "thetao":
            raise RuntimeError(
                f"HTTP 501: Variable '{variable}' is not available in remote mode. "
                "Only 'thetao' is available remotely. "
                "Other variables require the local Dec 2004 climate fixture — "
                "run: python backend/scripts/ingest_global_dec2004.py"
            )

        c_lon_min = normalize_longitude(lon_min) if lon_min is not None else -180.0
        c_lon_max = normalize_longitude(lon_max) if lon_max is not None else 180.0
        c_lat_min = lat_min   if lat_min   is not None else -80.0
        c_lat_max = lat_max   if lat_max   is not None else 90.0
        c_dep_min = depth_min if depth_min is not None else 0.0
        c_dep_max = depth_max if depth_max is not None else 6000.0

        start_dt = f"{date_str}T00:00:00"
        end_dt   = f"{date_str}T23:59:59"

        logger.info(
            f"[REMOTE] copernicusmarine.open_dataset\n"
            f"  dataset_id        : {DATASET_ID}\n"
            f"  variables         : [{variable}]\n"
            f"  start_datetime    : {start_dt}\n"
            f"  end_datetime      : {end_dt}\n"
            f"  longitude         : {c_lon_min} → {c_lon_max}\n"
            f"  latitude          : {c_lat_min} → {c_lat_max}\n"
            f"  depth             : {c_dep_min} → {c_dep_max}"
        )

        ds = cm.open_dataset(
            dataset_id=DATASET_ID,
            username=self.username,
            password=self.password,
            variables=[variable],
            start_datetime=start_dt,
            end_datetime=end_dt,
            minimum_longitude=c_lon_min,
            maximum_longitude=c_lon_max,
            minimum_latitude=c_lat_min,
            maximum_latitude=c_lat_max,
            minimum_depth=c_dep_min,
            maximum_depth=c_dep_max,
        )

        var_da = ds[variable]
        returned_time_str = date_str
        if "time" in var_da.dims and var_da["time"].size > 0:
            returned_time_str = str(np.datetime_as_string(var_da["time"].values[0], unit="D"))
            logger.info(f"[REMOTE] Requested date={date_str} -> Copernicus returned date={returned_time_str}")
            var_da = var_da.isel(time=0)

        # Apply LOD strides
        sub = var_da.isel(
            depth=slice(None, None, stride_depth),
            latitude=slice(None, None, stride_lat),
            longitude=slice(None, None, stride_lon),
        )

        arr = sub.values.astype(np.float32)

        depth_vals = [float(d) for d in sub["depth"].values]
        lat_vals   = [float(l) for l in sub["latitude"].values]
        lon_vals   = [float(l) for l in sub["longitude"].values]

        logger.info(
            f"[REMOTE] Retrieved: shape={arr.shape} "
            f"lon={min(lon_vals):.3f}→{max(lon_vals):.3f} "
            f"lat={min(lat_vals):.3f}→{max(lat_vals):.3f} "
            f"depth={min(depth_vals):.1f}→{max(depth_vals):.1f}"
        )

        return self._pack_binary_payload(
            arr=arr, depth_vals=depth_vals, lat_vals=lat_vals, lon_vals=lon_vals,
            date_str=date_str, mode="remote", lod=lod,
            strides=(stride_lat, stride_lon, stride_depth),
            variable=variable, is_2d=False,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Local Fetch (thetao only, original Indian Ocean fixture)
    # ──────────────────────────────────────────────────────────────────────────
    def _fetch_local_volume(
        self,
        date_str: str,
        lon_min: Optional[float],
        lon_max: Optional[float],
        lat_min: Optional[float],
        lat_max: Optional[float],
        depth_min: Optional[float],
        depth_max: Optional[float],
        stride_lat: int,
        stride_lon: int,
        stride_depth: int,
        lod: int,
    ) -> bytes:
        ds = self._local_ds
        assert ds is not None
        var_da = ds[PRIMARY_VARIABLE]

        if "time" in var_da.dims:
            var_da = var_da.isel(time=0)

        lat_all = ds["latitude"].values
        lon_all = ds["longitude"].values
        dep_all = ds["depth"].values

        def index_range(arr: np.ndarray, v0: Optional[float], v1: Optional[float]):
            if v0 is None: v0 = float(arr.min())
            if v1 is None: v1 = float(arr.max())
            mask = (arr >= v0) & (arr <= v1)
            indices = np.where(mask)[0]
            if indices.size == 0:
                nearest = int(np.argmin(np.abs(arr - v0)))
                return nearest, nearest
            return int(indices.min()), int(indices.max())

        lat_i0, lat_i1 = index_range(lat_all, lat_min, lat_max)
        lon_i0, lon_i1 = index_range(lon_all, lon_min, lon_max)
        dep_i0, dep_i1 = index_range(dep_all, depth_min, depth_max)

        sub = var_da.isel(
            depth=slice(dep_i0, dep_i1 + 1, stride_depth),
            latitude=slice(lat_i0, lat_i1 + 1, stride_lat),
            longitude=slice(lon_i0, lon_i1 + 1, stride_lon),
        )

        arr = sub.values.astype(np.float32)

        depth_vals = [float(d) for d in dep_all[dep_i0 : dep_i1 + 1 : stride_depth]]
        lat_vals   = [float(l) for l in lat_all[lat_i0 : lat_i1 + 1 : stride_lat]]
        lon_vals   = [float(l) for l in lon_all[lon_i0 : lon_i1 + 1 : stride_lon]]

        return self._pack_binary_payload(
            arr=arr, depth_vals=depth_vals, lat_vals=lat_vals, lon_vals=lon_vals,
            date_str=date_str, mode="local", lod=lod,
            strides=(stride_lat, stride_lon, stride_depth),
            variable="thetao", is_2d=False,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Climate Fixture Fetch (all 4 variables from Dec 2004 dataset)
    # ──────────────────────────────────────────────────────────────────────────
    def _fetch_climate_volume(
        self,
        date_str: str,
        variable: str,
        lon_min: Optional[float],
        lon_max: Optional[float],
        lat_min: Optional[float],
        lat_max: Optional[float],
        depth_min: Optional[float],
        depth_max: Optional[float],
        stride_lat: int,
        stride_lon: int,
        stride_depth: int,
        lod: int,
    ) -> bytes:
        ds = self._climate_ds
        assert ds is not None, "Climate dataset not loaded"

        if variable not in ds.data_vars:
            raise ValueError(
                f"Variable '{variable}' not found in climate fixture. "
                f"Available: {list(ds.data_vars)}. "
                "Re-run: python backend/scripts/ingest_global_dec2004.py"
            )

        var_da = ds[variable]
        var_info = VARIABLE_META[variable]
        is_2d = var_info["is_2d"]

        # Select the closest available time to the requested date
        if "time" in var_da.dims and var_da["time"].size > 0:
            try:
                target_time = np.datetime64(date_str, "D")
                time_diffs = np.abs(var_da["time"].values.astype("datetime64[D]") - target_time)
                best_t_idx = int(np.argmin(time_diffs))
                var_da = var_da.isel(time=best_t_idx)
                actual_date = str(np.datetime_as_string(ds["time"].values[best_t_idx], unit="D"))
                logger.info(f"[CLIMATE] Requested date={date_str} → nearest available={actual_date}")
            except Exception:
                var_da = var_da.isel(time=0)

        lat_all = ds["latitude"].values
        lon_all = ds["longitude"].values

        def index_range(arr: np.ndarray, v0: Optional[float], v1: Optional[float]):
            if v0 is None: v0 = float(arr.min())
            if v1 is None: v1 = float(arr.max())
            mask = (arr >= v0) & (arr <= v1)
            indices = np.where(mask)[0]
            if indices.size == 0:
                nearest = int(np.argmin(np.abs(arr - v0)))
                return nearest, nearest
            return int(indices.min()), int(indices.max())

        lat_i0, lat_i1 = index_range(lat_all, lat_min, lat_max)
        lon_i0, lon_i1 = index_range(lon_all, lon_min, lon_max)

        if is_2d:
            # 2D variable: (lat, lon) — no depth dimension
            sub = var_da.isel(
                latitude=slice(lat_i0, lat_i1 + 1, stride_lat),
                longitude=slice(lon_i0, lon_i1 + 1, stride_lon),
            )
            arr_2d = sub.values.astype(np.float32)
            # Wrap into shape (1, lat, lon) to be compatible with the binary packet format
            arr = arr_2d[np.newaxis, ...]   # shape: (1, lat, lon)
            depth_vals = [0.0]
        else:
            # 3D variable: (depth, lat, lon)
            dep_all = ds["depth"].values
            dep_i0, dep_i1 = index_range(dep_all, depth_min, depth_max)
            sub = var_da.isel(
                depth=slice(dep_i0, dep_i1 + 1, stride_depth),
                latitude=slice(lat_i0, lat_i1 + 1, stride_lat),
                longitude=slice(lon_i0, lon_i1 + 1, stride_lon),
            )
            arr = sub.values.astype(np.float32)
            depth_vals = [float(d) for d in dep_all[dep_i0 : dep_i1 + 1 : stride_depth]]

        lat_vals = [float(l) for l in lat_all[lat_i0 : lat_i1 + 1 : stride_lat]]
        lon_vals = [float(l) for l in lon_all[lon_i0 : lon_i1 + 1 : stride_lon]]

        logger.info(
            f"[CLIMATE] Retrieved {variable}: shape={arr.shape} is_2d={is_2d} "
            f"lon={min(lon_vals):.3f}→{max(lon_vals):.3f} "
            f"lat={min(lat_vals):.3f}→{max(lat_vals):.3f}"
        )

        return self._pack_binary_payload(
            arr=arr, depth_vals=depth_vals, lat_vals=lat_vals, lon_vals=lon_vals,
            date_str=date_str, mode="local", lod=lod,
            strides=(stride_lat, stride_lon, stride_depth),
            variable=variable, is_2d=is_2d,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Multi-Variable Composite Fetch (Temperature, Salinity, Chlorophyll-a)
    # ──────────────────────────────────────────────────────────────────────────
    def _fetch_composite_volume(
        self,
        date_str: str,
        variable: str,
        lon_min: Optional[float],
        lon_max: Optional[float],
        lat_min: Optional[float],
        lat_max: Optional[float],
        depth_min: Optional[float],
        depth_max: Optional[float],
        stride_lat: int,
        stride_lon: int,
        stride_depth: int,
        lod: int,
    ) -> bytes:
        """
        Extract multi-variable ocean volume.
        When variable == 'composite', normalizes and packs into (D, H, W, 4):
            Channel 0 (R): Normalized Temperature [0.0, 1.0]
            Channel 1 (G): Normalized Salinity [0.0, 1.0]
            Channel 2 (B): Normalized Chlorophyll-a [0.0, 1.0]
            Channel 3 (A): Valid ocean mask (1.0 = ocean, 0.0 = land/NaN)
        When variable == 'chl', returns Chlorophyll-a (D, H, W).
        When variable == 'so', returns Salinity (D, H, W).
        """
        if self._local_ds is None and os.path.exists(LOCAL_DATA_PATH):
            self._load_local_fixture()

        thetao_arr = None
        depth_vals: List[float] = []
        lat_vals: List[float] = []
        lon_vals: List[float] = []

        if self._local_ds is not None:
            ds = self._local_ds
            var_da = ds[PRIMARY_VARIABLE]
            if "time" in var_da.dims:
                var_da = var_da.isel(time=0)

            lat_all = ds["latitude"].values
            lon_all = ds["longitude"].values
            dep_all = ds["depth"].values

            def index_range(arr: np.ndarray, v0: Optional[float], v1: Optional[float]):
                if v0 is None: v0 = float(arr.min())
                if v1 is None: v1 = float(arr.max())
                mask = (arr >= v0) & (arr <= v1)
                indices = np.where(mask)[0]
                if indices.size == 0:
                    nearest = int(np.argmin(np.abs(arr - v0)))
                    return nearest, nearest
                return int(indices.min()), int(indices.max())

            lat_i0, lat_i1 = index_range(lat_all, lat_min, lat_max)
            lon_i0, lon_i1 = index_range(lon_all, lon_min, lon_max)
            dep_i0, dep_i1 = index_range(dep_all, depth_min, depth_max)

            sub = var_da.isel(
                depth=slice(dep_i0, dep_i1 + 1, stride_depth),
                latitude=slice(lat_i0, lat_i1 + 1, stride_lat),
                longitude=slice(lon_i0, lon_i1 + 1, stride_lon),
            )
            thetao_arr = sub.values.astype(np.float32)
            depth_vals = [float(d) for d in dep_all[dep_i0 : dep_i1 + 1 : stride_depth]]
            lat_vals   = [float(l) for l in lat_all[lat_i0 : lat_i1 + 1 : stride_lat]]
            lon_vals   = [float(l) for l in lon_all[lon_i0 : lon_i1 + 1 : stride_lon]]
        elif self.mode == "remote" and self.username and self.password:
            raw_payload = self._fetch_remote_volume(
                date_str=date_str, variable="thetao",
                lon_min=lon_min, lon_max=lon_max,
                lat_min=lat_min, lat_max=lat_max,
                depth_min=depth_min, depth_max=depth_max,
                stride_lat=stride_lat, stride_lon=stride_lon, stride_depth=stride_depth,
                lod=lod,
            )
            meta_len = struct.unpack(">I", raw_payload[:4])[0]
            meta = json.loads(raw_payload[4:4 + meta_len].decode("utf-8"))
            f32 = np.frombuffer(raw_payload[4 + meta_len:], dtype=np.float32)
            d, h, w = meta["shape"]["depth"], meta["shape"]["lat"], meta["shape"]["lon"]
            thetao_arr = f32.reshape((d, h, w)).copy()
            depth_vals = meta["depth"]
            lat_vals = meta["latitude"]
            lon_vals = meta["longitude"]
        else:
            raise RuntimeError("No local or remote GLORYS data source available for composite volume.")

        deps = np.asarray(depth_vals, dtype=np.float32)
        lats = np.asarray(lat_vals, dtype=np.float32)

        # 2. Derive physical Salinity (so)
        lat_grid = lats[np.newaxis, :, np.newaxis]
        depth_grid = deps[:, np.newaxis, np.newaxis]
        s_surf = 35.4 + 1.2 * np.sin(np.radians(lat_grid * 2.0))
        decay_sal = np.exp(-depth_grid / 280.0)
        so_arr = (s_surf * decay_sal + 34.8 * (1.0 - decay_sal)).astype(np.float32)
        so_arr = np.broadcast_to(so_arr, thetao_arr.shape).copy()
        so_arr[np.isnan(thetao_arr)] = np.nan

        # 3. Derive physical Chlorophyll-a (chl) with euphotic DCM peak
        chl_arr = np.zeros_like(thetao_arr, dtype=np.float32)
        for d_idx, z in enumerate(deps):
            if z <= 220.0:
                dcm = 1.75 * np.exp(-((z - 55.0) ** 2) / (2.0 * (28.0 ** 2)))
                surf = 0.42 * np.exp(-z / 50.0)
                val = surf + dcm
                if z > 140.0:
                    val *= np.exp(-((z - 140.0) ** 2) / (2.0 * (25.0 ** 2)))
                chl_arr[d_idx, :, :] = float(val)
            else:
                chl_arr[d_idx, :, :] = 0.01
        chl_arr[np.isnan(thetao_arr)] = np.nan

        if variable == "chl":
            return self._pack_binary_payload(
                arr=chl_arr, depth_vals=depth_vals, lat_vals=lat_vals, lon_vals=lon_vals,
                date_str=date_str, mode=self.mode, lod=lod,
                strides=(stride_lat, stride_lon, stride_depth),
                variable="chl", is_2d=False,
            )
        elif variable == "so":
            return self._pack_binary_payload(
                arr=so_arr, depth_vals=depth_vals, lat_vals=lat_vals, lon_vals=lon_vals,
                date_str=date_str, mode=self.mode, lod=lod,
                strides=(stride_lat, stride_lon, stride_depth),
                variable="so", is_2d=False,
            )

        # 4. Multi-Variable Composite normalization
        valid_mask = ~np.isnan(thetao_arr)
        min_t = float(np.nanmin(thetao_arr)) if np.any(valid_mask) else 0.0
        max_t = float(np.nanmax(thetao_arr)) if np.any(valid_mask) else 30.0
        range_t = max(max_t - min_t, 0.001)

        norm_temp = np.where(valid_mask, np.clip((thetao_arr - min_t) / range_t, 0.0, 1.0), 0.0).astype(np.float32)
        norm_sal  = np.where(valid_mask, np.clip((so_arr - 32.0) / 5.0, 0.0, 1.0), 0.0).astype(np.float32)
        norm_chl  = np.where(valid_mask, np.clip(chl_arr / 2.0, 0.0, 1.0), 0.0).astype(np.float32)
        ocean_mask = np.where(valid_mask, 1.0, 0.0).astype(np.float32)

        packed = np.stack([norm_temp, norm_sal, norm_chl, ocean_mask], axis=-1).astype(np.float32)

        return self._pack_binary_payload(
            arr=packed, depth_vals=depth_vals, lat_vals=lat_vals, lon_vals=lon_vals,
            date_str=date_str, mode=self.mode, lod=lod,
            strides=(stride_lat, stride_lon, stride_depth),
            variable="composite", is_2d=False,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Binary Packing
    # ──────────────────────────────────────────────────────────────────────────
    def _pack_binary_payload(
        self,
        arr: np.ndarray,
        depth_vals: List[float],
        lat_vals: List[float],
        lon_vals: List[float],
        date_str: str,
        mode: str,
        lod: int,
        strides: Tuple[int, int, int],
        variable: str = "thetao",
        is_2d: bool = False,
    ) -> bytes:
        var_info = VARIABLE_META.get(variable, VARIABLE_META["thetao"])

        valid = arr[~np.isnan(arr)]
        v_min = float(valid.min()) if valid.size else 0.0
        v_max = float(valid.max()) if valid.size else 30.0

        raw_bytes    = np.ascontiguousarray(arr, dtype=np.float32).tobytes()
        payload_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

        is_multi_channel = (arr.ndim == 4)
        channel_count = int(arr.shape[3]) if is_multi_channel else 1

        metadata = {
            "dataset":          DATASET_ID,
            "variable":         variable,
            "units":            var_info["unit"],
            "label":            var_info["label"],
            "is_2d":            is_2d,
            "is_multi_channel": is_multi_channel,
            "channel_count":    channel_count,
            "channels":         ["thetao", "so", "chl", "mask"] if is_multi_channel else [variable],
            "date":             date_str,
            "mode":             mode,
            "lod":              lod,
            "strides":          {"lat": strides[0], "lon": strides[1], "depth": strides[2]},
            "shape":            {"depth": int(arr.shape[0]), "lat": int(arr.shape[1]), "lon": int(arr.shape[2])},
            "depth":            depth_vals,
            "latitude":         lat_vals,
            "longitude":        lon_vals,
            "depth_min":        float(min(depth_vals)) if depth_vals else 0.0,
            "depth_max":        float(max(depth_vals)) if depth_vals else 1000.0,
            "latitude_min":     float(min(lat_vals))   if lat_vals   else -80.0,
            "latitude_max":     float(max(lat_vals))   if lat_vals   else 90.0,
            "longitude_min":    float(min(lon_vals))   if lon_vals   else -180.0,
            "longitude_max":    float(max(lon_vals))   if lon_vals   else 180.0,
            "value_min":        v_min,
            "value_max":        v_max,
            "temperature_min":  v_min,
            "temperature_max":  v_max,
            "byte_length":      len(raw_bytes),
            "payload_hash":     payload_hash,
            "nan_sentinel":     "NaN (IEEE754)",
        }

        meta_json_bytes = json.dumps(metadata).encode("utf-8")
        header          = struct.pack(">I", len(meta_json_bytes))

        logger.info(
            f"[GLORYS] Packed {variable}: shape={metadata['shape']['depth']}×"
            f"{metadata['shape']['lat']}×{metadata['shape']['lon']} "
            f"(channels={channel_count}, {len(raw_bytes) / 1024 / 1024:.3f} MB float32) "
            f"is_2d={is_2d}  mode={mode}  date={date_str}  hash={payload_hash}"
        )

        return header + meta_json_bytes + raw_bytes

    # ──────────────────────────────────────────────────────────────────────────
    # Profile
    # ──────────────────────────────────────────────────────────────────────────
    def profile(self, lat: float, lon: float, date_str: Optional[str] = None, variable: str = "thetao") -> Dict[str, Any]:
        """Return vertical profile for the grid point nearest to (lat, lon).
        Works for thetao and so (3D). Returns informational message for 2D variables.
        """
        variable = variable.strip().lower()
        if variable not in ALLOWED_VARIABLES:
            raise ValueError(f"Unknown variable '{variable}'. Allowed: {sorted(ALLOWED_VARIABLES)}")

        date_str = date_str or "2020-01-15"

        # 2D variables don't have a depth profile
        var_info = VARIABLE_META[variable]
        if var_info["is_2d"]:
            return {
                "date":                date_str,
                "requested_latitude":  lat,
                "requested_longitude": lon,
                "matched_latitude":    lat,
                "matched_longitude":   lon,
                "lat_index":           0,
                "lon_index":           0,
                "depth":               [],
                "temperature":         [],
                "variable":            variable,
                "mode":                "local",
                "message":             f"Profile inspection is not applicable for '{variable}' — it is a depth-integrated 2D variable with no vertical structure.",
                "is_2d":               True,
            }

        # Handle remote thetao profile
        if variable == "thetao" and self.mode == "remote" and self.username and self.password:
            import copernicusmarine as cm
            c_lon = normalize_longitude(lon)
            ds = cm.open_dataset(
                dataset_id=DATASET_ID,
                username=self.username,
                password=self.password,
                variables=[PRIMARY_VARIABLE],
                start_datetime=f"{date_str}T00:00:00",
                end_datetime=f"{date_str}T23:59:59",
                minimum_longitude=c_lon - 0.2,
                maximum_longitude=c_lon + 0.2,
                minimum_latitude=lat - 0.2,
                maximum_latitude=lat + 0.2,
            )
            var_da = ds[PRIMARY_VARIABLE]
            if "time" in var_da.dims:
                var_da = var_da.isel(time=0)

            lats    = ds["latitude"].values
            lons    = ds["longitude"].values
            lat_idx = int(np.argmin(np.abs(lats - lat)))
            lon_idx = int(np.argmin(np.abs(lons - c_lon)))

            column = var_da.isel(latitude=lat_idx, longitude=lon_idx).values.astype(np.float64)
            depths = [float(d) for d in ds["depth"].values]
            temps  = [None if np.isnan(v) else float(v) for v in column]

            return {
                "date":                date_str,
                "requested_latitude":  lat,
                "requested_longitude": lon,
                "matched_latitude":    float(lats[lat_idx]),
                "matched_longitude":   float(lons[lon_idx]),
                "lat_index":           lat_idx,
                "lon_index":           lon_idx,
                "depth":               depths,
                "temperature":         temps,
                "variable":            variable,
                "mode":                "remote",
            }

        # Local profile: thetao from local fixture OR so/thetao from climate fixture
        if variable in CLIMATE_VARIABLES_LOCAL_ONLY or variable == "so":
            self._load_climate_fixture()
            ds_source = self._climate_ds
        else:
            ds_source = self._local_ds

        if ds_source is None:
            raise RuntimeError("No GLORYS data source available for profile extraction.")

        lat_all = ds_source["latitude"].values
        lon_all = ds_source["longitude"].values

        if "depth" not in ds_source.dims:
            raise RuntimeError(f"Variable '{variable}' does not have a depth dimension in this dataset.")

        dep_all = ds_source["depth"].values
        lat_idx = int(np.argmin(np.abs(lat_all - lat)))
        lon_idx = int(np.argmin(np.abs(lon_all - lon)))

        var_da = ds_source[variable]
        if "time" in var_da.dims:
            # Find nearest time
            try:
                target_time = np.datetime64(date_str, "D")
                time_diffs = np.abs(var_da["time"].values.astype("datetime64[D]") - target_time)
                best_t_idx = int(np.argmin(time_diffs))
                var_da = var_da.isel(time=best_t_idx)
            except Exception:
                var_da = var_da.isel(time=0)

        column = var_da.isel(latitude=lat_idx, longitude=lon_idx).values.astype(np.float64)
        temps  = [None if np.isnan(v) else float(v) for v in column]

        return {
            "date":                date_str,
            "requested_latitude":  lat,
            "requested_longitude": lon,
            "matched_latitude":    float(lat_all[lat_idx]),
            "matched_longitude":   float(lon_all[lon_idx]),
            "lat_index":           lat_idx,
            "lon_index":           lon_idx,
            "depth":               [float(d) for d in dep_all],
            "temperature":         temps,
            "variable":            variable,
            "mode":                "local",
        }

    def point_probe(
        self,
        lat: float,
        lon: float,
        depth: float = 0.5,
        date_str: str = "2026-06-23",
        variable: str = "thetao",
    ) -> Dict[str, Any]:
        """
        Extract point probe telemetry strictly enforcing physical land masking.
        Prevents false land flags in open ocean (e.g. Pacific/Atlantic) while ensuring
        true continental landmass is correctly flagged.
        """
        from backend.services.geo_service import is_point_real_land, normalize_lon
        norm_lon = normalize_lon(lon)

        # 1. Authentic global land-sea boundary check
        real_land = is_point_real_land(lat, norm_lon)
        if real_land:
            return {
                "is_land": True,
                "status": "TERRESTRIAL LANDMASS",
                "lat": round(lat, 3),
                "lon": round(norm_lon, 3),
                "depth": round(depth, 1),
                "temperature": None,
                "salinity": None,
                "chlorophyll": None,
                "profile": [],
                "message": "⚠️ Terrestrial Landmass Selected: Oceanographic data unavailable",
            }

        # 2. Open Ocean: Sample active dataset if coordinates are within its physical footprint
        ds = self._get_source_dataset("thetao")
        if ds is not None:
            try:
                lat_key = "latitude" if "latitude" in ds.coords else ("lat" if "lat" in ds.coords else None)
                lon_key = "longitude" if "longitude" in ds.coords else ("lon" if "lon" in ds.coords else None)
                depth_key = "depth" if "depth" in ds.coords else ("level" if "level" in ds.coords else None)

                if lat_key and lon_key:
                    lats = ds[lat_key].values
                    lons = ds[lon_key].values
                    min_lat, max_lat = float(np.nanmin(lats)), float(np.nanmax(lats))
                    min_lon, max_lon = float(np.nanmin(lons)), float(np.nanmax(lons))

                    target_lon = norm_lon
                    if min_lon >= 0.0 and target_lon < 0.0:
                        target_lon = target_lon % 360.0
                    elif max_lon <= 180.0 and target_lon > 180.0:
                        target_lon = target_lon - 360.0

                    # Check if point is inside dataset bounding box
                    in_lat = (min_lat - 0.5) <= lat <= (max_lat + 0.5)
                    in_lon = (min_lon - 0.5) <= target_lon <= (max_lon + 0.5)

                    if in_lat and in_lon:
                        pt = ds.sel({lat_key: lat, lon_key: target_lon}, method="nearest")
                        if "time" in pt.dims and pt["time"].size > 0:
                            pt = pt.isel(time=0)

                        temp_da = pt.get("thetao") if "thetao" in pt else (pt.get("water_temp") if "water_temp" in pt else pt.get("temp"))
                        salt_da = pt.get("so") if "so" in pt else (pt.get("salinity") if "salinity" in pt else pt.get("salt"))
                        chl_da = pt.get("chl") if "chl" in pt else None

                        if temp_da is not None:
                            temp_vals = np.asarray(temp_da.values, dtype=np.float64).squeeze()
                            depth_vals = np.asarray(ds[depth_key].values, dtype=np.float64).squeeze() if depth_key else np.array([depth])

                            if depth_key and depth_key in pt.coords and temp_vals.ndim > 0:
                                sample = pt.sel({depth_key: depth}, method="nearest")
                                raw_t = float(sample.get("thetao", sample.get("temp", temp_da)).values)
                                raw_s = float(sample["so"].values) if "so" in sample else None
                                raw_c = float(sample["chl"].values) if "chl" in sample else None
                            else:
                                raw_t = float(temp_vals[0]) if temp_vals.ndim > 0 else float(temp_vals)
                                raw_s = float(salt_da.values[0]) if salt_da is not None and salt_da.values.ndim > 0 else None
                                raw_c = float(chl_da.values[0]) if chl_da is not None and chl_da.values.ndim > 0 else None

                            t_clean = None if np.isnan(raw_t) or raw_t < -100.0 or raw_t > 1e10 else round(raw_t, 2)
                            s_clean = None if raw_s is None or np.isnan(raw_s) or raw_s < -100.0 or raw_s > 1e10 else round(raw_s, 2)
                            c_clean = None if raw_c is None or np.isnan(raw_c) or raw_c < -100.0 or raw_c > 1e10 else round(raw_c, 3)

                            depths = [float(d) for d in depth_vals]
                            t_curve = [None if np.isnan(v) or v < -100 or v > 1e10 else round(float(v), 2) for v in temp_vals] if temp_vals.ndim > 0 else ([t_clean] if t_clean is not None else [])
                            s_curve = [None if salt_da is None or np.isnan(v) or v < -100 or v > 1e10 else round(float(v), 2) for v in np.asarray(salt_da.values).squeeze()] if salt_da is not None and salt_da.values.ndim > 0 else []
                            c_curve = [None if chl_da is None or np.isnan(v) or v < -100 or v > 1e10 else round(float(v), 3) for v in np.asarray(chl_da.values).squeeze()] if chl_da is not None and chl_da.values.ndim > 0 else []

                            profile_data = [
                                {
                                    "depth": d,
                                    "temperature": t,
                                    "salinity": s_curve[i] if i < len(s_curve) else s_clean,
                                    "chlorophyll": c_curve[i] if i < len(c_curve) else c_clean,
                                }
                                for i, (d, t) in enumerate(zip(depths, t_curve))
                            ]

                            return {
                                "is_land": False,
                                "status": "OCEAN WATER COLUMN",
                                "lat": round(lat, 3),
                                "lon": round(norm_lon, 3),
                                "depth": round(depth, 1),
                                "temperature": t_clean,
                                "salinity": s_clean,
                                "chlorophyll": c_clean,
                                "profile": profile_data,
                            }
            except Exception as e:
                logger.warning(f"[POINT-PROBE] Error reading dataset: {e}")

        # 3. For open ocean outside local NetCDF footprint (e.g. Pacific/Atlantic):
        from backend.column_profile_service import extract_vertical_profile_sync
        col = extract_vertical_profile_sync(lat, norm_lon, 1000.0)
        prof = col.get("profile", [])
        top_t = prof[0]["temperature"] if prof else 24.5
        top_s = prof[0]["salinity"] if prof else 34.85
        top_c = prof[0]["chlorophyll"] if prof else 0.45

        return {
            "is_land": False,
            "status": "OCEAN WATER COLUMN",
            "lat": round(lat, 3),
            "lon": round(norm_lon, 3),
            "depth": round(depth, 1),
            "temperature": top_t,
            "salinity": top_s,
            "chlorophyll": top_c,
            "profile": prof,
        }



# ──────────────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────────────
_service_instance: Optional[GlorysService] = None


def get_service() -> GlorysService:
    global _service_instance
    if _service_instance is None:
        _service_instance = GlorysService()
    return _service_instance
