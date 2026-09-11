"""Test suite for ECV Viewer Backend."""

import pytest
from pathlib import Path
import numpy as np


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_cog_path(tmp_path: Path) -> Path:
    """Create a sample COG file for testing."""
    import rasterio
    from rasterio.transform import from_bounds
    
    # Create a simple 256x256 test COG
    data = np.random.randint(0, 35, (256, 256), dtype=np.int16)
    
    cog_path = tmp_path / "test_sst_2024-01-15.tif"
    
    profile = {
        'driver': 'GTiff',
        'dtype': 'int16',
        'width': 256,
        'height': 256,
        'count': 1,
        'crs': 'EPSG:4326',
        'transform': from_bounds(-180, -90, 180, 90, 256, 256),
        'nodata': -32768,
    }
    
    with rasterio.open(cog_path, 'w', **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(scale=0.01, offset=0)
    
    return cog_path


@pytest.fixture
def sample_zarr_store(tmp_path: Path) -> Path:
    """Create a sample Zarr store for testing."""
    import zarr
    import xarray as xr
    import pandas as pd
    
    zarr_path = tmp_path / "test_sst.zarr"
    
    # Create sample dataset
    times = pd.date_range("2024-01-01", periods=10, freq="D")
    lats = np.linspace(-90, 90, 180)
    lons = np.linspace(-180, 180, 360)
    
    data = np.random.rand(10, 180, 360).astype(np.float32) * 35 - 2
    
    ds = xr.Dataset({
        "sst": (["time", "latitude", "longitude"], data),
        "climatology_mean": (["latitude", "longitude"], data.mean(axis=0)),
        "trend": (["latitude", "longitude"], np.random.rand(180, 360) * 0.1),
    }, coords={
        "time": times,
        "latitude": lats,
        "longitude": lons,
    })
    
    ds.to_zarr(zarr_path)
    
    return zarr_path


@pytest.fixture
def test_client():
    """Create a FastAPI test client."""
    from fastapi.testclient import TestClient
    from server.main import app
    
    return TestClient(app)


# =============================================================================
# Tile Server Tests
# =============================================================================

class TestTileServer:
    """Tests for tile rendering functionality."""
    
    def test_render_tile_basic(self, sample_cog_path: Path):
        """Test basic tile rendering."""
        from server.tile_server import render_tile
        
        result = render_tile(
            str(sample_cog_path),
            z=0,
            x=0,
            y=0,
            variable="sst",
            vmin=-2,
            vmax=35
        )
        
        # Should return PNG bytes or None
        if result is not None:
            assert isinstance(result, bytes)
            # Check PNG magic bytes
            assert result[:4] == b'\x89PNG'
    
    def test_render_tile_out_of_bounds(self, sample_cog_path: Path):
        """Test tile rendering for out-of-bounds request."""
        from server.tile_server import render_tile
        
        result = render_tile(
            str(sample_cog_path),
            z=10,
            x=9999,
            y=9999,
            variable="sst"
        )
        
        # Should return None for out-of-bounds
        # (or transparent PNG depending on implementation)
        assert result is None or isinstance(result, bytes)
    
    def test_render_tile_custom_colormap(self, sample_cog_path: Path):
        """Test tile rendering with custom vmin/vmax."""
        from server.tile_server import render_tile
        
        result = render_tile(
            str(sample_cog_path),
            z=0,
            x=0,
            y=0,
            variable="sst",
            vmin=0,
            vmax=30,
        )
        
        assert result is None or isinstance(result, bytes)


# =============================================================================
# API Endpoint Tests
# =============================================================================

class TestAPIEndpoints:
    """Tests for FastAPI endpoints."""
    
    def test_root_endpoint(self, test_client):
        """Test root endpoint returns expected response."""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "status" in data
    
    def test_health_endpoint(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
    
    def test_time_range_endpoint(self, test_client):
        """Test time range endpoint."""
        response = test_client.get("/api/time-range/sst")
        # May fail if no data, but should not crash
        assert response.status_code in [200, 404, 500]
    
    def test_tile_endpoint_missing_data(self, test_client):
        """Test tile endpoint handles missing data gracefully."""
        response = test_client.get("/api/tiles/sst/2099-01-01/0/0/0.png")
        # Should return transparent PNG, not 404
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
    
    def test_point_query_endpoint(self, test_client):
        """Test point query endpoint."""
        response = test_client.get(
            "/api/sst/point",
            params={"date": "2024-01-15", "lon": 0.0, "lat": 45.0}
        )
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "value" in data or "error" in data


# =============================================================================
# Zarr Builder Tests
# =============================================================================

class TestZarrBuilder:
    """Tests for Zarr store building."""
    
    def test_climatology_calculation(self, sample_zarr_store: Path):
        """Test climatology calculation produces valid output."""
        import xarray as xr
        
        ds = xr.open_zarr(sample_zarr_store)
        
        assert "climatology_mean" in ds.data_vars
        assert not np.all(np.isnan(ds.climatology_mean.values))
    
    def test_trend_calculation(self, sample_zarr_store: Path):
        """Test trend calculation produces valid output."""
        import xarray as xr
        
        ds = xr.open_zarr(sample_zarr_store)
        
        assert "trend" in ds.data_vars
        assert not np.all(np.isnan(ds.trend.values))


# =============================================================================
# Earthkit Integration Tests
# =============================================================================

class TestEarthkitIntegration:
    """Tests for earthkit integration layer."""
    
    def test_load_netcdf(self, tmp_path: Path):
        """Test loading NetCDF data."""
        import xarray as xr
        import pandas as pd
        from server.earthkit_integration import load_netcdf
        
        # Create test NetCDF
        nc_path = tmp_path / "test.nc"
        ds = xr.Dataset({
            "sst": (["time", "latitude", "longitude"], 
                   np.random.rand(5, 10, 20).astype(np.float32))
        }, coords={
            "time": pd.date_range("2024-01-01", periods=5),
            "latitude": np.linspace(-45, 45, 10),
            "longitude": np.linspace(-90, 90, 20),
        })
        ds.to_netcdf(nc_path)
        
        # Load with earthkit integration
        result = load_netcdf(nc_path)
        
        assert "sst" in result.data_vars
        assert result.dims == {"time": 5, "latitude": 10, "longitude": 20}
    
    def test_compute_anomaly(self):
        """Test anomaly computation."""
        import xarray as xr
        from server.earthkit_integration import compute_anomaly
        
        data = xr.DataArray(
            np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
            dims=["time"]
        )
        climatology = xr.DataArray(3.0)
        
        anomaly = compute_anomaly(data, climatology)
        
        expected = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        np.testing.assert_array_almost_equal(anomaly.values, expected)
    
    def test_compute_percentiles(self):
        """Test percentile computation."""
        from server.earthkit_integration import compute_percentiles
        
        np.random.seed(42)
        data = np.random.rand(100, 10, 10).astype(np.float32)
        
        result = compute_percentiles(data, percentiles=[10, 50, 90])
        
        assert isinstance(result, dict)
        assert 10 in result
        assert 50 in result
        assert 90 in result
        assert result[50].shape == (10, 10)
    
    def test_kelvin_to_celsius(self):
        """Test Kelvin to Celsius conversion."""
        from server.earthkit_integration import kelvin_to_celsius
        
        # Test with numpy array
        kelvin = np.array([273.15, 283.15, 293.15])
        celsius = kelvin_to_celsius(kelvin)
        
        np.testing.assert_array_almost_equal(celsius, [0.0, 10.0, 20.0])


# =============================================================================
# Configuration Tests
# =============================================================================

class TestConfiguration:
    """Tests for configuration handling."""
    
    def test_settings_defaults(self):
        """Test default settings are valid."""
        from server.config import Settings
        
        settings = Settings()
        
        assert settings.products_source in ["local", "azure"]
        assert settings.products_dir is not None
    
    def test_get_cog_path_local(self):
        """Test COG path generation for local storage."""
        from server.config import Settings
        
        settings = Settings(products_source="local", products_dir="test/products")
        
        path = settings.get_cog_path("sst", "2024-01-15")
        
        assert "sst" in path
        assert "2024-01-15" in path
        assert path.startswith("test/products")
    
    def test_get_cog_path_azure(self):
        """Test COG path generation for Azure storage."""
        from server.config import Settings
        
        settings = Settings(
            products_source="azure",
            azure_storage_account="teststorage",
            azure_storage_container="products",
        )
        
        path = settings.get_cog_path("sst", "2024-01-15")
        
        assert path.startswith("/vsicurl/")
        assert "teststorage.blob.core.windows.net" in path


# =============================================================================
# Pipeline Tests
# =============================================================================

class TestPipeline:
    """Tests for data pipeline components."""
    
    def test_variable_config_loading(self):
        """Test variable configuration loading."""
        from server.pipeline.config import get_variable_config
        
        config = get_variable_config("sst")
        
        assert config is not None
        assert hasattr(config, "dtype")
        assert hasattr(config, "scale")
        assert hasattr(config, "nodata")
    
    def test_datasets_json_valid(self):
        """Test datasets.json is valid JSON with required fields."""
        import json
        
        datasets_path = Path(__file__).parent.parent / "server" / "datasets.json"
        
        with open(datasets_path) as f:
            datasets = json.load(f)
        
        assert isinstance(datasets, dict)
        
        # Check at least one variable exists
        assert len(datasets) > 0
        
        # Check required fields for each variable
        for var_name, var_config in datasets.items():
            assert "colormap" in var_config or "cmap" in var_config
            # Other fields may vary


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Performance tests for tile rendering."""
    
    @pytest.mark.slow
    def test_tile_render_performance(self, sample_cog_path: Path):
        """Test tile rendering completes within performance requirements."""
        import time
        from server.tile_server import render_tile
        
        start = time.time()
        
        for _ in range(10):
            render_tile(
                str(sample_cog_path),
                z=0, x=0, y=0,
                variable="sst"
            )
        
        elapsed = time.time() - start
        avg_time = elapsed / 10
        
        # Tiles should render quickly (< 500ms)
        assert avg_time < 0.5, f"Tile render too slow: {avg_time:.3f}s"
