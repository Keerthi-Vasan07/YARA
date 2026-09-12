#!/usr/bin/env python3
"""
Download Chlorophyll-a data from Copernicus Marine Service and convert to COG.

Usage:
    python download_chl.py 2024-01-15
    python download_chl.py 2024-01-15 2024-01-20  # Date range
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


# Dataset configuration - L4 gap-free products for full ocean coverage
# L3 = multi-sensor merged with gaps, L4 = gap-filled interpolated analysis
CHL_DATASETS = {
    "nrt": {
        "dataset_id": "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
        "variable": "CHL",
    },
    "rep": {
        "dataset_id": "cmems_obs-oc_glo_bgc-plankton_my_l4-gapfree-multi-4km_P1D",
        "variable": "CHL",
    },
}

PRODUCTS_DIR = Path(__file__).parent / "products" / "chl"


def download_chl_cmems(date: str, stream: str = "nrt") -> Path | None:
    """
    Download CHL data using copernicusmarine CLI.
    
    Args:
        date: Date in YYYY-MM-DD format
        stream: 'nrt' or 'rep'
    
    Returns:
        Path to downloaded NetCDF file, or None if failed
    """
    config = CHL_DATASETS.get(stream, CHL_DATASETS["nrt"])
    dataset_id = config["dataset_id"]
    variable = config["variable"]
    
    # Create temp file for download
    output_file = Path(tempfile.mkdtemp()) / f"chl_{date}.nc"
    
    # Date range (single day)
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
        "--force-download",
    ]
    
    print(f"Downloading CHL for {date} ({stream})...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"Download failed: {result.stderr}")
            # Try alternate stream
            if stream == "nrt":
                print("Trying REP stream...")
                return download_chl_cmems(date, "rep")
            return None
        
        # Check for downloaded file (copernicusmarine may adjust filename)
        if output_file.exists():
            return output_file
        
        # Look for any .nc file in output dir
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
    Convert CHL NetCDF to Cloud-Optimized GeoTIFF.
    
    CHL values span ~0.01 to 100 mg/m³. We use float32 to preserve
    precision for log-scale visualization.
    
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
        
        # Get CHL variable
        if "CHL" in ds:
            chl = ds["CHL"]
        elif "chl" in ds:
            chl = ds["chl"]
        else:
            # Try to find it
            for var in ds.data_vars:
                if "chl" in var.lower():
                    chl = ds[var]
                    break
            else:
                print(f"Could not find CHL variable in {ds.data_vars}")
                return None
        
        # Squeeze time dimension if present
        if "time" in chl.dims:
            chl = chl.isel(time=0)
        
        # Get data as float32
        data = chl.values.astype(np.float32)
        
        # Get coordinates
        lat = ds["lat"].values if "lat" in ds else ds["latitude"].values
        lon = ds["lon"].values if "lon" in ds else ds["longitude"].values
        
        # Ensure lat is descending (north to south)
        if lat[0] < lat[-1]:
            data = np.flipud(data)
            lat = lat[::-1]
        
        # Get bounds
        lat_res = abs(lat[1] - lat[0]) if len(lat) > 1 else 0.05
        lon_res = abs(lon[1] - lon[0]) if len(lon) > 1 else 0.05
        
        west = lon.min() - lon_res / 2
        east = lon.max() + lon_res / 2
        north = lat.max() + lat_res / 2
        south = lat.min() - lat_res / 2
        
        height, width = data.shape
        transform = from_bounds(west, south, east, north, width, height)
        
        # Set nodata (NaN for ocean color products)
        nodata = np.nan
        
        # Write COG
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": CRS.from_epsg(4326),
            "transform": transform,
            "nodata": nodata,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "predictor": 2,
        }
        
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(
                variable="CHL",
                units="mg/m³",
                source="Copernicus Marine Ocean Colour",
                date=date,
            )
        
        # Build overviews
        with rasterio.open(output_path, "r+") as dst:
            dst.build_overviews([2, 4, 8, 16, 32], rasterio.enums.Resampling.average)
            dst.update_tags(ns="rio_overview", resampling="average")
        
        # Validate
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
    """Download and convert CHL for a single date."""
    output_path = PRODUCTS_DIR / f"{date}.tif"
    
    # Skip if already exists
    if output_path.exists():
        print(f"Already exists: {output_path}")
        return True
    
    # Download NetCDF
    nc_path = download_chl_cmems(date)
    if nc_path is None:
        return False
    
    # Convert to COG
    cog_path = convert_to_cog(nc_path, date)
    
    # Cleanup temp file
    try:
        nc_path.unlink()
        nc_path.parent.rmdir()
    except Exception:
        pass
    
    return cog_path is not None


def main():
    parser = argparse.ArgumentParser(description="Download CHL data from Copernicus Marine")
    parser.add_argument("start_date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("end_date", nargs="?", help="End date (YYYY-MM-DD), optional")
    parser.add_argument("--stream", choices=["nrt", "rep"], default="nrt", help="Data stream")
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
