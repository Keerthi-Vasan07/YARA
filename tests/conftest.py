"""
Pytest configuration and shared fixtures for ECV integration tests.

This module provides fixtures for:
- Sample COG files (synthetic test data)
- Sample Zarr stores (pre-computed analytics)
- STAC catalog fixtures
- FastAPI test client
- Temporary directories for test outputs
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np


# =============================================================================
# Directory Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return path to test data directory (created if needed)."""
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def temp_products_dir(tmp_path: Path) -> Path:
    """Create temporary products directory structure."""
    products_dir = tmp_path / "products"
    for var in ["sst", "sic", "sla", "chl", "kd490", "rrs"]:
        (products_dir / var).mkdir(parents=True)
    return products_dir


@pytest.fixture
def temp_zarr_dir(tmp_path: Path) -> Path:
    """Create temporary zarr directory."""
    zarr_dir = tmp_path / "zarr"
    zarr_dir.mkdir(parents=True)
    return zarr_dir


@pytest.fixture
def temp_stac_dir(tmp_path: Path) -> Path:
    """Create temporary STAC directory structure."""
    stac_dir = tmp_path / "stac"
    (stac_dir / "collections").mkdir(parents=True)
    (stac_dir / "items").mkdir(parents=True)
    return stac_dir


# =============================================================================
# COG File Fixtures
# =============================================================================

@pytest.fixture
def sample_sst_cog(temp_products_dir: Path) -> Path:
    """Create a sample SST COG file."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    # Create synthetic SST data (int16 encoded, scale=0.01)
    # Valid SST range: -2°C to 35°C -> -200 to 3500 after encoding
    np.random.seed(42)
    data = np.random.randint(-200, 3500, (360, 720), dtype=np.int16)
    
    # Add some nodata (land) areas
    data[:50, :] = -32768  # Arctic land
    data[-50:, :] = -32768  # Antarctic land
    
    cog_path = temp_products_dir / "sst" / "2024-01-15.tif"
    
    profile = {
        "driver": "GTiff",
        "dtype": "int16",
        "width": 720,
        "height": 360,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": from_bounds(-180, -90, 180, 90, 720, 360),
        "nodata": -32768,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(
            variable="sst",
            units="degC",
            scale_factor="0.01",
            date="2024-01-15",
        )
    
    return cog_path


@pytest.fixture
def sample_sic_cog(temp_products_dir: Path) -> Path:
    """Create a sample SIC (Sea Ice Concentration) COG file."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    # SIC: uint8 0-100%, nodata=255
    np.random.seed(43)
    data = np.full((360, 720), 255, dtype=np.uint8)  # All nodata by default
    
    # Add Arctic ice (lat > 60°N -> rows 0-60)
    data[:60, :] = np.random.randint(0, 100, (60, 720), dtype=np.uint8)
    # Add Antarctic ice (lat < -60°S -> rows 300-360)
    data[300:, :] = np.random.randint(0, 100, (60, 720), dtype=np.uint8)
    
    cog_path = temp_products_dir / "sic" / "2024-01-15.tif"
    
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "width": 720,
        "height": 360,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": from_bounds(-180, -90, 180, 90, 720, 360),
        "nodata": 255,
        "compress": "deflate",
        "tiled": True,
    }
    
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(variable="sic", units="percent", date="2024-01-15")
    
    return cog_path


