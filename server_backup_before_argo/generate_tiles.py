"""
Generate Cloud Optimized GeoTIFFs (COGs) for SST data.

These can be served via Martin or any tile server that supports COGs.
Each month produces one styled RGB COG with the thermal colormap applied.

Run:
    python -m server.generate_tiles [--months N]
"""

import argparse
import json
import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from pathlib import Path
from datetime import datetime
from scipy.interpolate import griddata
from scipy.spatial import cKDTree
from cartopy.io import shapereader as shpreader
from shapely.ops import unary_union
from shapely import contains_xy
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from .config import settings

# Output directories
TILES_DIR = Path(__file__).parent / "tiles"
CACHE_DIR = Path(__file__).parent / "cache"

# Use cmocean thermal or fall back to turbo
try:
    import cmocean
    SST_CMAP = cmocean.cm.thermal
except ImportError:
    SST_CMAP = plt.cm.turbo

# Temperature range for colormap (matching notebook)
SST_VMIN = -2.0
SST_VMAX = 20.0
SST_BOUNDARIES = np.arange(-2, 21, 1)  # 1°C discrete steps like notebook


def sst_to_rgb(sst: np.ndarray, vmin: float = SST_VMIN, vmax: float = SST_VMAX) -> np.ndarray:
    """
    Convert SST values to RGB using the thermal colormap with discrete bands.
    
    Uses BoundaryNorm for discrete 1°C color steps like the notebook.
    """
    # Simple linear normalization to 0-1 range
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    normalized = norm(sst)
    
    # Apply colormap (returns RGBA floats 0-1)
    rgba = SST_CMAP(normalized)
    
    # Convert to uint8 RGB
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    
    return rgb


