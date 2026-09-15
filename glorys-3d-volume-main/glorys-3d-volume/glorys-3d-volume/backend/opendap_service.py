"""
opendap_service.py

Production-grade lazy remote OPeNDAP reader for THREDDS-served 3D ocean datasets.
Supports:
  - Multi-URL variable aggregation (temperature, salinity, u-current, v-current)
  - Dynamic coordinate normalization (0..360 vs -180..180 lon, ascending/descending lat, positive depth)
  - Physical unit normalization (Kelvin -> degC, kg/kg -> PSU)
  - Direct model variables (temperature, salinity, current components)
  - Derived physical ocean metrics (Mackenzie 1981 sound speed, UNESCO 1981 sigma-theta density, current speed)
  - Binary wire protocol identical to glorys_service._pack_binary_payload

Environment Endpoints (.env):
  OPENDAP_URL        - Primary 3D dataset URL (e.g. NOAA GODAS pottmp.2023.nc or INCOIS THREDDS)
  OPENDAP_SALT_URL   - Salinity 3D dataset URL (e.g. NOAA GODAS salt.2023.nc)
  OPENDAP_UCUR_URL   - Zonal current 3D dataset URL (e.g. NOAA GODAS ucur.2023.nc)
  OPENDAP_VCUR_URL   - Meridional current 3D dataset URL (e.g. NOAA GODAS vcur.2023.nc)
"""

from __future__ import annotations

import concurrent.futures
import functools
import hashlib
import json
import logging
import os
import socket
import struct
import urllib.request
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Strict global socket timeout — caps ALL blocking socket.connect() /
# socket.recv() calls process-wide, including inside netCDF4 and pydap C
# extensions that ignore higher-level request timeouts.
# ---------------------------------------------------------------------------
socket.setdefaulttimeout(2.0)

logger = logging.getLogger("opendap_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[OPENDAP] %(levelname)s - %(message)s"))
    logger.addHandler(_ch)

# ---------------------------------------------------------------------------
# Default verified 3D Ocean Endpoints (NOAA GODAS 40-level Reanalysis)
# ---------------------------------------------------------------------------
DEFAULT_TEMP_URL = "https://psl.noaa.gov/thredds/dodsC/Datasets/godas/pottmp.2023.nc"
DEFAULT_SALT_URL = "https://psl.noaa.gov/thredds/dodsC/Datasets/godas/salt.2023.nc"
DEFAULT_UCUR_URL = "https://psl.noaa.gov/thredds/dodsC/Datasets/godas/ucur.2023.nc"
DEFAULT_VCUR_URL = "https://psl.noaa.gov/thredds/dodsC/Datasets/godas/vcur.2023.nc"

def get_configured_candidate_urls(role: str) -> List[str]:
    """
    Returns an ordered priority list of candidate OPeNDAP endpoints for the given role:
      1. Primary 6,000m model (NASA ECCO V4r4 via OPENDAP_URL / OPENDAP_CURRENTS_URL)
      2. Fallback 1: HYCOM GOFS 3.1 5,000m abyssal model (OPENDAP_HYCOM_TS / OPENDAP_HYCOM_UV)
      3. Fallback 2: NOAA GODAS 4,478m model (OPENDAP_FALLBACK_TEMP / OPENDAP_FALLBACK_SALT / default)
    """
    raw_list: List[Optional[str]] = []
    if role == "temperature":
        raw_list = [
            os.getenv("OPENDAP_URL"),
            os.getenv("OPENDAP_HYCOM_TS"),
            os.getenv("OPENDAP_FALLBACK_TEMP"),
            DEFAULT_TEMP_URL,
        ]
    elif role == "salinity":
        raw_list = [
            os.getenv("OPENDAP_SALT_URL"),
            os.getenv("OPENDAP_URL"),
            os.getenv("OPENDAP_HYCOM_TS"),
            os.getenv("OPENDAP_FALLBACK_SALT"),
            DEFAULT_SALT_URL,
        ]
    elif role == "ucur":
        raw_list = [
            os.getenv("OPENDAP_UCUR_URL"),
            os.getenv("OPENDAP_CURRENTS_URL"),
            os.getenv("OPENDAP_HYCOM_UV"),
            DEFAULT_UCUR_URL,
        ]
    elif role == "vcur":
        raw_list = [
            os.getenv("OPENDAP_VCUR_URL"),
            os.getenv("OPENDAP_CURRENTS_URL"),
            os.getenv("OPENDAP_HYCOM_UV"),
            DEFAULT_VCUR_URL,
        ]
    else:
        raw_list = [
            os.getenv("OPENDAP_URL"),
            os.getenv("OPENDAP_HYCOM_TS"),
            DEFAULT_TEMP_URL,
        ]

    # Deduplicate while preserving order and stripping whitespace/quotes
    seen = set()
    cleaned = []
    for u in raw_list:
        if not u:
            continue
        cleaned_u = u.strip().strip('"').strip("'")
        if cleaned_u and cleaned_u not in seen:
            seen.add(cleaned_u)
            cleaned.append(cleaned_u)
    return cleaned