@pytest.fixture
def sample_cog_series(temp_products_dir: Path) -> list[Path]:
    """Create a series of SST COG files for time-series testing."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    cog_paths = []
    base_date = datetime(2024, 1, 1)
    
    for i in range(10):
        date = base_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        
        # Create synthetic SST with slight temporal variation
        np.random.seed(42 + i)
        data = np.random.randint(-200, 3500, (180, 360), dtype=np.int16)
        data[:25, :] = -32768  # Land
        
        cog_path = temp_products_dir / "sst" / f"{date_str}.tif"
        
        profile = {
            "driver": "GTiff",
            "dtype": "int16",
            "width": 360,
            "height": 180,
            "count": 1,
            "crs": CRS.from_epsg(4326),
            "transform": from_bounds(-180, -90, 180, 90, 360, 180),
            "nodata": -32768,
        }
        
        with rasterio.open(cog_path, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(variable="sst", date=date_str)
        
        cog_paths.append(cog_path)
    
    return cog_paths


# =============================================================================
# Zarr Store Fixtures
# =============================================================================

@pytest.fixture
def sample_zarr_store(temp_zarr_dir: Path) -> Path:
    """Create a sample Zarr store with pre-computed analytics."""
    import zarr
    
    zarr_path = temp_zarr_dir / "sst.zarr"
    
    # Create coordinate arrays
    n_times = 30
    nlat, nlon = 180, 360
    
    lat = np.linspace(90, -90, nlat).astype(np.float32)
    lon = np.linspace(-180, 180, nlon).astype(np.float32)
    time_values = np.arange(n_times, dtype=np.int32)  # Days since epoch
    
    # Create synthetic SST data (°C)
    np.random.seed(42)
    sst_data = np.random.rand(n_times, nlat, nlon).astype(np.float32) * 37 - 2
    
    # Add NaN for land areas
    sst_data[:, :20, :] = np.nan  # Arctic
    sst_data[:, -20:, :] = np.nan  # Antarctic
    
    root = zarr.open_group(str(zarr_path), mode="w")
    
    # Coordinate arrays
    root.create_array("lat", data=lat, chunks=(nlat,))
    root.create_array("lon", data=lon, chunks=(nlon,))
    root.create_array("time", data=time_values, chunks=(n_times,))
    
    # Main data array
    root.create_array("sst", data=sst_data, chunks=(10, 90, 180))
    
    # Pre-computed analytics
    with np.errstate(all='ignore'):
        clim_mean = np.nanmean(sst_data, axis=0)
        clim_std = np.nanstd(sst_data, axis=0)
        p10 = np.nanpercentile(sst_data, 10, axis=0)
        p50 = np.nanpercentile(sst_data, 50, axis=0)
        p90 = np.nanpercentile(sst_data, 90, axis=0)
    
    root.create_array("climatology_mean", data=clim_mean.astype(np.float32))
    root.create_array("climatology_std", data=clim_std.astype(np.float32))
    root.create_array("valid_count", data=np.sum(~np.isnan(sst_data), axis=0).astype(np.int16))
    root.create_array("percentile_10", data=p10.astype(np.float32))
    root.create_array("percentile_50", data=p50.astype(np.float32))
    root.create_array("percentile_90", data=p90.astype(np.float32))
    
    # Monthly climatology (12 months)
    monthly_mean = np.random.rand(12, nlat, nlon).astype(np.float32) * 35
    monthly_std = np.random.rand(12, nlat, nlon).astype(np.float32) * 5
    root.create_array("climatology_monthly_mean", data=monthly_mean)
    root.create_array("climatology_monthly_std", data=monthly_std)
    root.create_array("monthly_percentile_10", data=np.random.rand(12, nlat, nlon).astype(np.float32) * 30)
    root.create_array("monthly_percentile_50", data=np.random.rand(12, nlat, nlon).astype(np.float32) * 30)
    root.create_array("monthly_percentile_90", data=np.random.rand(12, nlat, nlon).astype(np.float32) * 30)
    
    # Trend
    root.create_array("trend", data=np.random.rand(nlat, nlon).astype(np.float32) * 0.1 - 0.05)
    
    # Month coordinate
    root.create_array("month", data=np.arange(1, 13, dtype=np.int32))
    
    # Metadata
    dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_times)]
    root.attrs["dates"] = dates
    root.attrs["title"] = "Test SST Dataset"
    root.attrs["source"] = "Test Data"
    root.attrs["global_stats"] = {
        "temporal_mean": float(np.nanmean(sst_data)),
        "temporal_std": float(np.nanstd(sst_data)),
        "n_timesteps": n_times,
    }
    
    return zarr_path


# =============================================================================
# STAC Catalog Fixtures
# =============================================================================

@pytest.fixture
def sample_stac_catalog(temp_stac_dir: Path, sample_cog_series: list[Path]) -> Path:
    """Create a sample STAC catalog from COG series."""
    # Root catalog
    catalog = {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": "test-ocean-ecv",
        "title": "Test Ocean ECV Catalog",
        "description": "Test STAC catalog for integration testing",
        "links": [
            {"rel": "self", "href": "./catalog.json", "type": "application/json"},
            {"rel": "root", "href": "./catalog.json", "type": "application/json"},
            {"rel": "child", "href": "./collections/sst.json", "type": "application/json"},
        ],
    }
    
    with open(temp_stac_dir / "catalog.json", "w") as f:
        json.dump(catalog, f, indent=2)
    
    # SST collection
    items_dir = temp_stac_dir / "items" / "sst"
    items_dir.mkdir(parents=True)
    
    dates = sorted([cog.stem for cog in sample_cog_series])
    
    collection = {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "sst",
        "title": "Sea Surface Temperature",
        "description": "Test SST collection",
        "extent": {
            "spatial": {"bbox": [[-180, -90, 180, 90]]},
            "temporal": {"interval": [[f"{dates[0]}T00:00:00Z", f"{dates[-1]}T23:59:59Z"]]},
        },
        "license": "proprietary",
        "links": [
            {"rel": "self", "href": "../collections/sst.json"},
            {"rel": "parent", "href": "../catalog.json"},
        ],
    }
    
    for date in dates:
        collection["links"].append({
            "rel": "item",
            "href": f"../items/sst/{date}.json",
        })
    
    with open(temp_stac_dir / "collections" / "sst.json", "w") as f:
        json.dump(collection, f, indent=2)
    
    # STAC items
    for cog_path in sample_cog_series:
        date = cog_path.stem
        item = {
            "type": "Feature",
            "stac_version": "1.0.0",
            "id": f"sst-{date}",
            "geometry": {"type": "Polygon", "coordinates": [[[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]]]},
            "bbox": [-180, -90, 180, 90],
            "properties": {
                "datetime": f"{date}T00:00:00Z",
                "variable": "sst",
            },
            "links": [
                {"rel": "self", "href": f"./{date}.json"},
                {"rel": "parent", "href": "../../collections/sst.json"},
                {"rel": "collection", "href": "../../collections/sst.json"},
            ],
            "assets": {
                "data": {
                    "href": str(cog_path),
                    "type": "image/tiff; application=geotiff",
                    "roles": ["data"],
                }
            },
        }
        
        with open(items_dir / f"{date}.json", "w") as f:
            json.dump(item, f, indent=2)
    
    return temp_stac_dir


# =============================================================================
# FastAPI Test Client Fixture
# =============================================================================

@pytest.fixture
def test_client(temp_products_dir: Path, temp_zarr_dir: Path, temp_stac_dir: Path, monkeypatch):
    """Create a FastAPI test client with mocked data directories."""
    from fastapi.testclient import TestClient
    
    # Monkeypatch settings to use temp directories
    monkeypatch.setenv("SST_PRODUCTS_SOURCE", "local")
    monkeypatch.setenv("SST_PRODUCTS_DIR", str(temp_products_dir))
    
    # Import app and dependencies after setting env vars
    from server.main import app
    import server.api.dependencies as deps_module
    
    # Override directory constants in the dependencies module
    monkeypatch.setattr(deps_module, "PRODUCTS_DIR", temp_products_dir)
    monkeypatch.setattr(deps_module, "ZARR_DIR", temp_zarr_dir)
    monkeypatch.setattr(deps_module, "STAC_DIR", temp_stac_dir)
    
    return TestClient(app)


@pytest.fixture
def test_client_with_data(
    test_client, 
    sample_sst_cog: Path, 
    sample_sic_cog: Path, 
    sample_sla_cog: Path,
    sample_chl_cog: Path,
    sample_kd490_cog: Path,
    sample_zarr_store: Path,
    sample_stac_catalog: Path,
    temp_zarr_dir: Path,
    monkeypatch,
):
    """Test client with sample data files pre-created for all ECVs."""
    # Link zarr store to expected location (more robust than copy)
    dest_zarr = temp_zarr_dir / "sst.zarr"
    if not dest_zarr.exists():
        try:
            # Try symlink first (most efficient)
            dest_zarr.symlink_to(sample_zarr_store)
        except (OSError, NotImplementedError):
            try:
                # Fallback to copy
                shutil.copytree(sample_zarr_store, dest_zarr, dirs_exist_ok=True)
            except shutil.Error:
                # If copy fails, just skip zarr setup (tests may still work)
                pass
    return test_client


# =============================================================================
# Sample NetCDF Fixtures (for downloader testing)
# =============================================================================

@pytest.fixture
def sample_sst_netcdf(tmp_path: Path) -> Path:
    """Create a sample SST NetCDF file (mimicking Copernicus Marine data)."""
    import xarray as xr
    import pandas as pd
    
    nc_path = tmp_path / "sst_nrt_2024-01-15.nc"
    
    # Create sample dataset matching Copernicus Marine format
    lat = np.linspace(-90, 90, 180)
    lon = np.linspace(-180, 180, 360)
    time = pd.date_range("2024-01-15", periods=1, freq="D")
    
    # SST in Kelvin (as delivered by Copernicus)
    sst_kelvin = np.random.rand(1, 180, 360).astype(np.float32) * 30 + 273.15
    sst_kelvin[:, :20, :] = np.nan  # Land
    
    ds = xr.Dataset(
        {
            "analysed_sst": (["time", "lat", "lon"], sst_kelvin, {
                "units": "kelvin",
                "long_name": "analysed sea surface temperature",
                "standard_name": "sea_surface_temperature",
            }),
            "analysis_error": (["time", "lat", "lon"], np.random.rand(1, 180, 360).astype(np.float32) * 0.5, {
                "units": "kelvin",
                "long_name": "estimated error standard deviation of analysed_sst",
            }),
        },
        coords={
            "time": time,
            "lat": lat,
            "lon": lon,
        },
    )
    
    ds.to_netcdf(nc_path)
    return nc_path


@pytest.fixture
def sample_sla_netcdf(tmp_path: Path) -> Path:
    """Create a sample SLA NetCDF file (mimicking Copernicus Marine data)."""
    import xarray as xr
    import pandas as pd
    
    nc_path = tmp_path / "sla_2024-01-15.nc"
    
    lat = np.linspace(-90, 90, 180)
    lon = np.linspace(-180, 180, 360)
    time = pd.date_range("2024-01-15", periods=1, freq="D")
    
    # SLA in meters
    sla = (np.random.rand(1, 180, 360).astype(np.float32) - 0.5) * 0.5  # -0.25m to +0.25m
    sla[:, :20, :] = np.nan  # Land
    
    ds = xr.Dataset(
        {
            "sla": (["time", "latitude", "longitude"], sla, {
                "units": "m",
                "long_name": "sea level anomaly",
                "standard_name": "sea_surface_height_above_sea_level",
            }),
        },
        coords={
            "time": time,
            "latitude": lat,
            "longitude": lon,
        },
    )
    
    ds.to_netcdf(nc_path)
    return nc_path


@pytest.fixture
def sample_chl_netcdf(tmp_path: Path) -> Path:
    """Create a sample CHL NetCDF file (mimicking Copernicus Marine data)."""
    import xarray as xr
    import pandas as pd
    
    nc_path = tmp_path / "chl_2024-01-15.nc"
    
    lat = np.linspace(-90, 90, 180)
    lon = np.linspace(-180, 180, 360)
    time = pd.date_range("2024-01-15", periods=1, freq="D")
    
    # CHL in mg/m³ (log-normal distribution typical)
    np.random.seed(44)
    chl = np.exp(np.random.randn(1, 180, 360).astype(np.float32) * 0.5 - 1)  # ~0.1-2 mg/m³
    chl[:, :20, :] = np.nan  # Land
    
    ds = xr.Dataset(
        {
            "CHL": (["time", "lat", "lon"], chl, {
                "units": "mg/m^3",
                "long_name": "chlorophyll-a concentration",
                "standard_name": "mass_concentration_of_chlorophyll_a_in_sea_water",
            }),
        },
        coords={
            "time": time,
            "lat": lat,
            "lon": lon,
        },
    )
    
    ds.to_netcdf(nc_path)
    return nc_path


@pytest.fixture
def sample_kd490_netcdf(tmp_path: Path) -> Path:
    """Create a sample KD490 NetCDF file (mimicking Copernicus Marine data)."""
    import xarray as xr
    import pandas as pd
    
    nc_path = tmp_path / "kd490_2024-01-15.nc"
    
    lat = np.linspace(-90, 90, 180)
    lon = np.linspace(-180, 180, 360)
    time = pd.date_range("2024-01-15", periods=1, freq="D")
    
    # Kd490 in m^-1 (typical ocean range 0.01-0.5)
    np.random.seed(45)
    kd490 = np.random.rand(1, 180, 360).astype(np.float32) * 0.3 + 0.02
    kd490[:, :20, :] = np.nan  # Land
    
    ds = xr.Dataset(
        {
            "KD490": (["time", "lat", "lon"], kd490, {
                "units": "m^-1",
                "long_name": "diffuse attenuation coefficient at 490nm",
                "standard_name": "volume_attenuation_coefficient_of_downwelling_radiative_flux_in_sea_water",
            }),
        },
        coords={
            "time": time,
            "lat": lat,
            "lon": lon,
        },
    )
    
    ds.to_netcdf(nc_path)
    return nc_path


@pytest.fixture
def sample_sic_netcdf(tmp_path: Path) -> Path:
    """Create a sample SIC NetCDF file (mimicking OSI SAF data)."""
    import xarray as xr
    import pandas as pd
    
    nc_path = tmp_path / "sic_2024-01-15.nc"
    
    lat = np.linspace(-90, 90, 180)
    lon = np.linspace(-180, 180, 360)
    time = pd.date_range("2024-01-15", periods=1, freq="D")
    
    # SIC in fraction 0-1 (will convert to %)
    np.random.seed(46)
    sic = np.zeros((1, 180, 360), dtype=np.float32)
    # Arctic ice (high latitudes)
    sic[:, :30, :] = np.random.rand(1, 30, 360).astype(np.float32) * 0.8 + 0.2
    # Antarctic ice
    sic[:, -30:, :] = np.random.rand(1, 30, 360).astype(np.float32) * 0.8 + 0.2
    
    ds = xr.Dataset(
        {
            "ice_conc": (["time", "lat", "lon"], sic, {
                "units": "1",
                "long_name": "sea ice concentration",
                "standard_name": "sea_ice_area_fraction",
            }),
        },
        coords={
            "time": time,
            "lat": lat,
            "lon": lon,
        },
    )
    
    ds.to_netcdf(nc_path)
    return nc_path


@pytest.fixture
def sample_rrs_netcdf(tmp_path: Path) -> Path:
    """Create a sample RRS NetCDF file (Remote Sensing Reflectance)."""
    import xarray as xr
    import pandas as pd
    
    nc_path = tmp_path / "rrs_2024-01-15.nc"
    
    lat = np.linspace(-90, 90, 180)
    lon = np.linspace(-180, 180, 360)
    time = pd.date_range("2024-01-15", periods=1, freq="D")
    
    # RRS values in sr^-1 (typical range 0.001-0.01)
    np.random.seed(47)
    rrs_443 = np.random.rand(1, 180, 360).astype(np.float32) * 0.01
    rrs_555 = np.random.rand(1, 180, 360).astype(np.float32) * 0.01
    rrs_670 = np.random.rand(1, 180, 360).astype(np.float32) * 0.005
    
    # Land mask
    rrs_443[:, :20, :] = np.nan
    rrs_555[:, :20, :] = np.nan
    rrs_670[:, :20, :] = np.nan
    
    ds = xr.Dataset(
        {
            "RRS443": (["time", "lat", "lon"], rrs_443, {"units": "sr^-1", "long_name": "Rrs at 443nm"}),
            "RRS555": (["time", "lat", "lon"], rrs_555, {"units": "sr^-1", "long_name": "Rrs at 555nm"}),
            "RRS670": (["time", "lat", "lon"], rrs_670, {"units": "sr^-1", "long_name": "Rrs at 670nm"}),
        },
        coords={
            "time": time,
            "lat": lat,
            "lon": lon,
        },
    )
    
    ds.to_netcdf(nc_path)
    return nc_path


@pytest.fixture
def sample_sla_cog(temp_products_dir: Path) -> Path:
    """Create a sample SLA (Sea Level Anomaly) COG file."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    # SLA: int16 encoded in mm, scale=0.001 to get meters
    np.random.seed(48)
    data = np.random.randint(-500, 500, (360, 720), dtype=np.int16)  # -0.5m to +0.5m
    data[:50, :] = -32768  # Land
    
    cog_path = temp_products_dir / "sla" / "2024-01-15.tif"
    
    profile = {
        "driver": "GTiff",
        "dtype": "int16",
        "width": 720,
        "height": 360,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": from_bounds(-180, -90, 180, 90, 720, 360),
        "nodata": -32768,
        "compress": "deflate",
        "tiled": True,
    }
    
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(variable="sla", units="m", scale_factor="0.001", date="2024-01-15")
    
    return cog_path


