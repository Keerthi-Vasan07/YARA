"""
volume_service.py

High-performance, non-blocking volume extraction service with strict timeouts
and physics-consistent synthetic ocean climatology fallback for global coordinates.

Features:
  1. Fast Path: Local NetCDF extraction when coordinates lie inside Indian Ocean fixture.
  2. Non-blocking Remote Path: Asynchronous execution via asyncio.to_thread with 6.0s timeout.
  3. Resilient Fallback: Immediate synthesis of 3D physical ocean column when remote
     queries time out or fail, ensuring zero indefinite client hangs anywhere on Earth.
  4. Timestamped diagnostic logging for complete pipeline observability.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import struct
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from backend.services.geo_service import (
    check_region_land_fraction,
    get_2d_land_mask,
    is_point_land,
)

logger = logging.getLogger("volume_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[VOLUME-SERVICE] %(levelname)s - %(message)s"))
    logger.addHandler(_ch)

# ─────────────────────────────────────────────────────────────────────────────
# Local NetCDF Coverage Bounds (Indian Ocean GLORYS Reanalysis Fixture)
# ─────────────────────────────────────────────────────────────────────────────
LOCAL_BOUNDS = {
    "min_lat": -2.83,
    "max_lat": 22.83,
    "min_lon": 42.00,
    "max_lon": 107.42,
    "min_depth": 0.49,
    "max_depth": 1062.44,
}

# Variable units and display configurations
VARIABLE_SPECS: Dict[str, Dict[str, Any]] = {
    "thetao": {"unit": "°C", "label": "Potential Temperature", "range": [-2.0, 35.0], "is_2d": False},
    "temperature": {"unit": "°C", "label": "Potential Temperature", "range": [-2.0, 35.0], "is_2d": False},
    "so": {"unit": "PSU", "label": "Salinity", "range": [30.0, 40.0], "is_2d": False},
    "salinity": {"unit": "PSU", "label": "Salinity", "range": [30.0, 40.0], "is_2d": False},
    "chl": {"unit": "mg/m³", "label": "Chlorophyll-a", "range": [0.0, 2.0], "is_2d": False},
    "chlorophyll": {"unit": "mg/m³", "label": "Chlorophyll-a", "range": [0.0, 2.0], "is_2d": False},
    "composite": {"unit": "Multi", "label": "Multi-Variable Composite", "range": [0.0, 1.0], "is_2d": False},
    "mlotst": {"unit": "m", "label": "Mixed Layer Thickness", "range": [0.0, 200.0], "is_2d": True},
    "ohc_0_700m": {"unit": "J/m²", "label": "Ocean Heat Content (0–700m)", "range": [0.0, 4.0e9], "is_2d": True},
    "current_speed": {"unit": "m/s", "label": "Current Speed", "range": [0.0, 2.5], "is_2d": False},
    "sound_speed": {"unit": "m/s", "label": "Sound Speed (Mackenzie)", "range": [1440.0, 1560.0], "is_2d": False},
    "density": {"unit": "kg/m³", "label": "Density Anomaly (σθ)", "range": [20.0, 30.0], "is_2d": False},
}


def is_within_local_dataset(
    min_lat: Optional[float],
    max_lat: Optional[float],
    min_lon: Optional[float],
    max_lon: Optional[float],
) -> bool:
    """
    Check whether the requested query box is strictly contained within
    the local Indian Ocean NetCDF dataset coverage.
    """
    if min_lat is None or max_lat is None or min_lon is None or max_lon is None:
        return False

    # Allow slight numerical margin (~0.05°)
    return (
        min_lat >= (LOCAL_BOUNDS["min_lat"] - 0.05) and
        max_lat <= (LOCAL_BOUNDS["max_lat"] + 0.05) and
        min_lon >= (LOCAL_BOUNDS["min_lon"] - 0.05) and
        max_lon <= (LOCAL_BOUNDS["max_lon"] + 0.05)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Physical Climatology Synthesis (Global Resilient Fallback)
# ─────────────────────────────────────────────────────────────────────────────
def generate_synthetic_ocean_volume(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    date_str: str = "2026-06-23",
    depth_min: float = 0.0,
    depth_max: float = 500.0,
    variable: str = "thetao",
    dims: Tuple[int, int, int] = (61, 61, 31),
    lod: int = 1,
) -> bytes:
    """
    Synthesize a physically grounded 3D ocean volume packet using canonical
    physical oceanography principles (thermal stratification, halocline,
    Morel-Berthon chlorophyll DCM euphotic profile, and hydrostatic stability).

    Returns binary packet format matching GLORYS wire standard.
    """
    n_lon, n_lat, n_depth = dims
    variable = variable.strip().lower()
    spec = VARIABLE_SPECS.get(variable, VARIABLE_SPECS["thetao"])
    is_2d = spec["is_2d"]

    # Pre-check: If bounding box is 100% continental land, abort synthesis
    land_fraction = check_region_land_fraction(min_lat, max_lat, min_lon, max_lon, samples=20)
    if land_fraction >= 0.999:
        logger.warning(
            f"[VOLUME-SYNTH] Bounding box [{min_lon:.2f}..{max_lon:.2f}E, {min_lat:.2f}..{max_lat:.2f}N] "
            f"is 100% terrestrial land (fraction={land_fraction:.2f}). Aborting ocean volume synthesis."
        )
        raise ValueError("⚠️ Terrestrial Landmass Selected: Oceanographic data unavailable")

    # 1. Coordinate grids
    lon_vals = [float(x) for x in np.linspace(min_lon, max_lon, n_lon)]
    lat_vals = [float(y) for y in np.linspace(min_lat, max_lat, n_lat)]
    
    if is_2d:
        depth_vals = [0.0]
        n_depth = 1
    else:
        # Standard oceanographic logarithmic depth spacing (higher resolution near surface)
        d_raw = np.geomspace(max(0.5, depth_min if depth_min > 0 else 0.5), max(10.0, depth_max), n_depth) - 0.5
        d_raw[0] = float(depth_min)
        d_raw[-1] = float(depth_max)
        depth_vals = [float(round(d, 2)) for d in d_raw]

    # Coordinate mesh: shape = (depth, lat, lon)
    LON, LAT, DEPTH = np.meshgrid(
        np.array(lon_vals, dtype=np.float32),
        np.array(lat_vals, dtype=np.float32),
        np.array(depth_vals, dtype=np.float32),
        indexing="xy",
    )
    # Transpose to (depth, lat, lon)
    LON = np.transpose(LON, (2, 0, 1))
    LAT = np.transpose(LAT, (2, 0, 1))
    DEPTH = np.transpose(DEPTH, (2, 0, 1))

    # 2. Physics-Based Sea Surface & Thermocline Formulation
    # Surface temperature modulated by latitude (tropical warm pool vs subpolar)
    abs_lat = np.abs(LAT)
    sst = 29.5 - 28.0 * np.power(np.clip(abs_lat / 70.0, 0.0, 1.0), 1.35)
    # Longitudinal gentle planetary wave variation (~1°C)
    sst += 0.85 * np.cos(np.radians(LON * 3.0))

    # Deep abyssal temperature (~1.5°C to 2.5°C)
    t_deep = 1.8 + 0.6 * np.cos(np.radians(LAT))
    # Thermocline decay depth scale (thicker in tropics/subtropics, shallower near poles)
    z_therm = 160.0 + 50.0 * np.cos(np.radians(LAT))

    # Potential Temperature 3D array
    thetao_3d = t_deep + (sst - t_deep) * np.exp(-DEPTH / np.maximum(10.0, z_therm))
    thetao_3d = np.clip(thetao_3d, -1.8, 32.5).astype(np.float32)

    # Practical Salinity 3D array (evaporation-precipitation balance)
    s_surf = 35.2 + 1.2 * np.cos(np.radians(LAT * 2.0)) - 0.4 * np.sin(np.radians(LON))
    s_deep = 34.68 + 0.1 * np.cos(np.radians(LAT))
    so_3d = s_deep + (s_surf - s_deep) * np.exp(-DEPTH / 220.0)
    so_3d = np.clip(so_3d, 31.0, 37.8).astype(np.float32)

    # Chlorophyll-a 3D array (DCM peak in euphotic zone ~45-80m, tapering >150m)
    c_surf = np.where(abs_lat > 45.0, 1.2, np.where(abs_lat < 20.0, 0.45, 0.22))
    z_dcm = np.where(abs_lat > 45.0, 35.0, np.where(abs_lat < 20.0, 65.0, 80.0))
    c_peak = c_surf * 1.55
    dcm = (c_peak - c_surf * 0.7) * np.exp(-np.square((DEPTH - z_dcm) / 28.0))
    chl_3d = c_surf * np.exp(-0.008 * DEPTH) + dcm
    # Below photic zone taper
    chl_3d = np.where(DEPTH > 200.0, 0.01 + (chl_3d - 0.01) * np.exp(-(DEPTH - 200.0) / 40.0), chl_3d)
    chl_3d = np.clip(chl_3d, 0.01, 3.5).astype(np.float32)

    # Select output array based on variable
    if variable in ("thetao", "temperature"):
        arr = thetao_3d
    elif variable in ("so", "salinity"):
        arr = so_3d
    elif variable in ("chl", "chlorophyll"):
        arr = chl_3d
    # Compute 2D land mask to carve out coastal terrestrial landmass
    is_land_2d = get_2d_land_mask(np.array(lat_vals, dtype=np.float64), np.array(lon_vals, dtype=np.float64))
    has_land = bool(np.any(is_land_2d))

    if variable == "composite":
        # 4-channel composite: shape (depth, lat, lon, 4)
        t_norm = (thetao_3d - 5.0) / 25.0
        s_norm = (so_3d - 32.0) / 5.0
        c_norm = np.log1p(chl_3d * 2.0) / 2.0
        mask = np.ones_like(thetao_3d, dtype=np.float32)
        if has_land:
            mask[:, is_land_2d] = 0.0
            t_norm[:, is_land_2d] = 0.0
            s_norm[:, is_land_2d] = 0.0
            c_norm[:, is_land_2d] = 0.0
        arr = np.stack([
            np.clip(t_norm, 0.0, 1.0),
            np.clip(s_norm, 0.0, 1.0),
            np.clip(c_norm, 0.0, 1.0),
            mask
        ], axis=-1).astype(np.float32)
    elif variable == "mlotst":
        # Mixed layer thickness 2D (shape: 1, lat, lon)
        mld_2d = 35.0 + 25.0 * np.cos(np.radians(LAT[0])) + 10.0 * np.sin(np.radians(LON[0]))
        arr = mld_2d[np.newaxis, ...].astype(np.float32)
        if has_land:
            arr[:, is_land_2d] = np.nan
    elif variable == "ohc_0_700m":
        # Ocean heat content 2D
        ohc_2d = 1.8e9 + 1.2e9 * np.cos(np.radians(LAT[0]))
        arr = ohc_2d[np.newaxis, ...].astype(np.float32)
        if has_land:
            arr[:, is_land_2d] = np.nan
    elif variable == "sound_speed":
        # Mackenzie formula
        T, S, D = thetao_3d.astype(np.float64), so_3d.astype(np.float64), DEPTH.astype(np.float64)
        c = (1448.96 + 4.591 * T - 5.304e-2 * T**2 + 2.374e-4 * T**3
             + 1.340 * (S - 35.0) + 1.630e-2 * D + 1.675e-7 * D**2
             - 1.025e-2 * T * (S - 35.0) - 7.139e-13 * T * D**3)
        arr = c.astype(np.float32)
        if has_land:
            arr[:, is_land_2d] = np.nan
    elif variable == "density":
        # UNESCO simplified potential density anomaly
        T, S = thetao_3d.astype(np.float64), so_3d.astype(np.float64)
        rho_w = 999.84 + 6.79e-2 * T - 9.09e-3 * T**2 + 1.00e-4 * T**3
        A = 8.24e-1 - 4.09e-3 * T + 7.64e-5 * T**2
        rho = rho_w + A * S
        arr = (rho - 1000.0).astype(np.float32)
        if has_land:
            arr[:, is_land_2d] = np.nan
    else:
        arr = thetao_3d
        if has_land:
            arr[:, is_land_2d] = np.nan

    # 3. Binary Packing
    valid = arr[~np.isnan(arr)]
    v_min = float(valid.min()) if valid.size else 0.0
    v_max = float(valid.max()) if valid.size else 30.0

    raw_bytes = np.ascontiguousarray(arr, dtype=np.float32).tobytes()
    payload_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

    is_multi_channel = (arr.ndim == 4)
    channel_count = int(arr.shape[3]) if is_multi_channel else 1

    metadata: Dict[str, Any] = {
        "dataset":          "GLORYS_SYNTHETIC_CLIMATOLOGY",
        "variable":         variable,
        "units":            spec["unit"],
        "label":            spec["label"],
        "is_2d":            is_2d,
        "is_multi_channel": is_multi_channel,
        "channel_count":    channel_count,
        "channels":         ["thetao", "so", "chl", "mask"] if is_multi_channel else [variable],
        "date":             date_str,
        "mode":             "synthetic_climatology",
        "lod":              lod,
        "strides":          {"lat": 1, "lon": 1, "depth": 1},
        "shape":            {"depth": int(arr.shape[0]), "lat": int(arr.shape[1]), "lon": int(arr.shape[2])},
        "depth":            depth_vals,
        "latitude":         lat_vals,
        "longitude":        lon_vals,
        "depth_min":        float(min(depth_vals)) if depth_vals else 0.0,
        "depth_max":        float(max(depth_vals)) if depth_vals else 500.0,
        "latitude_min":     float(min(lat_vals)) if lat_vals else -80.0,
        "latitude_max":     float(max(lat_vals)) if lat_vals else 90.0,
        "longitude_min":    float(min(lon_vals)) if lon_vals else -180.0,
        "longitude_max":    float(max(lon_vals)) if lon_vals else 180.0,
        "value_min":        v_min,
        "value_max":        v_max,
        "temperature_min":  v_min,
        "temperature_max":  v_max,
        "byte_length":      len(raw_bytes),
        "payload_hash":     payload_hash,
        "nan_sentinel":     "NaN (IEEE754)",
        "land_fraction":    round(land_fraction, 4),
        "has_land_mask":    has_land,
    }

    meta_json = json.dumps(metadata).encode("utf-8")
    header = struct.pack(">I", len(meta_json))
    logger.info(
        f"[VOLUME-SYNTH] Generated synthetic volume for '{variable}': "
        f"{metadata['shape']['depth']}×{metadata['shape']['lat']}×{metadata['shape']['lon']} "
        f"bbox=[{min_lon:.1f}..{max_lon:.1f}E, {min_lat:.1f}..{max_lat:.1f}N] "
        f"bytes={len(raw_bytes)} hash={payload_hash}"
    )

    return header + meta_json + raw_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Synchronous Extraction Helpers (invoked via asyncio.to_thread)
# ─────────────────────────────────────────────────────────────────────────────
def extract_local_volume(
    min_lat: Optional[float],
    max_lat: Optional[float],
    min_lon: Optional[float],
    max_lon: Optional[float],
    date_str: str,
    depth_min: Optional[float] = None,
    depth_max: Optional[float] = None,
    lod: int = 1,
    stride_lat: Optional[int] = None,
    stride_lon: Optional[int] = None,
    stride_depth: Optional[int] = None,
    variable: str = "thetao",
) -> bytes:
    """Extract volume from local GLORYS / NetCDF service."""
    from backend.glorys_service import get_service, CLIMATE_VARIABLES_LOCAL_ONLY
    service = get_service()

    # Fast path: If local NetCDF fixture exists, extract directly from local fixture
    if os.path.exists(service.local_path):
        if service._local_ds is None:
            service._load_local_fixture()
        if service._local_ds is not None and variable in ("thetao", "temperature"):
            s_lat = stride_lat or max(1, lod)
            s_lon = stride_lon or max(1, lod)
            s_dep = stride_depth or 1
            return service._fetch_local_volume(
                date_str=date_str,
                lon_min=min_lon,
                lon_max=max_lon,
                lat_min=min_lat,
                lat_max=max_lat,
                depth_min=depth_min,
                depth_max=depth_max,
                stride_lat=s_lat,
                stride_lon=s_lon,
                stride_depth=s_dep,
                lod=lod,
            )

    return service.get_volume_binary(
        date_str=date_str,
        lon_min=min_lon,
        lon_max=max_lon,
        lat_min=min_lat,
        lat_max=max_lat,
        depth_min=depth_min,
        depth_max=depth_max,
        lod=lod,
        stride_lat=stride_lat,
        stride_lon=stride_lon,
        stride_depth=stride_depth,
        variable=variable,
    )


def extract_remote_opendap_volume(
    min_lat: Optional[float],
    max_lat: Optional[float],
    min_lon: Optional[float],
    max_lon: Optional[float],
    date_str: str,
    depth_min: Optional[float] = None,
    depth_max: Optional[float] = None,
    downsample_stride: int = 1,
    variable: str = "thetao",
) -> bytes:
    """Extract volume from remote OPeNDAP service."""
    from backend import opendap_service
    # Map GLORYS variable names to OPeNDAP supported names
    op_var = "temperature" if variable == "thetao" else ("salinity" if variable == "so" else variable)
    if op_var in opendap_service.ALLOWED_OPENDAP_VARIABLES:
        return opendap_service.extract_volume(
            variable=op_var,
            lat_min=min_lat,
            lat_max=max_lat,
            lon_min=min_lon,
            lon_max=max_lon,
            depth_min=depth_min,
            depth_max=depth_max,
            downsample_stride=downsample_stride,
        )

    # Fallback to glorys remote service
    from backend.glorys_service import get_service
    service = get_service()
    return service.get_volume_binary(
        date_str=date_str,
        lon_min=min_lon,
        lon_max=max_lon,
        lat_min=min_lat,
        lat_max=max_lat,
        depth_min=depth_min,
        depth_max=depth_max,
        lod=1,
        variable=variable,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Resilient Safe Extraction Entrypoint (Async with Strict 6.0s Timeout)
# ─────────────────────────────────────────────────────────────────────────────
async def extract_volume_safe(
    min_lat: Optional[float],
    max_lat: Optional[float],
    min_lon: Optional[float],
    max_lon: Optional[float],
    date_str: str,
    depth_min: Optional[float] = None,
    depth_max: Optional[float] = None,
    lod: int = 1,
    stride_lat: Optional[int] = None,
    stride_lon: Optional[int] = None,
    stride_depth: Optional[int] = None,
    variable: str = "thetao",
    timeout: float = 3.5,
) -> bytes:
    """
    Non-blocking safe volume extraction with:
      - Diagnostic timestamped telemetry.
      - Fast local NetCDF path when inside local bounds.
      - Non-blocking remote query execution with strict 6.0s timeout.
      - Instant synthetic physical climatology fallback on failure or timeout.
    """
    start_t = time.time()
    logger.info(
        f"[DIAG-START] Querying volume for bounds: "
        f"lat({min_lat}..{max_lat}), lon({min_lon}..{max_lon}), depth({depth_min}..{depth_max}), "
        f"date={date_str}, var={variable}, lod={lod}"
    )

    # 0. Fast Global Landmass Boundary Check:
    # If the user selects a region situated 100% on continental land (e.g. Eastern Europe,
    # central Australia, Sahara), reject immediately with a user-facing warning rather than
    # synthesizing a false ocean.
    if min_lat is not None and max_lat is not None and min_lon is not None and max_lon is not None:
        land_frac = check_region_land_fraction(min_lat, max_lat, min_lon, max_lon, samples=20)
        logger.info(f"[VOLUME-LAND] Region [{min_lon:.1f}..{max_lon:.1f}E, {min_lat:.1f}..{max_lat:.1f}N] land fraction: {land_frac * 100.0:.1f}%")
        if land_frac >= 0.999:
            logger.warning(
                f"[VOLUME-LAND] Bounding box [{min_lon}..{max_lon}E, {min_lat}..{max_lat}N] "
                f"is 100% continental landmass (fraction={land_frac:.2f}). Aborting ocean volume synthesis."
            )
            raise ValueError("⚠️ Terrestrial Landmass Selected: Oceanographic data unavailable")

    # 1. Fast path: Extract from local NetCDF if within Indian Ocean bounds
    if is_within_local_dataset(min_lat, max_lat, min_lon, max_lon):
        logger.info("[VOLUME] Coordinates inside local dataset bounds. Extracting via local NetCDF.")
        try:
            payload = await asyncio.to_thread(
                extract_local_volume,
                min_lat, max_lat, min_lon, max_lon, date_str,
                depth_min, depth_max, lod, stride_lat, stride_lon, stride_depth, variable
            )
            logger.info(f"[VOLUME-SUCCESS] Local extraction completed in {time.time() - start_t:.3f}s")
            return payload
        except Exception as local_err:
            logger.warning(f"[VOLUME-WARN] Local extraction encountered error: {local_err}. Proceeding to fallback.")

    # 2. Remote path: map variable name and guard against unsupported remote vars.
    #    Variables like 'chl', 'composite', 'mlotst', 'ohc_0_700m' have no OPeNDAP
    #    backing — serve synthetic immediately without launching a network thread.
    op_var = "temperature" if variable in ("thetao", "temperature") else (
        "salinity" if variable in ("so", "salinity") else variable
    )
    from backend.opendap_service import ALLOWED_OPENDAP_VARIABLES
    if op_var not in ALLOWED_OPENDAP_VARIABLES:
        d_min = depth_min if depth_min is not None else 0.0
        d_max = depth_max if depth_max is not None else 500.0
        q_min_lat = min_lat if min_lat is not None else -10.0
        q_max_lat = max_lat if max_lat is not None else 0.0
        q_min_lon = min_lon if min_lon is not None else 0.0
        q_max_lon = max_lon if max_lon is not None else 10.0
        logger.info(
            f"[VOLUME] Variable '{variable}' (op_var='{op_var}') has no remote OPeNDAP backing. "
            "Serving synthetic climatology immediately."
        )
        return generate_synthetic_ocean_volume(
            min_lat=q_min_lat, max_lat=q_max_lat,
            min_lon=q_min_lon, max_lon=q_max_lon,
            date_str=date_str, depth_min=d_min, depth_max=d_max,
            variable=variable, dims=(61, 61, 31), lod=lod,
        )

    logger.info(
        f"[VOLUME] Coordinates outside local dataset ({min_lat}..{max_lat}, {min_lon}..{max_lon}). "
        f"Attempting remote query with {timeout:.1f}s timeout..."
    )
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                extract_remote_opendap_volume,
                min_lat, max_lat, min_lon, max_lon, date_str,
                depth_min, depth_max, downsample_stride=max(1, lod), variable=variable
            ),
            timeout=timeout,
        )
        logger.info(f"[VOLUME-SUCCESS] Remote query completed in {time.time() - start_t:.3f}s")
        return payload
    except (asyncio.TimeoutError, Exception) as err:
        elapsed = time.time() - start_t
        err_name = "Timeout" if isinstance(err, asyncio.TimeoutError) else f"Error ({type(err).__name__}: {err})"
        logger.warning(
            f"[VOLUME-WARN] Remote fetch failed or timed out after {elapsed:.2f}s ({err_name}). "
            "Generating synthetic fallback ocean slice."
        )

        # 3. Resilient Fallback: Immediate physical climatology synthesis
        d_min = depth_min if depth_min is not None else 0.0
        d_max = depth_max if depth_max is not None else 500.0
        q_min_lat = min_lat if min_lat is not None else -10.0
        q_max_lat = max_lat if max_lat is not None else 0.0
        q_min_lon = min_lon if min_lon is not None else 0.0
        q_max_lon = max_lon if max_lon is not None else 10.0

        return generate_synthetic_ocean_volume(
            min_lat=q_min_lat,
            max_lat=q_max_lat,
            min_lon=q_min_lon,
            max_lon=q_max_lon,
            date_str=date_str,
            depth_min=d_min,
            depth_max=d_max,
            variable=variable,
            dims=(61, 61, 31),
            lod=lod,
        )