def get_configured_url(role: str) -> str:
    """Retrieve top-priority environment-configured OPeNDAP URL."""
    candidates = get_configured_candidate_urls(role)
    return candidates[0] if candidates else DEFAULT_TEMP_URL


# ---------------------------------------------------------------------------
# CF-name alias lists for robust variable discovery
# ---------------------------------------------------------------------------
_TEMP_NAMES  = ["thetao", "temp", "temperature", "sea_water_potential_temperature", "pottmp", "water_temp", "THETA", "theta"]
_SAL_NAMES   = ["so", "salt", "salinity", "sea_water_salinity", "SALT", "sal"]
_U_NAMES     = ["uo", "u", "eastward_sea_water_velocity", "ucur", "water_u", "UVEL", "uvel"]
_V_NAMES     = ["vo", "v", "northward_sea_water_velocity", "vcur", "water_v", "VVEL", "vvel"]
_LAT_NAMES   = ["latitude", "lat", "nav_lat", "y", "YC", "yc"]
_LON_NAMES   = ["longitude", "lon", "nav_lon", "x", "XC", "xc"]
_DEPTH_NAMES = ["depth", "lev", "level", "deptht", "z_l", "depth_full", "pres", "Z", "k", "Zl", "Zu"]
_TIME_NAMES  = ["time", "TIME", "t", "time_step", "step"]

# ---------------------------------------------------------------------------
# Display metadata for each OPeNDAP-sourced variable
# ---------------------------------------------------------------------------
OPENDAP_VARIABLE_META: Dict[str, Dict[str, Any]] = {
    "temperature": {
        "unit":          "degC",
        "label":         "Potential Temperature",
        "default_range": [-2.0, 35.0],
        "is_2d":         False,
    },
    "salinity": {
        "unit":          "PSU",
        "label":         "Practical Salinity",
        "default_range": [30.0, 40.0],
        "is_2d":         False,
    },
    "current_speed": {
        "unit":          "m/s",
        "label":         "Current Speed",
        "default_range": [0.0, 1.5],
        "is_2d":         False,
    },
    "sound_speed": {
        "unit":          "m/s",
        "label":         "Sound Speed (Mackenzie 1981)",
        "default_range": [1450.0, 1550.0],
        "is_2d":         False,
    },
    "density": {
        "unit":          "kg/m3",
        "label":         "Seawater Density Anomaly (sigma-theta)",
        "default_range": [21.0, 30.0],
        "is_2d":         False,
    },
}

ALLOWED_OPENDAP_VARIABLES: frozenset = frozenset(OPENDAP_VARIABLE_META.keys())
_OPENDAP_DATASET_ID = "opendap_remote"


# ===========================================================================
# Physical formula implementations
# ===========================================================================

def compute_sound_speed(temp_c: np.ndarray, sal_psu: np.ndarray, depth_m: np.ndarray) -> np.ndarray:
    """
    Mackenzie (1981) underwater sound speed.
    c = 1448.96 + 4.591T - 5.304e-2 T^2 + 2.374e-4 T^3
        + 1.340(S-35) + 1.630e-2 D + 1.675e-7 D^2
        - 1.025e-2 T(S-35) - 7.139e-13 T D^3
    T[degC], S[PSU], D[m] -> c[m/s]
    """
    T = temp_c.astype(np.float64)
    S = sal_psu.astype(np.float64)
    D = depth_m.astype(np.float64)
    c = (
        1448.96
        + 4.591 * T
        - 5.304e-2 * T**2
        + 2.374e-4 * T**3
        + 1.340 * (S - 35.0)
        + 1.630e-2 * D
        + 1.675e-7 * D**2
        - 1.025e-2 * T * (S - 35.0)
        - 7.139e-13 * T * D**3
    )
    return c.astype(np.float32)


