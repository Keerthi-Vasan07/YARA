#!/usr/bin/env python3
"""
Download Ocean Colour Rrs bands and create RGB composite from Copernicus Marine.

Creates a true-color-like visualization from Remote Sensing Reflectance bands:
- Red: Rrs670 (670nm)
- Green: Rrs555 (555nm)  
- Blue: Rrs443 (443nm)

This shows phytoplankton blooms as green/brown, clear water as blue.

Usage:
    python download_rrs_rgb.py 2024-01-15
    python download_rrs_rgb.py 2024-01-15 2024-01-20  # Date range
"""

import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import tempfile
import subprocess


# L3 multi-sensor Rrs products (no L4 gap-free for Rrs)
RRS_DATASETS = {
    "nrt": {
        "dataset_id": "cmems_obs-oc_glo_bgc-reflectance_nrt_l3-multi-4km_P1D",
        "variables": ["RRS412", "RRS443", "RRS490", "RRS510", "RRS555", "RRS670"],
    },
    "rep": {
        "dataset_id": "cmems_obs-oc_glo_bgc-reflectance_my_l3-multi-4km_P1D",
        "variables": ["RRS412", "RRS443", "RRS490", "RRS510", "RRS555", "RRS670"],
    },
}

# Bands for RGB composite (R, G, B wavelengths)
RGB_BANDS = {
    "red": "RRS670",    # 670nm - shows sediments, blooms
    "green": "RRS555",  # 555nm - phytoplankton, mid-visible
    "blue": "RRS443",   # 443nm - clear water appears bright
}

PRODUCTS_DIR = Path(__file__).parent / "products" / "rrs"


