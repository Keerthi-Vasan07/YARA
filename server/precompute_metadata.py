"""
Precompute and cache SST metadata locally.

This script computes the available time range from the ARCO ERA5 dataset
and saves it to a local JSON file for fast API responses.

Run this once to generate the metadata cache:
    python -m server.precompute_metadata
"""

import json
import numpy as np
import xarray as xr
from pathlib import Path
from datetime import datetime

from .config import settings

CACHE_DIR = Path(__file__).parent / "cache"
METADATA_FILE = CACHE_DIR / "time_metadata.json"


def precompute_time_metadata():
    """Compute and cache available months from ARCO ERA5 dataset."""
    print("Opening ARCO ERA5 dataset...")
    
    ds = xr.open_zarr(
        settings.zarr_path,
        chunks="auto",
        storage_options={"token": "anon"},
        decode_timedelta=False,
    )
    
    # Restrict to valid time range
    valid_start = ds.attrs.get('valid_time_start')
    valid_stop = ds.attrs.get('valid_time_stop')
    
    if valid_start and valid_stop:
        ds = ds.sel(time=slice(valid_start, valid_stop))
        print(f"Valid time range: {valid_start} to {valid_stop}")
    
    # Get unique months from the time coordinate
    times = ds.time.values
    print(f"Total time steps: {len(times)}")
    
    # Convert to monthly (first of each month)
    unique_months = set()
    for t in times:
        dt = np.datetime64(t, 'M')  # Truncate to month
        unique_months.add(str(dt))
    
    # Sort and format as YYYY-MM-01
    sorted_months = sorted(unique_months)
    available_dates = [f"{m}-01" for m in sorted_months]
    
    # Build metadata structure with year/month grouping for UI
    years_data = {}
    for date_str in available_dates:
        year = int(date_str[:4])
        month = int(date_str[5:7])
        if year not in years_data:
            years_data[year] = []
        years_data[year].append(month)
    
    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": settings.zarr_path,
        "total_months": len(available_dates),
        "start_date": available_dates[0] if available_dates else None,
        "end_date": available_dates[-1] if available_dates else None,
        "available_dates": available_dates,
        "years": {str(y): months for y, months in sorted(years_data.items())},
    }
    
    # Save to cache
    CACHE_DIR.mkdir(exist_ok=True)
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nMetadata saved to {METADATA_FILE}")
    print(f"Total months: {len(available_dates)}")
    print(f"Date range: {available_dates[0]} to {available_dates[-1]}")
    print(f"Years covered: {min(years_data.keys())} - {max(years_data.keys())}")
    
    return metadata


if __name__ == "__main__":
    precompute_time_metadata()
