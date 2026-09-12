import os
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

OUT = Path("local_dataset")
OUT.mkdir(exist_ok=True)

# ------------------------------------------------------------
# REAL DATA SOURCE
# NOAA ERDDAP -> NASA/JPL MUR SST
# Small geographic/time subset to keep the test files manageable.
# ------------------------------------------------------------

URL = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/"
    "jplMURSST41.nc"
    "?analysed_sst[0:1:1][0:50:1][0:50:1]"
)

print("\nDownloading REAL MUR SST data...")
print(URL)

nc_file = OUT / "yara_real_sst.nc"

# Download through Python/xarray
try:
    import requests

    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    nc_file.write_bytes(r.content)

    print(f"Downloaded: {nc_file}")
    print(f"Size: {nc_file.stat().st_size / 1024:.1f} KB")

except Exception as e:
    print("\nDirect download failed:")
    print(e)
    print("\nTrying xarray/netCDF4...")
    ds_tmp = xr.open_dataset(URL)
    ds_tmp.to_netcdf(nc_file)
    ds_tmp.close()

# ------------------------------------------------------------
# READ REAL DATA
# ------------------------------------------------------------

print("\nOpening NetCDF...")

ds = xr.open_dataset(nc_file)

print(ds)

# Find SST variable robustly
possible = [
    "analysed_sst",
    "sst",
    "sea_surface_temperature",
]

sst_name = None

for name in possible:
    if name in ds.data_vars:
        sst_name = name
        break

if sst_name is None:
    # fallback: first numeric data variable
    for name, da in ds.data_vars.items():
        if np.issubdtype(da.dtype, np.number):
            sst_name = name
            break

if sst_name is None:
    raise RuntimeError("Could not find a numeric SST variable.")

sst = ds[sst_name]

print(f"\nUsing variable: {sst_name}")
print("Dimensions:", sst.dims)
print("Shape:", sst.shape)

# ------------------------------------------------------------
# CREATE ZARR
# ------------------------------------------------------------

zarr_dir = OUT / "yara_real_sst.zarr"

if zarr_dir.exists():
    shutil.rmtree(zarr_dir)

print("\nCreating Zarr...")

try:
    ds.to_zarr(zarr_dir, mode="w")
    print(f"Created: {zarr_dir}")

except Exception as e:
    print("Zarr creation failed:", e)

# ------------------------------------------------------------
# CREATE HDF5
# ------------------------------------------------------------

h5_file = OUT / "yara_real_sst.h5"

print("\nCreating HDF5...")

try:
    ds.to_netcdf(
        h5_file,
        engine="h5netcdf",
    )
    print(f"Created: {h5_file}")

except Exception:
    try:
        ds.to_netcdf(h5_file)
        print(f"Created: {h5_file}")
    except Exception as e:
        print("HDF5 creation failed:", e)

# ------------------------------------------------------------
# EXTRACT A 2D FRAME
# ------------------------------------------------------------

frame = sst

# Select first time dimension if present
if "time" in frame.dims:
    frame = frame.isel(time=0)

# Remove singleton dimensions
frame = frame.squeeze()

values = frame.values.astype("float32")

# Find coordinates
lat_name = None
lon_name = None

for name in ["lat", "latitude", "y"]:
    if name in frame.coords:
        lat_name = name
        break

for name in ["lon", "longitude", "x"]:
    if name in frame.coords:
        lon_name = name
        break

print("\nCoordinates:")
print("Latitude :", lat_name)
print("Longitude:", lon_name)

if lat_name is None or lon_name is None:
    raise RuntimeError("Latitude/longitude coordinates not found.")

lat = frame[lat_name].values
lon = frame[lon_name].values

# ------------------------------------------------------------
# CSV
# ------------------------------------------------------------

csv_file = OUT / "yara_real_sst.csv"

print("\nCreating CSV...")

rows = []

for i, la in enumerate(lat):
    for j, lo in enumerate(lon):
        value = values[i, j]

        if np.isfinite(value):
            rows.append(
                {
                    "latitude": float(la),
                    "longitude": float(lo),
                    "sst": float(value),
                }
            )

pd.DataFrame(rows).to_csv(csv_file, index=False)

print(f"Created: {csv_file}")

# ------------------------------------------------------------
# TXT
# ------------------------------------------------------------

txt_file = OUT / "yara_real_sst.txt"

print("\nCreating TXT...")

pd.DataFrame(rows).to_csv(
    txt_file,
    sep="\t",
    index=False,
)

print(f"Created: {txt_file}")

# ------------------------------------------------------------
# JSON
# ------------------------------------------------------------

json_file = OUT / "yara_real_sst.json"

print("\nCreating JSON...")

metadata = {
    "source": "NASA/JPL MUR SST",
    "provider": "NOAA ERDDAP",
    "variable": sst_name,
    "units": sst.attrs.get("units", "unknown"),
    "coordinates": {
        "latitude": lat_name,
        "longitude": lon_name,
    },
    "data": rows,
}

json_file.write_text(
    json.dumps(metadata, indent=2),
    encoding="utf-8",
)

print(f"Created: {json_file}")

# ------------------------------------------------------------
# GEOTIFF
# ------------------------------------------------------------

tif_file = OUT / "yara_real_sst.tif"

print("\nCreating GeoTIFF...")

try:
    import rasterio
    from rasterio.transform import from_bounds

    # Make sure latitude is north -> south
    data = values.copy()
    lat2 = lat.copy()

    if lat2[0] < lat2[-1]:
        data = np.flipud(data)
        lat2 = lat2[::-1]

    transform = from_bounds(
        float(lon.min()),
        float(lat2.min()),
        float(lon.max()),
        float(lat2.max()),
        data.shape[1],
        data.shape[0],
    )

    with rasterio.open(
        tif_file,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(data.astype("float32"), 1)

    print(f"Created: {tif_file}")

except Exception as e:
    print("GeoTIFF creation failed:", e)

# ------------------------------------------------------------
# README
# ------------------------------------------------------------

readme = OUT / "README.txt"

readme.write_text(
    """YARA REAL DATA TEST PACK
==========================

Source:
NASA/JPL Multi-scale Ultra-high Resolution (MUR) Sea Surface Temperature

Access:
NOAA ERDDAP

This directory contains real SST observations.

Files:

yara_real_sst.nc
    Original NetCDF scientific dataset.

yara_real_sst.zarr/
    Zarr representation.

yara_real_sst.h5
    HDF5 representation.

yara_real_sst.tif
    GeoTIFF raster representation.

yara_real_sst.csv
    Latitude / longitude / SST table.

yara_real_sst.txt
    Tab-delimited latitude / longitude / SST table.

yara_real_sst.json
    Structured coordinate/value representation.

These files are intended for testing YARA's
local dataset ingestion architecture.

Do not treat converted files as independent observations:
they originate from the same real SST dataset.
""",
    encoding="utf-8",
)

ds.close()

print("\n==============================================")
print(" REAL YARA TEST DATA CREATED SUCCESSFULLY")
print("==============================================")

for p in sorted(OUT.iterdir()):
    print(p)

print("\nNext:")
print("1. Start FastAPI")
print("2. Start Vite")
print("3. Open the YARA globe")
print("4. Upload/drop yara_real_sst.nc")
print("5. Verify SST rendering")
print("6. Test CSV/TXT/JSON/TIFF/HDF5/Zarr")