def download_rrs_cmems(date: str, stream: str = "nrt") -> Path | None:
    """
    Download Rrs bands using copernicusmarine CLI.
    """
    config = RRS_DATASETS.get(stream, RRS_DATASETS["nrt"])
    dataset_id = config["dataset_id"]
    
    output_file = Path(tempfile.mkdtemp()) / f"rrs_{date}.nc"
    
    start_date = f"{date}T00:00:00"
    end_date = f"{date}T23:59:59"
    
    # Request the 3 bands we need for RGB
    cmd = [
        "copernicusmarine", "subset",
        "--dataset-id", dataset_id,
        "--variable", RGB_BANDS["red"],
        "--variable", RGB_BANDS["green"],
        "--variable", RGB_BANDS["blue"],
        "--start-datetime", start_date,
        "--end-datetime", end_date,
        "--minimum-longitude", "-180",
        "--maximum-longitude", "180",
        "--minimum-latitude", "-90",
        "--maximum-latitude", "90",
        "-o", str(output_file.parent),
        "-f", output_file.name,
    ]
    
    print(f"Downloading Rrs for {date} ({stream})...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            print(f"Download failed: {result.stderr}")
            if stream == "nrt":
                print("Trying REP stream...")
                return download_rrs_cmems(date, "rep")
            return None
        
        if output_file.exists():
            return output_file
        
        nc_files = list(output_file.parent.glob("*.nc"))
        if nc_files:
            return nc_files[0]
        
        print(f"No output file found")
        return None
        
    except subprocess.TimeoutExpired:
        print("Download timed out")
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None


def gamma_correct(arr: np.ndarray, gamma: float = 2.2) -> np.ndarray:
    """Apply gamma correction for better visual contrast."""
    return np.power(np.clip(arr, 0, 1), 1.0 / gamma)


def convert_to_rgb_cog(nc_path: Path, date: str) -> Path | None:
    """
    Convert Rrs NetCDF to RGB Cloud-Optimized GeoTIFF.
    
    Rrs values are typically 0-0.03 sr⁻¹. We scale and gamma-correct
    for a natural-looking ocean visualization.
    """
    output_path = PRODUCTS_DIR / f"{date}.tif"
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        ds = xr.open_dataset(nc_path)
        
        # Find the bands (case insensitive)
        def find_var(name):
            for v in ds.data_vars:
                if v.upper() == name.upper():
                    return ds[v]
            return None
        
        red = find_var(RGB_BANDS["red"])
        green = find_var(RGB_BANDS["green"])
        blue = find_var(RGB_BANDS["blue"])
        
        if red is None or green is None or blue is None:
            print(f"Missing bands. Available: {list(ds.data_vars)}")
            return None
        
        # Squeeze time dimension
        if "time" in red.dims:
            red = red.isel(time=0)
            green = green.isel(time=0)
            blue = blue.isel(time=0)
        
        # Get data as float32
        r_data = red.values.astype(np.float32)
        g_data = green.values.astype(np.float32)
        b_data = blue.values.astype(np.float32)
        
        # Scale Rrs to 0-1 range (typical Rrs max ~0.03)
        # Use 98th percentile for scaling to handle outliers
        def scale_band(arr):
            valid = arr[~np.isnan(arr)]
            if len(valid) == 0:
                return arr
            vmin = 0
            vmax = np.percentile(valid, 98)
            if vmax <= vmin:
                vmax = 0.03  # Default max
            scaled = (arr - vmin) / (vmax - vmin)
            return gamma_correct(scaled)
        
        r_scaled = scale_band(r_data)
        g_scaled = scale_band(g_data)
        b_scaled = scale_band(b_data)
        
        # Convert to uint8 for RGB output
        def to_uint8(arr):
            result = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
            # Set nodata pixels to 0
            result[np.isnan(arr)] = 0
            return result
        
        r_uint8 = to_uint8(r_scaled)
        g_uint8 = to_uint8(g_scaled)
        b_uint8 = to_uint8(b_scaled)
        
        # Create alpha channel (255 where valid, 0 where nodata)
        alpha = np.where(np.isnan(r_data) | np.isnan(g_data) | np.isnan(b_data), 0, 255).astype(np.uint8)
        
        # Get coordinates
        lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
        lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
        
        # Ensure lat is descending
        if lat[0] < lat[-1]:
            r_uint8 = np.flipud(r_uint8)
            g_uint8 = np.flipud(g_uint8)
            b_uint8 = np.flipud(b_uint8)
            alpha = np.flipud(alpha)
            lat = lat[::-1]
        
        lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
        lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
        
        west = lon.min() - lon_res / 2
        east = lon.max() + lon_res / 2
        north = lat.max() + lat_res / 2
        south = lat.min() - lat_res / 2
        
        height, width = r_uint8.shape
        transform = from_bounds(west, south, east, north, width, height)
        
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 4,  # RGBA
            "dtype": "uint8",
            "crs": CRS.from_epsg(4326),
            "transform": transform,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "photometric": "RGB",
        }
        
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(r_uint8, 1)
            dst.write(g_uint8, 2)
            dst.write(b_uint8, 3)
            dst.write(alpha, 4)
            dst.update_tags(
                variable="Rrs RGB",
                bands="670nm/555nm/443nm",
                source="Copernicus Marine Ocean Colour",
                date=date,
            )
        
        # Build overviews
        with rasterio.open(output_path, "r+") as dst:
            dst.build_overviews([2, 4, 8, 16, 32], rasterio.enums.Resampling.average)
            dst.update_tags(ns="rio_overview", resampling="average")
        
        valid = (alpha > 0).sum()
        print(f"Valid pixels: {valid:,} / {width * height:,}")
        print(f"Created: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Conversion error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        ds.close()


def download_date(date: str) -> bool:
    """Download and convert Rrs for a single date."""
    output_path = PRODUCTS_DIR / f"{date}.tif"
    
    if output_path.exists():
        print(f"Already exists: {output_path}")
        return True
    
    nc_path = download_rrs_cmems(date)
    if nc_path is None:
        return False
    
    cog_path = convert_to_rgb_cog(nc_path, date)
    
    try:
        nc_path.unlink()
        nc_path.parent.rmdir()
    except Exception:
        pass
    
    return cog_path is not None


def main():
    parser = argparse.ArgumentParser(description="Download Rrs RGB from Copernicus Marine")
    parser.add_argument("start_date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("end_date", nargs="?", help="End date (YYYY-MM-DD), optional")
    args = parser.parse_args()
    
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else start
    
    current = start
    success = 0
    failed = 0
    
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        if download_date(date_str):
            success += 1
        else:
            failed += 1
        current += timedelta(days=1)
    
    print(f"\nComplete: {success} succeeded, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