def generate_sst_cog(
    ds: xr.Dataset,
    region_ds: xr.Dataset, 
    sst_monthly: xr.DataArray,
    date: str,
    resolution: int = 1024,
    output_dir: Path = TILES_DIR,
    land_geom = None,
) -> Path:
    """
    Generate a styled COG for a specific date with land masking.
    
    Returns the path to the generated COG file.
    """
    target_time = np.datetime64(date)
    times = sst_monthly.time.values
    idx = np.abs(times - target_time).argmin()
    selected_time = times[idx]
    
    # Load SST data for this timestamp
    sst_slice = sst_monthly.sel(time=selected_time).load()
    
    lon = region_ds["longitude"].values
    lat = region_ds["latitude"].values
    vals = sst_slice.values
    
    # Filter valid points
    valid = np.isfinite(vals) & np.isfinite(lon) & np.isfinite(lat)
    lon_v, lat_v, z_v = lon[valid], lat[valid], vals[valid]
    
    if lon_v.size < 10:
        raise ValueError("Not enough valid points for interpolation")
    
    # Create high-resolution regular grid
    # Use aspect-aware resolution like the notebook
    lon_range = settings.default_lon_max - settings.default_lon_min
    lat_range = settings.default_lat_max - settings.default_lat_min
    aspect = lon_range / lat_range
    
    ny = resolution
    nx = int(resolution * aspect)
    
    xi = np.linspace(settings.default_lon_min, settings.default_lon_max, nx)
    yi = np.linspace(settings.default_lat_min, settings.default_lat_max, ny)
    Xi, Yi = np.meshgrid(xi, yi)
    
    # Use triangulation-based interpolation like the notebook for best quality
    import matplotlib.tri as mtri
    
    # Create triangulation with quality filter
    tri = mtri.Triangulation(lon_v, lat_v)
    try:
        tri.set_mask(mtri.TriAnalyzer(tri).get_flat_tri_mask(min_circle_ratio=0.0005))
    except Exception:
        pass
    
    # Linear interpolation on triangulation (smoother than griddata cubic at edges)
    Zi = mtri.LinearTriInterpolator(tri, z_v)(Xi, Yi)
    Zi = np.asarray(Zi)  # Convert from masked array
    
    # Nearest-neighbor backfill for areas outside triangulation hull
    nan_mask = np.isnan(Zi)
    if nan_mask.any():
        mean_lat = float(np.nanmean(lat_v))
        cos_phi = np.cos(np.deg2rad(mean_lat))
        tree = cKDTree(np.c_[lon_v * cos_phi, lat_v])
        _, idx_nn = tree.query(np.c_[Xi[nan_mask] * cos_phi, Yi[nan_mask]], k=1)
        Zi[nan_mask] = z_v[idx_nn]
    
    # Apply land masking (like the notebook)
    if land_geom is not None:
        land_mask = contains_xy(land_geom, Xi, Yi)
        Zi[land_mask] = np.nan
    
    # Convert to RGB using discrete colormap (no contours - they don't work on 3D globes)
    rgb = sst_to_rgb(Zi)
    
    # Create alpha channel (opaque where we have data)
    alpha = np.where(np.isnan(Zi), 0, 255).astype(np.uint8)
    
    # Flip for proper GeoTIFF orientation (north up)
    rgb = np.flipud(rgb)
    alpha = np.flipud(alpha)
    
    # Prepare for rasterio (bands, height, width)
    # RGB is (height, width, 3), need (3, height, width)
    rgba_bands = np.concatenate([
        np.transpose(rgb, (2, 0, 1)),  # RGB bands
        alpha[np.newaxis, :, :]  # Alpha band
    ], axis=0)
    
    # Get actual dimensions from the array
    height, width = Zi.shape
    
    # Define geospatial transform
    transform = from_bounds(
        settings.default_lon_min,
        settings.default_lat_min,
        settings.default_lon_max,
        settings.default_lat_max,
        width,
        height
    )
    
    # Output filename
    date_str = str(np.datetime_as_string(selected_time, unit='D'))
    output_path = output_dir / f"sst_{date_str}.tif"
    
    # Write COG with overviews for better tile serving
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=4,  # RGBA
        dtype=np.uint8,
        crs='EPSG:4326',
        transform=transform,
        compress='deflate',
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(rgba_bands)
        # Build overviews for faster tile serving
        dst.build_overviews([2, 4, 8], rasterio.enums.Resampling.bilinear)
        dst.update_tags(ns='rio_overview', resampling='bilinear')
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate SST COG tiles')
    parser.add_argument('--months', type=int, default=12, 
                        help='Number of recent months to generate (default: 12)')
    parser.add_argument('--resolution', type=int, default=1024,
                        help='Tile resolution height in pixels (default: 1024)')
    parser.add_argument('--all', action='store_true',
                        help='Generate all available months')
    args = parser.parse_args()
    
    print("Loading ARCO ERA5 dataset...")
    
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
    
    # Normalize longitudes
    ds = ds.assign_coords({
        "longitude": ((ds["longitude"] + 180) % 360) - 180
    })
    
    # Regional subset
    print("Computing regional subset...")
    lon_np = ds["longitude"].load().values
    lat_np = ds["latitude"].load().values
    
    bbox_mask = (
        (lon_np >= settings.default_lon_min) &
        (lon_np <= settings.default_lon_max) &
        (lat_np >= settings.default_lat_min) &
        (lat_np <= settings.default_lat_max)
    )
    bbox_idx = np.where(bbox_mask)[0]
    region_ds = ds.isel(values=bbox_idx)
    
    # Prepare SST data
    sst = region_ds["sst"]
    ci = region_ds["siconc"]
    sst_C = (sst - 273.15).astype('float32')
    sst_C = sst_C.where(ci <= settings.ice_threshold)
    sst_monthly = sst_C.resample(time="1MS").mean()
    
    # Load land geometry for masking (like the notebook)
    print("Loading land geometry for masking...")
    land_shp = shpreader.natural_earth(resolution='50m', category='physical', name='land')
    land_geom = unary_union(list(shpreader.Reader(land_shp).geometries()))
    try:
        land_geom = land_geom.buffer(0.01)  # tiny buffer to avoid coastal bleed
    except Exception:
        pass
    
    # Load time metadata
    with open(CACHE_DIR / "time_metadata.json") as f:
        metadata = json.load(f)
    
    available_dates = metadata["available_dates"]
    
    if args.all:
        dates_to_process = available_dates
    else:
        dates_to_process = available_dates[-args.months:]
    
    print(f"Generating COGs for {len(dates_to_process)} months...")
    
    for i, date in enumerate(dates_to_process):
        print(f"  [{i+1}/{len(dates_to_process)}] {date}...", end=" ", flush=True)
        try:
            output_path = generate_sst_cog(
                ds, region_ds, sst_monthly, date, 
                resolution=args.resolution,
                land_geom=land_geom
            )
            print(f"✓ {output_path.name}")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\nCOGs saved to {TILES_DIR}")
    print("\nTo serve with Martin, create martin.yaml:")
    print(f"""
sources:
  sst:
    type: raster
    path: {TILES_DIR}/*.tif
""")


if __name__ == "__main__":
    main()