def compute_density_anomaly(temp_c: np.ndarray, sal_psu: np.ndarray, depth_m: np.ndarray) -> np.ndarray:
    """
    Simplified UNESCO (1981) potential density anomaly sigma-theta [kg/m^3 - 1000].
    Error < 0.5 kg/m^3 over oceanic T/S ranges; suitable for visualization.
    """
    T = temp_c.astype(np.float64)
    S = sal_psu.astype(np.float64)

    rho_w = (
        999.842594
        + 6.793952e-2 * T
        - 9.095290e-3 * T**2
        + 1.001685e-4 * T**3
        - 1.120083e-6 * T**4
        + 6.536332e-9 * T**5
    )
    A = (
        8.24493e-1
        - 4.0899e-3 * T
        + 7.6438e-5 * T**2
        - 8.2467e-7 * T**3
        + 5.3875e-9 * T**4
    )
    B = -5.72466e-3 + 1.0227e-4 * T - 1.6546e-6 * T**2
    C = 4.8314e-4

    rho = rho_w + A * S + B * S**1.5 + C * S**2
    return (rho - 1000.0).astype(np.float32)


# ===========================================================================
# Internal helpers & dataset caching
# ===========================================================================

_DS_CACHE: Dict[str, Any] = {}

def _find_var(ds: Any, candidates: List[str]) -> Optional[Any]:
    for name in candidates:
        if name in ds.data_vars or name in ds.variables:
            return ds[name]
    return None


def _require_var(ds: Any, candidates: List[str], role: str) -> Any:
    da = _find_var(ds, candidates)
    if da is None:
        raise RuntimeError(
            f"Could not locate '{role}' variable in dataset. "
            f"Tried: {candidates}. Available: {list(ds.data_vars)}"
        )
    return da


def _find_coord(ds: Any, candidates: List[str]) -> Optional[str]:
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    return None


# Thread pool used to enforce hard per-engine open timeouts regardless of
# whether the underlying C library honours socket.setdefaulttimeout().
_OPEN_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="opendap-open")
_OPEN_TIMEOUT = 2.5  # seconds — hard deadline for a single engine attempt


def _open_ds(url: str) -> Any:
    """
    Open remote OPeNDAP dataset lazily with caching and engine fallback.

    Uses two layers of timeout protection:
      1. socket.setdefaulttimeout(2.0) — caps OS-level socket I/O globally.
      2. ThreadPoolExecutor.submit(...).result(timeout=2.5) — hard deadline
         even if a C extension bypasses the socket-level default.
    """
    if url in _DS_CACHE:
        return _DS_CACHE[url]

    import xarray as xr

    # ── Helper to run an open call in a worker thread with a hard timeout ──
    def _run_with_timeout(fn, *args, **kwargs):
        future = _OPEN_EXECUTOR.submit(fn, *args, **kwargs)
        return future.result(timeout=_OPEN_TIMEOUT)

    # 1. Try netcdf4 engine (fast native C DAP2 / THREDDS)
    e_nc_msg = ""
    try:
        ds = _run_with_timeout(
            xr.open_dataset, url, engine="netcdf4", decode_times=False
        )
        _DS_CACHE[url] = ds
        return ds
    except concurrent.futures.TimeoutError:
        e_nc_msg = f"netcdf4 engine timed out after {_OPEN_TIMEOUT}s"
        logger.warning(f"[OPENDAP] {e_nc_msg} for {url}. Falling back to pydap...")
    except Exception as e_nc:
        e_nc_msg = str(e_nc)
        logger.warning(f"[OPENDAP] netcdf4 engine failed for {url}: {e_nc}. Falling back to pydap...")

    # 2. Fall back to pydap engine
    pydap_url = url
    if pydap_url.startswith("https://"):
        pydap_url = "dap2://" + pydap_url[len("https://"):]
    elif pydap_url.startswith("http://"):
        pydap_url = "dap2://" + pydap_url[len("http://"):]

    def _open_pydap():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return xr.open_dataset(pydap_url, engine="pydap", cache=False, decode_times=False)

    try:
        ds = _run_with_timeout(_open_pydap)
        _DS_CACHE[url] = ds
        return ds
    except concurrent.futures.TimeoutError as e_py:
        raise RuntimeError(
            f"Failed to open OPeNDAP dataset at {url}: "
            f"netcdf4 ({e_nc_msg}), pydap (timed out after {_OPEN_TIMEOUT}s)"
        ) from e_py
    except Exception as e_py:
        raise RuntimeError(
            f"Failed to open OPeNDAP dataset at {url}: netcdf4 ({e_nc_msg}), pydap ({e_py})"
        ) from e_py


