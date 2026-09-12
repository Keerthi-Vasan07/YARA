#!/usr/bin/env python3
"""
Download Kd490 (Diffuse Attenuation Coefficient) from Copernicus Marine Service.

Kd490 measures how quickly light attenuates with depth at 490nm wavelength.
It indicates water clarity and euphotic zone depth - key for primary productivity.

Usage:
    python download_kd490.py 2024-01-15
    python download_kd490.py 2024-01-15 2024-01-20  # Date range
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


# L4 gap-free products for full ocean coverage
KD490_DATASETS = {
    "nrt": {
        "dataset_id": "cmems_obs-oc_glo_bgc-transp_nrt_l4-gapfree-multi-4km_P1D",
        "variable": "KD490",
    },
    "rep": {
        "dataset_id": "cmems_obs-oc_glo_bgc-transp_my_l4-gapfree-multi-4km_P1D",
        "variable": "KD490",
    },
}

PRODUCTS_DIR = Path(__file__).parent / "products" / "kd490"


def download_kd490_cmems(date: str, stream: str = "nrt") -> Path | None:
    """
    Download Kd490 data using copernicusmarine CLI.
    
    Args:
        date: Date in YYYY-MM-DD format
        stream: 'nrt' or 'rep'
    
    Returns:
        Path to downloaded NetCDF file, or None if failed
    """
    config = KD490_DATASETS.get(stream, KD490_DATASETS["nrt"])
    dataset_id = config["dataset_id"]
    variable = config["variable"]
    
    output_file = Path(tempfile.mkdtemp()) / f"kd490_{date}.nc"
    
    start_date = f"{date}T00:00:00"
    end_date = f"{date}T23:59:59"
    
    cmd = [
        "copernicusmarine", "subset",
        "--dataset-id", dataset_id,
        "--variable", variable,
        "--start-datetime", start_date,
        "--end-datetime", end_date,
        "--minimum-longitude", "-180",
        "--maximum-longitude", "180",
        "--minimum-latitude", "-90",
        "--maximum-latitude", "90",
        "-o", str(output_file.parent),
        "-f", output_file.name,
    ]
    
    print(f"Downloading Kd490 for {date} ({stream})...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"Download failed: {result.stderr}")
            if stream == "nrt":
                print("Trying REP stream...")
                return download_kd490_cmems(date, "rep")
            return None
        
        if output_file.exists():
            return output_file
        
        nc_files = list(output_file.parent.glob("*.nc"))
        if nc_files:
            return nc_files[0]
        
        print(f"No output file found in {output_file.parent}")
        return None
        
    except subprocess.TimeoutExpired:
        print("Download timed out")
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None


def convert_to_cog(nc_path: Path, date: str) -> Path | None:
    """
    Convert Kd490 NetCDF to Cloud-Optimized GeoTIFF.
    
    Kd490 values typically range from 0.01 (clear open ocean) to 
    5+ m⁻¹ (turbid coastal waters). Log scale visualization recommended.
    
    Args:
        nc_path: Path to input NetCDF
        date: Date string for output filename
    
    Returns:
        Path to output COG, or None if failed
    """
    output_path = PRODUCTS_DIR / f"{date}.tif"
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        ds = xr.open_dataset(nc_path)
        
        # Find Kd490 variable
        kd = None
        for var in ["KD490", "kd490", "Kd490"]:
            if var in ds:
                kd = ds[var]
                break
        
        if kd is None:
            for var in ds.data_vars:
                if "kd" in var.lower():
                    kd = ds[var]
                    break
        
        if kd is None:
            print(f"Could not find Kd490 variable in {ds.data_vars}")
            return None
        
        # Squeeze time dimension
        if "time" in kd.dims:
            kd = kd.isel(time=0)
        
        data = kd.values.astype(np.float32)
        
        # Get coordinates
        lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
        lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
        
        # Ensure lat is descending
        if lat[0] < lat[-1]:
            data = np.flipud(data)
            lat = lat[::-1]
        
        lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
        lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
        
        west = lon.min() - lon_res / 2
        east = lon.max() + lon_res / 2
        north = lat.max() + lat_res / 2
        south = lat.min() - lat_res / 2
        
        height, width = data.shape
        transform = from_bounds(west, south, east, north, width, height)
        
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": CRS.from_epsg(4326),
            "transform": transform,
            "nodata": np.nan,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "predictor": 2,
        }
        
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(
                variable="KD490",
                units="m^-1",
                source="Copernicus Marine Ocean Colour",
                date=date,
            )
        
        # Build overviews
        with rasterio.open(output_path, "r+") as dst:
            dst.build_overviews([2, 4, 8, 16, 32], rasterio.enums.Resampling.average)
            dst.update_tags(ns="rio_overview", resampling="average")
        
        with rasterio.open(output_path) as src:
            valid = (~np.isnan(src.read(1))).sum()
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
    """Download and convert Kd490 for a single date."""
    output_path = PRODUCTS_DIR / f"{date}.tif"
    
    if output_path.exists():
        print(f"Already exists: {output_path}")
        return True
    
    nc_path = download_kd490_cmems(date)
    if nc_path is None:
        return False
    
    cog_path = convert_to_cog(nc_path, date)
    
    try:
        nc_path.unlink()
        nc_path.parent.rmdir()
    except Exception:
        pass
    
    return cog_path is not None


def main():
    parser = argparse.ArgumentParser(description="Download Kd490 from Copernicus Marine")
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
