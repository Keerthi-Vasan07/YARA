"""
ingest_global_dec2004.py

One-time ingest script — NOT part of the live API server.

Pulls thetao, so, mlotst from Copernicus Marine GLORYS12V1 for December 2004
(full globe, 0–700 m, coarsened 3× horizontally, subsetted to 12 climate depth levels),
computes ohc_0_700m, and saves a compressed NetCDF4 fixture to:
    backend/data/glorys_global_dec2004_climate.nc

Usage:
    # From the glorys-3d-volume/ project root (with venv active):
    python backend/scripts/ingest_global_dec2004.py

Requirements: same as backend/requirements.txt
    pip install copernicusmarine xarray netCDF4 numpy python-dotenv
"""

import hashlib
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import xarray as xr
from dotenv import load_dotenv

# ── Resolve paths ──────────────────────────────────────────────────────────────
_SCRIPT_FILE  = Path(__file__).resolve()
_SCRIPTS_DIR  = _SCRIPT_FILE.parent           # .../backend/scripts/
_BACKEND_DIR  = _SCRIPTS_DIR.parent           # .../backend/
_PROJECT_ROOT = _BACKEND_DIR.parent           # .../glorys-3d-volume/
_ENV_FILE     = _PROJECT_ROOT / ".env"
_OUTPUT_FILE  = _PROJECT_ROOT / "backend" / "data" / "glorys_global_dec2004_climate.nc"
_CACHE_DIR    = _PROJECT_ROOT / "backend" / "data" / ".ingest_cache_dec2004"

# Load credentials from .env
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)
    print(f"[INGEST] Loaded .env from {_ENV_FILE}")
else:
    load_dotenv()
    print(f"[INGEST] WARNING: .env not found at {_ENV_FILE}, falling back to environment variables")

COPERNICUSMARINE_USERNAME = os.getenv("COPERNICUSMARINE_USERNAME", "").strip()
COPERNICUSMARINE_PASSWORD = os.getenv("COPERNICUSMARINE_PASSWORD", "").strip()

if not (COPERNICUSMARINE_USERNAME and COPERNICUSMARINE_PASSWORD):
    print("[INGEST] ERROR: COPERNICUSMARINE_USERNAME and COPERNICUSMARINE_PASSWORD must be set in .env")
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────
DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
VARIABLES  = ["thetao", "so", "mlotst"]

START_DATE = date(2004, 12, 1)
END_DATE   = date(2004, 12, 31)

# Standard climate-relevant depth levels (method="nearest" snaps to actual grid)
TARGET_DEPTHS = [0, 10, 25, 50, 75, 100, 150, 200, 300, 400, 500, 700]

# Horizontal coarsening factor
COARSEN_FACTOR = 3

# NetCDF4 compression
COMPRESS_ENCODING = {"zlib": True, "complevel": 4}

# Physical constants for OHC
RHO = 1025.0   # kg/m³ seawater density
CP  = 3985.0   # J/(kg·K) specific heat capacity


def fetch_day(day: date, cache_dir: Path) -> xr.Dataset | None:
    """
    Fetch a single day from Copernicus Marine with caching.
    Returns an xr.Dataset or None on failure.
    Cache is keyed by date string so the script is idempotent/resumable.
    """
    import copernicusmarine as cm

    cache_file = cache_dir / f"{day.isoformat()}.nc"
    if cache_file.exists():
        print(f"  [CACHE HIT] {day}")
        try:
            ds = xr.open_dataset(str(cache_file))
            return ds
        except Exception as e:
            print(f"  [CACHE CORRUPT] {day}: {e} — re-fetching")
            cache_file.unlink(missing_ok=True)

    start_dt = f"{day.isoformat()}T00:00:00"
    end_dt   = f"{day.isoformat()}T23:59:59"

    print(f"  [FETCH] {day} — variables={VARIABLES}")
    try:
        ds = cm.open_dataset(
            dataset_id=DATASET_ID,
            username=COPERNICUSMARINE_USERNAME,
            password=COPERNICUSMARINE_PASSWORD,
            variables=VARIABLES,
            start_datetime=start_dt,
            end_datetime=end_dt,
            minimum_longitude=-180.0,
            maximum_longitude=180.0,
            minimum_latitude=-80.0,
            maximum_latitude=90.0,
            minimum_depth=0.0,
            maximum_depth=710.0,  # slightly above 700m to ensure 700m level is included
        )

        # Subset to target depth levels using nearest-neighbour selection
        ds = ds.sel(depth=TARGET_DEPTHS, method="nearest")

        # Coarsen horizontal grid by factor 3
        ds = ds.coarsen(latitude=COARSEN_FACTOR, longitude=COARSEN_FACTOR, boundary="trim").mean()

        # Compute into memory before caching
        ds = ds.compute()

        # Cache to disk
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(str(cache_file))
        print(f"  [CACHED] {day} → {cache_file.name}")
        return ds

    except Exception as e:
        print(f"  [ERROR] {day}: {e}")
        return None


