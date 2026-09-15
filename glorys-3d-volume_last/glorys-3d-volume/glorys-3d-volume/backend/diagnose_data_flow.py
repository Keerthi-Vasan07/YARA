import os
import sys
import numpy as np
import xarray as xr
from dotenv import load_dotenv

load_dotenv()

opendap_url = os.getenv("OPENDAP_URL")
print(f"[CHECK 1] OPeNDAP URL in .env: {opendap_url}")

if not opendap_url:
    print("ERROR: OPENDAP_URL is not configured in .env.")
    sys.exit(1)

try:
    print("[CHECK 2] Opening dataset remotely...")
    try:
        ds = xr.open_dataset(opendap_url, engine="netcdf4")
        print("  -> Engine: netcdf4")
    except Exception:
        ds = xr.open_dataset(opendap_url, engine="pydap")
        print("  -> Engine: pydap")

    print(f"[CHECK 3] Remote Dataset Dimensions: {dict(ds.dims)}")
    print(f"[CHECK 4] Remote Coordinates: {list(ds.coords.keys())}")
    print(f"[CHECK 5] Data Variables: {list(ds.data_vars.keys())}")

    # Coordinate integrity check
    has_lat = any(c in ds.coords for c in ["lat", "latitude", "nav_lat"])
    has_lon = any(c in ds.coords for c in ["lon", "longitude", "nav_lon"])
    depth_coords = [c for c in ds.coords if c.lower() in ["depth", "lev", "level", "pres", "z"]]
    has_time = "time" in ds.coords

    print("\n--- COORDINATE INTEGRITY ---")
    print(f"  Latitude found: {has_lat}")
    print(f"  Longitude found: {has_lon}")
    print(f"  Vertical Depth Levels found: {depth_coords}")
    print(f"  Temporal dimension found: {has_time}")

    if depth_coords:
        depth_vals = ds[depth_coords[0]].values
        print(f"  Depth span: {depth_vals[0]}m to {depth_vals[-1]}m (Total levels: {len(depth_vals)})")
    else:
        print("  WARNING: No vertical depth dimension found! (Dataset is 2D surface-only)")

    if has_time:
        times = ds["time"].values
        print(f"  Time coverage: {times[0]} to {times[-1]} (Total steps: {len(times)})")

    # Target variable check
    expected = ["thetao", "temperature", "temp", "pottmp", "so", "salinity", "salt", "uo", "vo", "water_temp"]
    matched = [v for v in expected if v in ds.variables]
    print(f"\n[CHECK 6] Matched Physical Ocean Variables: {matched}")

except Exception as err:
    print(f"ERROR: Dataset inspection failed: {err}")
