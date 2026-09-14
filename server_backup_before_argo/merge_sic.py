#!/usr/bin/env python3
"""Merge Arctic and Antarctic SIC data into a global COG."""

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from pathlib import Path
from scipy.ndimage import zoom
import sys

def merge_sic_hemispheres(date: str = "2024-01-01"):
    """Merge Arctic and Antarctic SIC into one global COG."""
    
    # Paths
    south_nc = Path(f"/tmp/sic_south_{date}.nc")
    north_cog = Path(f"server/products/sic/{date}.tif")
    output = Path(f"server/products/sic/{date}_global.tif")
    
    if not south_nc.exists():
        print(f"Antarctic data not found: {south_nc}")
        return
    
    # Load Antarctic NetCDF
    ds_south = xr.open_dataset(south_nc)
    sic_south = ds_south["ice_conc"].squeeze().values.astype(np.float32)
    
    lat_s = ds_south["lat"].values if "lat" in ds_south else ds_south["latitude"].values
    lon_s = ds_south["lon"].values if "lon" in ds_south else ds_south["longitude"].values
    
    if lat_s.ndim == 2:
        lat_s = lat_s[:, 0]
    if lon_s.ndim == 2:
        lon_s = lon_s[0, :]
    
    print(f"Antarctic: shape={sic_south.shape}, lat=[{lat_s.min():.2f}, {lat_s.max():.2f}]")
    
    # Load Arctic COG
    with rasterio.open(north_cog) as src:
        sic_north = src.read(1).astype(np.float32)
        print(f"Arctic: shape={sic_north.shape}, bounds={src.bounds}")
    
    # Create global grid (0.1 deg resolution)
    global_lon = np.arange(-180, 180, 0.1)
    global_lat = np.arange(90, -90, -0.1)
    nlat, nlon = len(global_lat), len(global_lon)
    print(f"Global grid: {nlat}x{nlon}")
    
    global_sic = np.full((nlat, nlon), 255, dtype=np.uint8)
    
    # Resample and place Arctic (30N to 90N = indices 0:600)
    arctic_rows = 600
    sic_north_r = zoom(sic_north, (arctic_rows/sic_north.shape[0], nlon/sic_north.shape[1]), order=1)
    valid_n = (sic_north_r != 255) & (sic_north_r >= 0) & (sic_north_r <= 100)
    global_sic[:arctic_rows, :][valid_n[:arctic_rows, :nlon]] = sic_north_r[:arctic_rows, :nlon][valid_n[:arctic_rows, :nlon]].astype(np.uint8)
    print(f"Arctic pixels: {valid_n.sum()}")
    
    # Flip Antarctic if needed
    if lat_s[0] < lat_s[-1]:
        sic_south = np.flipud(sic_south)
        lat_s = lat_s[::-1]
    
    # Place Antarctic (35S to 85S = indices 1250:1750)
    ant_start = int((90 - (-35)) / 0.1)  # 1250
    ant_end = int((90 - (-85)) / 0.1)    # 1750
    ant_rows = ant_end - ant_start
    sic_south_r = zoom(sic_south, (ant_rows/sic_south.shape[0], nlon/sic_south.shape[1]), order=1)
    valid_s = (sic_south_r >= 0) & (sic_south_r <= 100) & ~np.isnan(sic_south_r)
    rows = min(ant_rows, sic_south_r.shape[0])
    cols = min(nlon, sic_south_r.shape[1])
    global_sic[ant_start:ant_start+rows, :cols][valid_s[:rows, :cols]] = np.clip(sic_south_r[:rows, :cols][valid_s[:rows, :cols]], 0, 100).astype(np.uint8)
    print(f"Antarctic pixels: {valid_s.sum()}")
    
    print(f"Total valid: {(global_sic != 255).sum()}")
    
    # Write COG
    transform = from_bounds(-180, -90, 180, 90, nlon, nlat)
    with rasterio.open(output, "w", driver="GTiff", height=nlat, width=nlon, count=1, dtype="uint8",
        crs=CRS.from_epsg(4326), transform=transform, nodata=255, compress="deflate", tiled=True,
        blockxsize=512, blockysize=512) as dst:
        dst.write(global_sic, 1)
    
    print(f"Wrote: {output}")
    
    # Replace original
    import shutil
    shutil.move(str(output), str(north_cog))
    print(f"Replaced: {north_cog}")
    
    ds_south.close()


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    merge_sic_hemispheres(date)
