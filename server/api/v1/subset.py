"""
Subset download endpoints for data extraction.
"""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Query, Response, HTTPException
from fastapi.responses import StreamingResponse
import numpy as np
import rasterio
from rasterio.windows import from_bounds

from server.config import settings
from server.api.dependencies import logger, VARIABLE_METADATA

router = APIRouter(prefix="/api", tags=["subset"])


@router.get("/{variable}/subset")
async def get_variable_subset(
    variable: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    north: float = Query(..., ge=-90, le=90, description="North boundary"),
    south: float = Query(..., ge=-90, le=90, description="South boundary"),
    east: float = Query(..., ge=-180, le=180, description="East boundary"),
    west: float = Query(..., ge=-180, le=180, description="West boundary"),
    format: str = Query("netcdf", pattern="^(netcdf|geotiff|csv)$", description="Output format"),
):
    """
    Download ECV data subset for a bounding box.
    
    Supports SST, SIC, SLA, CHL, Kd490 variables.
    Output formats: NetCDF (CF-compliant), GeoTIFF, CSV.
    """
    # Validate variable (rrs is RGBA, not supported for subset)
    if variable not in VARIABLE_METADATA:
        raise HTTPException(400, f"Unsupported variable: {variable}. Supported: {', '.join(VARIABLE_METADATA.keys())}")
    
    var_meta = VARIABLE_METADATA[variable]
    
    try:
        # Get COG path from config (handles local or Azure)
        cog_path = settings.get_cog_path(variable, date)
        
        # For local paths, verify file exists
        if settings.products_source == "local" and not Path(cog_path).exists():
            raise HTTPException(404, f"No {variable.upper()} data available for date {date}")
        
        with rasterio.open(cog_path) as src:
            # Get window for bbox
            window = from_bounds(west, south, east, north, src.transform)
            
            # Clamp window to valid extent
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            if window.width <= 0 or window.height <= 0:
                raise HTTPException(400, "Bounding box does not intersect data extent")
            
            # Read data
            data = src.read(1, window=window)
            transform = src.window_transform(window)
            crs = src.crs
            nodata = src.nodata
            
            # Get coordinate arrays
            height, width = data.shape
            cols, rows = np.meshgrid(np.arange(width), np.arange(height))
            xs, ys = rasterio.transform.xy(transform, rows.flatten(), cols.flatten())
            lons = np.array(xs).reshape(height, width)
            lats = np.array(ys).reshape(height, width)
        
        # Handle different output formats
        if format == "csv":
            # Generate CSV with variable-specific column name
            csv_column = var_meta.get("csv_column", variable)
            lines = [f"latitude,longitude,{csv_column}"]
            valid_mask = ~np.isnan(data) if nodata is None else (data != nodata) & ~np.isnan(data)
            
            for i in range(height):
                for j in range(width):
                    if valid_mask[i, j]:
                        lines.append(f"{lats[i,j]:.4f},{lons[i,j]:.4f},{data[i,j]:.2f}")
            
            csv_content = "\n".join(lines)
            
            return StreamingResponse(
                iter([csv_content]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{variable}_{date}_{south:.1f}_{north:.1f}_{west:.1f}_{east:.1f}.csv"'
                }
            )
        
        elif format == "geotiff":
            # Create a GeoTIFF in memory
            with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
                with rasterio.open(
                    tmp.name, 'w',
                    driver='GTiff',
                    height=height,
                    width=width,
                    count=1,
                    dtype=data.dtype,
                    crs=crs,
                    transform=transform,
                    nodata=nodata,
                ) as dst:
                    dst.write(data, 1)
                    dst.set_band_description(1, f"{var_meta['name']} {date}")
                
                # Read file and return
                with open(tmp.name, 'rb') as f:
                    content = f.read()
                
                os.unlink(tmp.name)
                
            return Response(
                content=content,
                media_type="image/tiff",
                headers={
                    "Content-Disposition": f'attachment; filename="{variable}_{date}_{south:.1f}_{north:.1f}_{west:.1f}_{east:.1f}.tif"'
                }
            )
        
        else:  # netcdf
            # Create NetCDF file with CF-compliant metadata
            import xarray as xr
            
            # Create coordinate arrays
            lat_coords = lats[:, 0]  # First column (all same)
            lon_coords = lons[0, :]  # First row (all same)
            
            # Create xarray dataset with variable-specific attributes
            ds = xr.Dataset(
                {
                    variable: (["lat", "lon"], data, {
                        "units": var_meta.get("cf_units", var_meta["unit"]),
                        "long_name": var_meta.get("cf_long_name", var_meta["name"]),
                        "standard_name": var_meta.get("cf_standard_name", ""),
                        "_FillValue": np.nan,
                    })
                },
                coords={
                    "lat": (["lat"], lat_coords, {
                        "units": "degrees_north",
                        "long_name": "latitude",
                        "standard_name": "latitude",
                    }),
                    "lon": (["lon"], lon_coords, {
                        "units": "degrees_east",
                        "long_name": "longitude",
                        "standard_name": "longitude",
                    }),
                    "time": date,
                },
                attrs={
                    "title": f"{var_meta['name']} subset for {date}",
                    "institution": var_meta.get("source", "Unknown"),
                    "source": var_meta.get("dataset", ""),
                    "Conventions": "CF-1.6",
                    "geospatial_lat_min": float(south),
                    "geospatial_lat_max": float(north),
                    "geospatial_lon_min": float(west),
                    "geospatial_lon_max": float(east),
                }
            )
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
                ds.to_netcdf(tmp.name, format="NETCDF4")
                
                with open(tmp.name, 'rb') as f:
                    content = f.read()
                
                os.unlink(tmp.name)
            
            return Response(
                content=content,
                media_type="application/x-netcdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{variable}_{date}_{south:.1f}_{north:.1f}_{west:.1f}_{east:.1f}.nc"'
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating subset")
        raise HTTPException(500, f"Error creating subset: {str(e)}")