@pytest.fixture
def sample_chl_cog(temp_products_dir: Path) -> Path:
    """Create a sample CHL (Chlorophyll-a) COG file."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    # CHL: float32, typical range 0.01-30 mg/m³
    np.random.seed(49)
    data = np.exp(np.random.randn(360, 720).astype(np.float32) * 0.5 - 1)
    data[:50, :] = np.nan  # Land
    
    cog_path = temp_products_dir / "chl" / "2024-01-15.tif"
    
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": 720,
        "height": 360,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": from_bounds(-180, -90, 180, 90, 720, 360),
        "nodata": float("nan"),
        "compress": "deflate",
        "tiled": True,
    }
    
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(variable="chl", units="mg/m^3", date="2024-01-15")
    
    return cog_path


@pytest.fixture
def sample_kd490_cog(temp_products_dir: Path) -> Path:
    """Create a sample KD490 COG file."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    # KD490: float32, typical range 0.01-0.5 m^-1
    np.random.seed(50)
    data = np.random.rand(360, 720).astype(np.float32) * 0.3 + 0.02
    data[:50, :] = np.nan  # Land
    
    cog_path = temp_products_dir / "kd490" / "2024-01-15.tif"
    
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": 720,
        "height": 360,
        "count": 1,
        "crs": CRS.from_epsg(4326),
        "transform": from_bounds(-180, -90, 180, 90, 720, 360),
        "nodata": float("nan"),
        "compress": "deflate",
        "tiled": True,
    }
    
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(variable="kd490", units="m^-1", date="2024-01-15")
    
    return cog_path