def compute_ohc(ds: xr.Dataset) -> xr.DataArray:
    """
    Compute Ocean Heat Content integrated 0–700 m.
    Result has dims (time, latitude, longitude) — no depth.
    OHC = integral(thetao * RHO * CP, depth=0..700)  [J/m²]
    """
    thetao_sub = ds["thetao"].sel(depth=slice(0, 700))
    ohc = (thetao_sub * RHO * CP).integrate("depth")
    ohc.attrs = {
        "long_name": "Ocean Heat Content 0–700m",
        "units": "J m-2",
        "standard_name": "ocean_heat_content",
    }
    return ohc


def print_summary(ds: xr.Dataset, output_path: Path) -> None:
    """Print a human-readable summary of the ingested dataset."""
    file_size_mb = output_path.stat().st_size / 1e6
    print("\n" + "=" * 60)
    print(f"  INGEST COMPLETE")
    print(f"  Output file : {output_path}")
    print(f"  File size   : {file_size_mb:.1f} MB")
    print("=" * 60)
    print(f"\nDimensions:")
    for dim, size in ds.dims.items():
        print(f"  {dim}: {size}")

    print(f"\nVariables:")
    for var_name in ds.data_vars:
        da = ds[var_name]
        arr = da.values.astype(np.float32)
        valid = arr[~np.isnan(arr)]
        nan_count = int(np.sum(np.isnan(arr)))
        total = arr.size
        nan_pct = 100.0 * nan_count / max(total, 1)
        if valid.size > 0:
            print(f"  {var_name:15s}  shape={list(da.shape)}  "
                  f"min={float(valid.min()):.4g}  max={float(valid.max()):.4g}  "
                  f"NaN={nan_count}/{total} ({nan_pct:.1f}% land mask)")
        else:
            print(f"  {var_name:15s}  shape={list(da.shape)}  all NaN!")

    print(f"\nDepth levels: {[float(d) for d in ds['depth'].values]}")
    print(f"Lat  range  : {float(ds.latitude.min()):.2f}° → {float(ds.latitude.max()):.2f}°")
    print(f"Lon  range  : {float(ds.longitude.min()):.2f}° → {float(ds.longitude.max()):.2f}°")
    if "time" in ds:
        times = [str(np.datetime_as_string(t, unit="D")) for t in ds.time.values]
        print(f"Time steps  : {len(times)}  [{times[0]} → {times[-1]}]")
    print("=" * 60 + "\n")


def main():
    print(f"\n{'=' * 60}")
    print(f"  GLORYS Dec 2004 Global Climate Ingest")
    print(f"  Dataset  : {DATASET_ID}")
    print(f"  Period   : {START_DATE} → {END_DATE}")
    print(f"  Variables: {VARIABLES} + ohc_0_700m (computed)")
    print(f"  Output   : {_OUTPUT_FILE}")
    print(f"{'=' * 60}\n")

    if _OUTPUT_FILE.exists():
        print(f"[INGEST] Output file already exists: {_OUTPUT_FILE}")
        print("[INGEST] Delete it manually to force re-ingest. Exiting.")
        sys.exit(0)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all days in Dec 2004, retry failures per-day
    daily_datasets: list[xr.Dataset] = []
    current = START_DATE
    failed_days: list[date] = []

    while current <= END_DATE:
        ds_day = fetch_day(current, _CACHE_DIR)
        if ds_day is not None:
            daily_datasets.append(ds_day)
        else:
            failed_days.append(current)
            print(f"  [SKIP] {current} failed, will note in summary")
        current += timedelta(days=1)

    if not daily_datasets:
        print("[INGEST] ERROR: No days were successfully fetched. Check credentials and network.")
        sys.exit(1)

    if failed_days:
        print(f"\n[INGEST] WARNING: {len(failed_days)} day(s) failed and are missing from output:")
        for d in failed_days:
            print(f"  {d}")

    print(f"\n[INGEST] Concatenating {len(daily_datasets)} daily slices along time axis...")
    ds_month = xr.concat(daily_datasets, dim="time")

    print("[INGEST] Computing ohc_0_700m...")
    ds_month["ohc_0_700m"] = compute_ohc(ds_month)

    # Ensure all variables are float32 to keep file size down
    encoding = {}
    for var_name in ds_month.data_vars:
        ds_month[var_name] = ds_month[var_name].astype(np.float32)
        encoding[var_name] = {**COMPRESS_ENCODING, "dtype": "float32"}

    print(f"[INGEST] Saving to {_OUTPUT_FILE} ...")
    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ds_month.to_netcdf(str(_OUTPUT_FILE), encoding=encoding, format="NETCDF4")

    # Verify written file
    ds_verify = xr.open_dataset(str(_OUTPUT_FILE))
    print_summary(ds_verify, _OUTPUT_FILE)
    ds_verify.close()

    print(f"[INGEST] Done! Run the API server and switch to a Dec 2004 date to use this dataset.")


if __name__ == "__main__":
    main()