def _probe_endpoint(url: str, timeout: float = 1.5) -> bool:
    """Preflight check candidate URL so we never hang on broken or 503 endpoints."""
    try:
        req_url = url.rstrip("/")
        if not req_url.endswith((".dds", ".das", ".html")):
            req_url += ".dds"
        req = urllib.request.Request(req_url, headers={"User-Agent": "GLORYS-3D-Client/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _open_ds_with_fallback(candidate_urls: List[str]) -> Tuple[Any, str]:
    """
    Attempts to open candidate OPeNDAP datasets in priority order:
      1. Primary 6,000m model (NASA ECCO V4r4)
      2. Fallback 1 (HYCOM GOFS 3.1 down to 5,000m)
      3. Fallback 2 (NOAA GODAS down to 4,478m)
    Returns (dataset, successful_url).
    """
    errors: List[str] = []
    for url in candidate_urls:
        if not url:
            continue
        if not _probe_endpoint(url, timeout=1.5):
            logger.warning(f"[OPENDAP] Candidate endpoint preflight check failed or timed out ({url}). Skipping...")
            errors.append(f"{url} (Preflight failed or timed out)")
            continue
        try:
            logger.info(f"[OPENDAP] Connecting to candidate endpoint: {url}")
            ds = _open_ds(url)
            logger.info(f"[OPENDAP] Connected to active endpoint: {url}")
            return ds, url
        except Exception as e:
            logger.warning(f"[OPENDAP] Candidate endpoint failed ({url}): {e}. Trying next fallback...")
            errors.append(f"{url} ({type(e).__name__}: {e})")
    raise RuntimeError(f"All candidate OPeNDAP endpoints failed: {'; '.join(errors)}")


def _slice_and_normalize(
    da: Any,
    lat_min: Optional[float],
    lat_max: Optional[float],
    lon_min: Optional[float],
    lon_max: Optional[float],
    depth_min: Optional[float],
    depth_max: Optional[float],
    stride: int,
    var_type: str = "general",
) -> Tuple[np.ndarray, List[float], List[float], List[float]]:
    """
    Extracts a 3D slab from da with dynamic coordinate normalization:
      - Normalizes longitude domain (0..360 vs -180..180)
      - Resolves latitude ordering (ascending vs descending)
      - Resolves depth orientation (positive downwards)
      - Performs unit conversion (Kelvin -> Celsius, kg/kg -> PSU)
    Returns:
      (arr_3d [depth, lat, lon], depth_vals, lat_vals, lon_vals)
    """
    lat_coord   = _find_coord(da, _LAT_NAMES)
    lon_coord   = _find_coord(da, _LON_NAMES)
    depth_coord = _find_coord(da, _DEPTH_NAMES)
    time_coord  = _find_coord(da, _TIME_NAMES)

    if not lat_coord or not lon_coord:
        raise RuntimeError(f"Cannot identify lat/lon coordinates in variable {da.name}. Present: {list(da.coords)}")

    # 1. Temporal selection (select latest time step if time dimension exists)
    if time_coord and time_coord in da.dims:
        da = da.isel({time_coord: -1})

    # 2. Dynamic Longitude Normalization
    raw_lons = da[lon_coord].values.astype(np.float64)
    is_lon_360 = bool(np.nanmin(raw_lons) >= -0.5 and np.nanmax(raw_lons) > 180.0)

    if is_lon_360:
        # Dataset is in 0..360 domain
        l0 = ((lon_min % 360.0) + 360.0) % 360.0 if lon_min is not None else float(np.nanmin(raw_lons))
        l1 = ((lon_max % 360.0) + 360.0) % 360.0 if lon_max is not None else float(np.nanmax(raw_lons))
        l_min_slice, l_max_slice = min(l0, l1), max(l0, l1)
    else:
        # Dataset is in -180..180 domain
        l_min_slice = lon_min if lon_min is not None else float(np.nanmin(raw_lons))
        l_max_slice = lon_max if lon_max is not None else float(np.nanmax(raw_lons))

    da = da.sel({lon_coord: slice(l_min_slice, l_max_slice)})

    # 3. Dynamic Latitude Normalization
    raw_lats = da[lat_coord].values.astype(np.float64)
    is_lat_descending = bool(len(raw_lats) > 1 and raw_lats[0] > raw_lats[-1])
    la_min = lat_min if lat_min is not None else float(np.nanmin(raw_lats))
    la_max = lat_max if lat_max is not None else float(np.nanmax(raw_lats))

    if is_lat_descending:
        da = da.sel({lat_coord: slice(max(la_min, la_max), min(la_min, la_max))})
    else:
        da = da.sel({lat_coord: slice(min(la_min, la_max), max(la_min, la_max))})

    # 4. Dynamic Depth Normalization
    has_depth = bool(depth_coord and depth_coord in da.dims)
    is_depth_negative = False
    is_depth_descending = False

    if has_depth:
        raw_deps = da[depth_coord].values.astype(np.float64)
        is_depth_negative = bool(np.nanmax(raw_deps) <= 0.0 and np.nanmin(raw_deps) < 0.0)
        is_depth_descending = bool(len(raw_deps) > 1 and raw_deps[0] > raw_deps[-1])

        if is_depth_negative:
            d_min_slice = -abs(depth_max) if depth_max is not None else float(np.nanmin(raw_deps))
            d_max_slice = -abs(depth_min) if depth_min is not None else float(np.nanmax(raw_deps))
        else:
            d_min_slice = abs(depth_min) if depth_min is not None else float(np.nanmin(raw_deps))
            d_max_slice = abs(depth_max) if depth_max is not None else float(np.nanmax(raw_deps))

        if is_depth_descending:
            da = da.sel({depth_coord: slice(max(d_min_slice, d_max_slice), min(d_min_slice, d_max_slice))})
        else:
            da = da.sel({depth_coord: slice(min(d_min_slice, d_max_slice), max(d_min_slice, d_max_slice))})

    # 5. Apply Horizontal Decimation Stride
    da = da.isel({
        lat_coord: slice(None, None, stride),
        lon_coord: slice(None, None, stride),
    })

    # 6. Load Slab into Memory
    logger.info(f"[OPENDAP] Fetching slab for {da.name}: {dict(da.sizes)}")
    arr = da.load().values.astype(np.float32)

    # 7. Coordinate Array Extraction
    lat_vals = [float(v) for v in da[lat_coord].values]
    lon_vals = [float(v) for v in da[lon_coord].values]
    if has_depth:
        depth_vals = [abs(float(v)) for v in da[depth_coord].values]
    else:
        depth_vals = [0.0]

    # Ensure strictly 3D shape: (depth, lat, lon)
    arr = np.squeeze(arr)
    if not has_depth or arr.ndim == 2:
        arr = arr[np.newaxis, ...]

    # 8. Coordinate Orientation Alignment (Standardize for Three.js VolumeViewer)
    # Latitude: must be ascending (South -> North along axis 1)
    if is_lat_descending and len(lat_vals) > 1:
        arr = np.flip(arr, axis=1)
        lat_vals = lat_vals[::-1]

    # Depth: must be surface downwards (axis 0: index 0 = surface)
    if is_depth_descending and len(depth_vals) > 1:
        arr = np.flip(arr, axis=0)
        depth_vals = depth_vals[::-1]

    # Normalize longitude in returned coordinate array to continuous standard degrees
    if is_lon_360 and lon_min is not None and lon_min < 0:
        lon_vals = [((x + 180.0) % 360.0) - 180.0 for x in lon_vals]

    # 9. Clean Masked & Sentinel Values
    arr[arr > 1e15]  = np.nan
    arr[arr < -1e15] = np.nan
    arr[arr == -999.0] = np.nan
    arr[arr < -900.0] = np.nan

    # 10. Physical Unit Normalization
    if var_type in ("temperature", "pottmp"):
        # Detect Kelvin (ocean water in Kelvin is ~271K to 310K)
        valid_sample = arr[~np.isnan(arr)]
        if valid_sample.size and np.nanmedian(valid_sample) > 100.0:
            logger.info("[OPENDAP] Normalizing temperature from Kelvin -> Celsius (-273.15)")
            arr = arr - 273.15
    elif var_type in ("salinity", "salt"):
        # Detect kg/kg (ocean salinity is ~0.030 to 0.040 kg/kg -> 30..40 PSU)
        valid_sample = arr[~np.isnan(arr)]
        if valid_sample.size and 0.0 < np.nanmedian(valid_sample) < 1.0:
            logger.info("[OPENDAP] Normalizing salinity from kg/kg -> PSU (* 1000.0)")
            arr = arr * 1000.0

    return arr, depth_vals, lat_vals, lon_vals


# ===========================================================================
# Public Extraction API
# ===========================================================================

def extract_volume(
    variable: str,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lon_min: Optional[float] = None,
    lon_max: Optional[float] = None,
    depth_min: Optional[float] = None,
    depth_max: Optional[float] = None,
    downsample_stride: int = 1,
    opendap_url: Optional[str] = None,
    opendap_salt_url: Optional[str] = None,
    opendap_ucur_url: Optional[str] = None,
    opendap_vcur_url: Optional[str] = None,
) -> bytes:
    """
    Extract a 3D ocean volume across single or multi-URL OPeNDAP datasets,
    perform coordinate normalization, unit conversions, and derived metric computation.
    Supports multi-tier fallback (NASA ECCO 6,000m -> HYCOM 5,000m -> NOAA GODAS 4,478m).
    Returns binary payload identical to glorys_service.
    """
    variable = variable.strip().lower()
    if variable not in ALLOWED_OPENDAP_VARIABLES:
        raise ValueError(f"Unknown variable '{variable}'. Allowed: {sorted(ALLOWED_OPENDAP_VARIABLES)}")

    import time
    start_t = time.time()
    print(f"[DIAG-START] Querying volume for bounds: lat({lat_min}..{lat_max}), lon({lon_min}..{lon_max})")

    logger.info(
        f"[OPENDAP] extract_volume('{variable}') bbox: "
        f"lon=[{lon_min},{lon_max}], lat=[{lat_min},{lat_max}], depth=[{depth_min},{depth_max}], stride={downsample_stride}"
    )

    arr: np.ndarray
    depth_vals: List[float]
    lat_vals: List[float]
    lon_vals: List[float]
    source_url: str

    if variable == "temperature":
        candidates = [opendap_url] if opendap_url else get_configured_candidate_urls("temperature")
        ds, source_url = _open_ds_with_fallback(candidates)
        da = _require_var(ds, _TEMP_NAMES, "temperature")
        arr, depth_vals, lat_vals, lon_vals = _slice_and_normalize(
            da, lat_min, lat_max, lon_min, lon_max, depth_min, depth_max, downsample_stride, "temperature"
        )

    elif variable == "salinity":
        candidates = [opendap_salt_url] if opendap_salt_url else get_configured_candidate_urls("salinity")
        ds, source_url = _open_ds_with_fallback(candidates)
        da = _require_var(ds, _SAL_NAMES, "salinity")
        arr, depth_vals, lat_vals, lon_vals = _slice_and_normalize(
            da, lat_min, lat_max, lon_min, lon_max, depth_min, depth_max, downsample_stride, "salinity"
        )

    elif variable in ("sound_speed", "density"):
        candidates_t = [opendap_url] if opendap_url else get_configured_candidate_urls("temperature")
        candidates_s = [opendap_salt_url] if opendap_salt_url else get_configured_candidate_urls("salinity")
        ds_t, src_t = _open_ds_with_fallback(candidates_t)
        ds_s, src_s = _open_ds_with_fallback(candidates_s)
        source_url = f"{src_t} + {src_s}"

        da_t = _require_var(ds_t, _TEMP_NAMES, "temperature")
        arr_t, depth_vals, lat_vals, lon_vals = _slice_and_normalize(
            da_t, lat_min, lat_max, lon_min, lon_max, depth_min, depth_max, downsample_stride, "temperature"
        )

        da_s = _require_var(ds_s, _SAL_NAMES, "salinity")
        arr_s, _, _, _ = _slice_and_normalize(
            da_s, lat_min, lat_max, lon_min, lon_max, depth_min, depth_max, downsample_stride, "salinity"
        )

        # Align shapes if slight pixel disparity exists
        min_z = min(arr_t.shape[0], arr_s.shape[0])
        min_y = min(arr_t.shape[1], arr_s.shape[1])
        min_x = min(arr_t.shape[2], arr_s.shape[2])

        arr_t = arr_t[:min_z, :min_y, :min_x]
        arr_s = arr_s[:min_z, :min_y, :min_x]
        depth_vals = depth_vals[:min_z]
        lat_vals = lat_vals[:min_y]
        lon_vals = lon_vals[:min_x]

        depth_arr = np.array(depth_vals, dtype=np.float64)
        D = depth_arr[:, np.newaxis, np.newaxis] * np.ones_like(arr_t, dtype=np.float64)

        if variable == "sound_speed":
            arr = compute_sound_speed(arr_t, arr_s, D)
        else:
            arr = compute_density_anomaly(arr_t, arr_s, D)

    elif variable == "current_speed":
        candidates_u = [opendap_ucur_url] if opendap_ucur_url else get_configured_candidate_urls("ucur")
        candidates_v = [opendap_vcur_url] if opendap_vcur_url else get_configured_candidate_urls("vcur")
        ds_u, src_u = _open_ds_with_fallback(candidates_u)
        ds_v, src_v = _open_ds_with_fallback(candidates_v)
        source_url = f"{src_u} + {src_v}"

        da_u = _require_var(ds_u, _U_NAMES, "zonal current (uo)")
        arr_u, depth_vals, lat_vals, lon_vals = _slice_and_normalize(
            da_u, lat_min, lat_max, lon_min, lon_max, depth_min, depth_max, downsample_stride, "general"
        )

        da_v = _require_var(ds_v, _V_NAMES, "meridional current (vo)")
        arr_v, _, _, _ = _slice_and_normalize(
            da_v, lat_min, lat_max, lon_min, lon_max, depth_min, depth_max, downsample_stride, "general"
        )

        min_z = min(arr_u.shape[0], arr_v.shape[0])
        min_y = min(arr_u.shape[1], arr_v.shape[1])
        min_x = min(arr_u.shape[2], arr_v.shape[2])

        arr_u = arr_u[:min_z, :min_y, :min_x]
        arr_v = arr_v[:min_z, :min_y, :min_x]
        depth_vals = depth_vals[:min_z]
        lat_vals = lat_vals[:min_y]
        lon_vals = lon_vals[:min_x]

        arr = np.sqrt(arr_u**2 + arr_v**2).astype(np.float32)
        arr[np.isnan(arr_u) | np.isnan(arr_v)] = np.nan
    else:
        raise ValueError(f"Unhandled variable '{variable}'")

    return _pack_binary(arr, depth_vals, lat_vals, lon_vals, variable, source_url)


# ===========================================================================
# Binary Packing Helper
# ===========================================================================

def _pack_binary(
    arr: np.ndarray,
    depth_vals: List[float],
    lat_vals: List[float],
    lon_vals: List[float],
    variable: str,
    url: str,
) -> bytes:
    var_info = OPENDAP_VARIABLE_META[variable]

    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]  # ensure (depth, lat, lon)

    valid = arr[~np.isnan(arr)]
    v_min = float(valid.min()) if valid.size else float(var_info["default_range"][0])
    v_max = float(valid.max()) if valid.size else float(var_info["default_range"][1])

    raw_bytes    = np.ascontiguousarray(arr, dtype=np.float32).tobytes()
    payload_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

    metadata: Dict[str, Any] = {
        "dataset":         _OPENDAP_DATASET_ID,
        "variable":        variable,
        "units":           var_info["unit"],
        "label":           var_info["label"],
        "is_2d":           False,
        "date":            None,
        "mode":            "opendap",
        "source_url":      url,
        "lod":             1,
        "strides":         {"lat": 1, "lon": 1, "depth": 1},
        "shape":           {"depth": int(arr.shape[0]), "lat": int(arr.shape[1]), "lon": int(arr.shape[2])},
        "depth":           depth_vals,
        "latitude":        lat_vals,
        "longitude":       lon_vals,
        "depth_min":       float(min(depth_vals)) if depth_vals else 0.0,
        "depth_max":       float(max(depth_vals)) if depth_vals else 1000.0,
        "latitude_min":    float(min(lat_vals))   if lat_vals   else -80.0,
        "latitude_max":    float(max(lat_vals))   if lat_vals   else 90.0,
        "longitude_min":   float(min(lon_vals))   if lon_vals   else -180.0,
        "longitude_max":   float(max(lon_vals))   if lon_vals   else 180.0,
        "value_min":       v_min,
        "value_max":       v_max,
        "temperature_min": v_min,   # backward-compat alias
        "temperature_max": v_max,
        "byte_length":     len(raw_bytes),
        "payload_hash":    payload_hash,
        "nan_sentinel":    "NaN (IEEE754)",
    }

    logger.info(
        f"[OPENDAP] Packed {variable}: "
        f"{metadata['shape']['depth']}x{metadata['shape']['lat']}x{metadata['shape']['lon']} "
        f"({len(raw_bytes)/1024/1024:.3f} MB float32) range=[{v_min:.2f}..{v_max:.2f}] hash={payload_hash}"
    )

    meta_json = json.dumps(metadata).encode("utf-8")
    header    = struct.pack(">I", len(meta_json))
    return header + meta_json + raw_bytes


# ===========================================================================
# Live OPeNDAP Chlorophyll-a Streaming Pipeline
# ===========================================================================

NOAA_CHLA_ENDPOINT = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisVHNnoaaSNPPnoaa20NRTchlaGapfilledDaily"


@functools.lru_cache(maxsize=128)
def _fetch_cached_chlorophyll(
    rounded_lat: float,
    rounded_lon: float,
    depths_tuple: Tuple[float, ...],
) -> List[float]:
    """
    Internal LRU-cached query:
      1. Performs lightweight byte-range query to NOAA CoastWatch VIIRS OPeNDAP/ERDDAP gateway
         for real-time surface Chlorophyll-a (last available daily composite, gap-filled DINEOF).
      2. Projects the live surface concentration into a 3D subsurface column across the euphotic
         zone with a distinct Deep Chlorophyll Maximum (DCM) based on latitude stratification.
      3. For depths > 200m (below photic zone), tapers residual concentration down to baseline (~0.01 mg/m³).
      4. Falls back gracefully to biophysical climatology on network timeout or land mask.
    """
    # 1. Normalize longitude to [-180, 180]
    norm_lon = rounded_lon
    while norm_lon < -180.0:
        norm_lon += 360.0
    while norm_lon > 180.0:
        norm_lon -= 360.0

    c_surf: Optional[float] = None

    # 2. Query live NOAA CoastWatch Near Real-Time Gap-Filled VIIRS gateway
    query_url = f"{NOAA_CHLA_ENDPOINT}.json?chlor_a[(last)][(0.0)][({rounded_lat:.2f})][({norm_lon:.2f})]"
    try:
        req = urllib.request.Request(
            query_url,
            headers={"User-Agent": "GLORYS-3D-Ocean-Viewer/1.0 (OPeNDAP-Profile-Service)"},
        )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rows = data.get("table", {}).get("rows", [])
            if rows and len(rows[0]) >= 5:
                raw_val = rows[0][4]
                if raw_val is not None:
                    parsed = float(raw_val)
                    if not np.isnan(parsed) and 0.005 <= parsed <= 35.0:
                        c_surf = parsed
                        logger.info(
                            f"[OPENDAP-CHL] Successfully streamed live Chlorophyll-a at ({rounded_lat}, {norm_lon}): {c_surf:.4f} mg/m³"
                        )
    except Exception as e:
        logger.warning(
            f"[OPENDAP-CHL] Live OPeNDAP query failed ({query_url}): {e}. Falling back to biophysical model."
        )

    # 3. If live query was unviable or coordinate was on land mask, evaluate biophysical baseline
    if c_surf is None:
        abs_lat = abs(rounded_lat)
        if abs_lat > 50.0:
            c_surf = 1.1 + 0.4 * np.cos(np.radians(rounded_lat * 2))
        elif abs_lat < 20.0:
            c_surf = 0.38 + 0.12 * np.sin(np.radians(abs_lat * 4))
        else:
            c_surf = 0.18 + 0.08 * np.cos(np.radians(abs_lat))

    # 4. Project across the vertical water column
    abs_lat = abs(rounded_lat)
    if abs_lat > 40.0:
        z_dcm = 35.0
        sigma = 20.0
        peak_factor = 1.6
    elif abs_lat < 20.0:
        z_dcm = 65.0
        sigma = 25.0
        peak_factor = 1.45
    else:
        z_dcm = 80.0
        sigma = 30.0
        peak_factor = 1.3

    c_peak = c_surf * peak_factor
    results: List[float] = []

    for d in depths_tuple:
        z = float(d)
        if z <= 0.0:
            val = c_surf
        elif z <= 200.0:
            # Euphotic zone: surface decay + Gaussian DCM peak
            dcm_term = (c_peak - c_surf * 0.75) * np.exp(-((z - z_dcm) ** 2) / (2.0 * (sigma ** 2)))
            background = c_surf * np.exp(-0.007 * z)
            val = background + dcm_term
        else:
            # Below photic zone (>200m): exponentially taper toward oceanic baseline (~0.01 mg/m³)
            dcm_at_200 = (c_peak - c_surf * 0.75) * np.exp(-((200.0 - z_dcm) ** 2) / (2.0 * (sigma ** 2)))
            val_at_200 = c_surf * np.exp(-0.007 * 200.0) + dcm_at_200
            val = 0.01 + (val_at_200 - 0.01) * np.exp(-(z - 200.0) / 35.0)

        # Physical safety clamp
        val = max(0.01, min(10.0, float(val)))
        if z >= 500.0:
            val = 0.01  # Baseline oceanic threshold

        results.append(round(val, 3))

    return results


def fetch_opendap_chlorophyll(lat: float, lon: float, depths: List[float]) -> List[float]:
    """
    Public entry point for live streaming Chlorophyll-a vertical profile.
    Fast, thread-safe, and cached via LRU cache on (lat, lon).
    """
    rounded_lat = round(float(lat), 2)
    rounded_lon = round(float(lon), 2)
    depths_tuple = tuple(float(d) for d in depths)
    return _fetch_cached_chlorophyll(rounded_lat, rounded_lon, depths_tuple)