@pytest.fixture
def sample_rrs_cog(temp_products_dir: Path) -> Path:
    """Create a sample RRS RGBA COG file."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    
    # RRS: RGBA uint8 (RGB composite)
    np.random.seed(51)
    r = np.random.randint(0, 255, (360, 720), dtype=np.uint8)
    g = np.random.randint(0, 255, (360, 720), dtype=np.uint8)
    b = np.random.randint(0, 255, (360, 720), dtype=np.uint8)
    a = np.full((360, 720), 255, dtype=np.uint8)
    a[:50, :] = 0  # Land (transparent)
    
    cog_path = temp_products_dir / "rrs" / "2024-01-15.tif"
    
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "width": 720,
        "height": 360,
        "count": 4,  # RGBA
        "crs": CRS.from_epsg(4326),
        "transform": from_bounds(-180, -90, 180, 90, 720, 360),
        "compress": "deflate",
        "tiled": True,
        "photometric": "RGBA",
    }
    
    with rasterio.open(cog_path, "w", **profile) as dst:
        dst.write(r, 1)
        dst.write(g, 2)
        dst.write(b, 3)
        dst.write(a, 4)
        dst.update_tags(variable="rrs", date="2024-01-15")
    
    return cog_path


@pytest.fixture
def all_ecv_cogs(
    sample_sst_cog: Path,
    sample_sic_cog: Path,
    sample_sla_cog: Path,
    sample_chl_cog: Path,
    sample_kd490_cog: Path,
    sample_rrs_cog: Path,
) -> dict[str, Path]:
    """Return dict of all ECV COG fixtures."""
    return {
        "sst": sample_sst_cog,
        "sic": sample_sic_cog,
        "sla": sample_sla_cog,
        "chl": sample_chl_cog,
        "kd490": sample_kd490_cog,
        "rrs": sample_rrs_cog,
    }


@pytest.fixture
def all_ecv_netcdfs(
    sample_sst_netcdf: Path,
    sample_sla_netcdf: Path,
    sample_chl_netcdf: Path,
    sample_kd490_netcdf: Path,
    sample_sic_netcdf: Path,
    sample_rrs_netcdf: Path,
) -> dict[str, Path]:
    """Return dict of all ECV NetCDF fixtures."""
    return {
        "sst": sample_sst_netcdf,
        "sla": sample_sla_netcdf,
        "chl": sample_chl_netcdf,
        "kd490": sample_kd490_netcdf,
        "sic": sample_sic_netcdf,
        "rrs": sample_rrs_netcdf,
    }


# =============================================================================
# Prefect Test Fixtures
# =============================================================================

@pytest.fixture
def prefect_ephemeral():
    """Configure Prefect to run in ephemeral mode (no server required).
    
    This enables running Prefect flows/tasks in tests without a Prefect server.
    Use this fixture for e2e tests that need to execute actual flows.
    """
    import os
    
    # Save current values
    old_api_url = os.environ.get("PREFECT_API_URL")
    old_home = os.environ.get("PREFECT_HOME")
    
    # Remove API URL to force local/ephemeral mode
    os.environ.pop("PREFECT_API_URL", None)
    
    # Also need to clear Prefect's cached client
    try:
        from prefect.context import _get_context_var
        # Clear any cached sync client context
        import prefect.context
        if hasattr(prefect.context, '_SyncClientContext'):
            prefect.context._SyncClientContext = None
    except Exception:
        pass
    
    yield
    
    # Restore original values
    if old_api_url is None:
        os.environ.pop("PREFECT_API_URL", None)
    else:
        os.environ["PREFECT_API_URL"] = old_api_url


# =============================================================================
# Pytest Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m not slow')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests (require prefect_ephemeral fixture)")
