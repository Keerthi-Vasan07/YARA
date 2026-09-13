"""
Product Generation Integration Tests

Tests the data processing pipeline:
- NetCDF to COG conversion
- Downloader implementations
- Zarr store building
- Earthkit integration
"""

import pytest
import numpy as np
from pathlib import Path


class TestEarthkitIntegration:
    """Tests for ECMWF earthkit integration layer."""
    
    def test_earthkit_status(self):
        """Test earthkit availability detection."""
        from server.earthkit_integration import get_earthkit_status
        
        status = get_earthkit_status()
        
        assert isinstance(status, dict)
        assert "earthkit-data" in status
        assert "earthkit-regrid" in status
        assert "earthkit-meteo" in status
    
    def test_load_netcdf(self, sample_sst_netcdf: Path):
        """Test loading NetCDF with earthkit integration."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_sst_netcdf)
        
        assert "analysed_sst" in ds.data_vars
        assert "lat" in ds.coords or "latitude" in ds.coords
        assert "lon" in ds.coords or "longitude" in ds.coords
    
    def test_load_netcdf_with_variables_filter(self, sample_sst_netcdf: Path):
        """Test loading specific variables from NetCDF."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_sst_netcdf, variables=["analysed_sst"])
        
        assert "analysed_sst" in ds.data_vars
    
    def test_kelvin_to_celsius(self):
        """Test Kelvin to Celsius conversion."""
        from server.earthkit_integration import kelvin_to_celsius
        
        kelvin = np.array([273.15, 283.15, 293.15])
        celsius = kelvin_to_celsius(kelvin)
        
        expected = np.array([0.0, 10.0, 20.0])
        np.testing.assert_array_almost_equal(celsius, expected)
    
    def test_celsius_to_kelvin(self):
        """Test Celsius to Kelvin conversion."""
        from server.earthkit_integration import celsius_to_kelvin
        
        celsius = np.array([0.0, 10.0, 20.0])
        kelvin = celsius_to_kelvin(celsius)
        
        expected = np.array([273.15, 283.15, 293.15])
        np.testing.assert_array_almost_equal(kelvin, expected)
    
    def test_resample_to_grid(self):
        """Test grid resampling."""
        from server.earthkit_integration import resample_to_grid
        
        # Create sample data
        data = np.random.rand(90, 180).astype(np.float32)
        source_lat = np.linspace(90, -90, 90)
        source_lon = np.linspace(-180, 180, 180)
        
        # Resample to higher resolution
        result = resample_to_grid(data, source_lat, source_lon, (180, 360))
        
        assert result.shape == (180, 360)
        assert not np.all(np.isnan(result))
    
    def test_resample_preserves_nan(self):
        """Test that resampling preserves NaN regions."""
        from server.earthkit_integration import resample_to_grid
        
        data = np.random.rand(90, 180).astype(np.float32)
        data[:20, :] = np.nan  # NaN in northern region
        
        source_lat = np.linspace(90, -90, 90)
        source_lon = np.linspace(-180, 180, 180)
        
        result = resample_to_grid(data, source_lat, source_lon, (180, 360))
        
        # Northern region should still have NaN
        assert np.any(np.isnan(result[:40, :]))
    
    def test_resample_rgb_to_grid(self):
        """Test RGB resampling for RRS data."""
        from server.earthkit_integration import resample_rgb_to_grid
        
        rgb_data = np.random.rand(3, 90, 180).astype(np.float32)
        source_lat = np.linspace(90, -90, 90)
        source_lon = np.linspace(-180, 180, 180)
        
        result = resample_rgb_to_grid(rgb_data, source_lat, source_lon, (180, 360))
        
        assert result.shape == (3, 180, 360)
    
    def test_compute_climatology(self):
        """Test climatology computation."""
        from server.earthkit_integration import compute_climatology
        
        # Create sample time series
        data = np.random.rand(30, 10, 20).astype(np.float32)
        data[:, :2, :] = np.nan  # Some NaN values
        
        mean, std = compute_climatology(data)
        
        assert mean.shape == (10, 20)
        assert std.shape == (10, 20)
        assert not np.all(np.isnan(mean))
    
    def test_compute_anomaly(self):
        """Test anomaly computation."""
        from server.earthkit_integration import compute_anomaly
        
        data = np.array([10.0, 15.0, 20.0, 25.0, 30.0])
        climatology = np.array(20.0)
        
        anomaly = compute_anomaly(data, climatology)
        
        expected = np.array([-10.0, -5.0, 0.0, 5.0, 10.0])
        np.testing.assert_array_almost_equal(anomaly, expected)
    
    def test_compute_anomaly_standardized(self):
        """Test standardized anomaly computation."""
        from server.earthkit_integration import compute_anomaly
        
        data = np.array([10.0, 15.0, 20.0, 25.0, 30.0])
        climatology = np.array(20.0)
        climatology_std = np.array(5.0)
        
        anomaly = compute_anomaly(data, climatology, standardize=True, climatology_std=climatology_std)
        
        expected = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        np.testing.assert_array_almost_equal(anomaly, expected)
    
    def test_compute_percentiles(self):
        """Test percentile computation."""
        from server.earthkit_integration import compute_percentiles
        
        # Create sample data
        data = np.random.rand(100, 10, 20).astype(np.float32)
        
        result = compute_percentiles(data, percentiles=[10, 50, 90])
        
        assert 10 in result
        assert 50 in result
        assert 90 in result
        assert result[10].shape == (10, 20)
    
    def test_compute_linear_trend(self):
        """Test linear trend computation."""
        from server.earthkit_integration import compute_linear_trend
        
        # Create data with known trend
        n_times, nlat, nlon = 30, 10, 20
        time_values = np.arange(n_times, dtype=np.float64)
        
        # Create data with linear trend of 0.1 per timestep
        base = np.ones((nlat, nlon)) * 20.0
        trend_rate = 0.1
        data = np.zeros((n_times, nlat, nlon))
        for t in range(n_times):
            data[t] = base + t * trend_rate
        
        slope, intercept = compute_linear_trend(data)
        
        # Slope should be close to 0.1
        np.testing.assert_array_almost_equal(slope, np.full((nlat, nlon), trend_rate), decimal=5)
    
    def test_compute_monthly_climatology(self):
        """Test monthly climatology computation."""
        from server.earthkit_integration import compute_monthly_climatology
        
        # Create sample data spanning multiple months
        nlat, nlon = 10, 20
        dates = [
            "2024-01-01", "2024-01-15",
            "2024-02-01", "2024-02-15",
            "2024-03-01", "2024-03-15",
        ]
        data = np.random.rand(len(dates), nlat, nlon).astype(np.float32)
        
        monthly_mean, monthly_std = compute_monthly_climatology(data, dates)
        
        assert monthly_mean.shape == (12, nlat, nlon)
        assert monthly_std.shape == (12, nlat, nlon)
        
        # January (month 0) should have non-NaN values
        assert not np.all(np.isnan(monthly_mean[0]))


class TestCOGConversion:
    """Tests for COG file creation and reading."""
    
    def test_cog_has_correct_encoding(self, sample_sst_cog: Path):
        """Test that COG file has correct encoding."""
        import rasterio
        
        with rasterio.open(sample_sst_cog) as ds:
            assert ds.dtypes[0] == 'int16'
            assert ds.nodata == -32768
            assert ds.crs is not None
            assert ds.crs.to_epsg() == 4326
    
    def test_cog_has_overviews(self, sample_sst_cog: Path):
        """Test that COG has pre-built overviews."""
        import rasterio
        
        with rasterio.open(sample_sst_cog) as ds:
            # COG should be tiled
            assert ds.profile.get("tiled", False)
    
    def test_cog_geotransform(self, sample_sst_cog: Path):
        """Test COG has correct geotransform."""
        import rasterio
        
        with rasterio.open(sample_sst_cog) as ds:
            bounds = ds.bounds
            assert bounds.left == -180
            assert bounds.right == 180
            assert bounds.bottom == -90
            assert bounds.top == 90
    
    def test_cog_metadata_tags(self, sample_sst_cog: Path):
        """Test COG has required metadata tags."""
        import rasterio
        
        with rasterio.open(sample_sst_cog) as ds:
            tags = ds.tags()
            assert "variable" in tags
            assert tags["variable"] == "sst"


class TestTileServer:
    """Tests for tile rendering functionality."""
    
    def test_render_tile_basic(self, sample_sst_cog: Path):
        """Test basic tile rendering."""
        from server.tile_server import render_tile
        
        result = render_tile(
            str(sample_sst_cog),
            z=0, x=0, y=0,
            variable="sst",
            vmin=-2, vmax=35
        )
        
        if result is not None:
            assert isinstance(result, bytes)
            # Check PNG magic bytes
            assert result[:4] == b'\x89PNG'
    
    def test_render_tile_with_variable(self, sample_sst_cog: Path):
        """Test tile rendering with specific variable (uses variable's colormap)."""
        from server.tile_server import render_tile
        
        result = render_tile(
            str(sample_sst_cog),
            z=0, x=0, y=0,
            variable="sst"
        )
        
        if result is not None:
            assert isinstance(result, bytes)
    
    def test_render_tile_custom_scale(self, sample_sst_cog: Path):
        """Test tile rendering with custom scale range."""
        from server.tile_server import render_tile
        
        result = render_tile(
            str(sample_sst_cog),
            z=0, x=0, y=0,
            variable="sst",
            vmin=10, vmax=30
        )
        
        if result is not None:
            assert isinstance(result, bytes)


class TestZarrBuilder:
    """Tests for Zarr store building."""
    
    def test_zarr_store_structure(self, sample_zarr_store: Path):
        """Test Zarr store has correct structure."""
        import zarr
        
        root = zarr.open_group(str(sample_zarr_store), mode='r')
        
        # Required coordinate arrays
        assert "lat" in root
        assert "lon" in root
        assert "time" in root
        
        # Main data array
        assert "sst" in root
        
        # Pre-computed analytics
        assert "climatology_mean" in root
        assert "climatology_std" in root
    
    def test_zarr_climatology_values(self, sample_zarr_store: Path):
        """Test climatology values are valid."""
        import zarr
        
        root = zarr.open_group(str(sample_zarr_store), mode='r')
        
        clim_mean = root["climatology_mean"][:]
        clim_std = root["climatology_std"][:]
        
        # Should have some valid values
        assert not np.all(np.isnan(clim_mean))
        assert not np.all(np.isnan(clim_std))
        
        # Std should be non-negative
        valid_std = clim_std[~np.isnan(clim_std)]
        assert np.all(valid_std >= 0)
    
    def test_zarr_percentiles(self, sample_zarr_store: Path):
        """Test percentile arrays are valid."""
        import zarr
        
        root = zarr.open_group(str(sample_zarr_store), mode='r')
        
        p10 = root["percentile_10"][:]
        p50 = root["percentile_50"][:]
        p90 = root["percentile_90"][:]
        
        # P10 <= P50 <= P90 where valid
        valid = ~(np.isnan(p10) | np.isnan(p50) | np.isnan(p90))
        
        if np.any(valid):
            assert np.all(p10[valid] <= p50[valid])
            assert np.all(p50[valid] <= p90[valid])
    
    def test_zarr_monthly_climatology(self, sample_zarr_store: Path):
        """Test monthly climatology has 12 months."""
        import zarr
        
        root = zarr.open_group(str(sample_zarr_store), mode='r')
        
        monthly_mean = root["climatology_monthly_mean"][:]
        
        assert monthly_mean.shape[0] == 12  # 12 months
    
    def test_zarr_metadata(self, sample_zarr_store: Path):
        """Test Zarr store has required metadata."""
        import zarr
        
        root = zarr.open_group(str(sample_zarr_store), mode='r')
        
        attrs = dict(root.attrs)
        
        assert "dates" in attrs
        assert "title" in attrs or "global_stats" in attrs
    
    def test_zarr_coordinate_ranges(self, sample_zarr_store: Path):
        """Test coordinate arrays cover expected ranges."""
        import zarr
        
        root = zarr.open_group(str(sample_zarr_store), mode='r')
        
        lat = root["lat"][:]
        lon = root["lon"][:]
        
        # Global coverage
        assert lat.min() >= -90
        assert lat.max() <= 90
        assert lon.min() >= -180
        assert lon.max() <= 180


class TestDownloaders:
    """Tests for variable-specific downloaders."""
    
    @pytest.mark.integration
    def test_sst_downloader_conversion(self, sample_sst_netcdf: Path, tmp_path: Path):
        """Test SST downloader conversion from NetCDF to COG."""
        pytest.importorskip("prefect")  # Skip if prefect not installed
        from server.pipeline.downloaders.sst import SSTDownloader
        from server.pipeline.config import get_variable_config
        
        config = get_variable_config("sst")
        downloader = SSTDownloader(config, output_dir=tmp_path / "products")
        
        cog_path = tmp_path / "products" / "sst" / "2024-01-15.tif"
        
        # Call the convert method directly
        stats = downloader._convert(sample_sst_netcdf, cog_path, "2024-01-15")
        
        # Should succeed or return None (if missing data)
        if stats is not None:
            assert cog_path.exists()
            assert "min" in stats or "mean" in stats
    
    def test_variable_config_exists(self):
        """Test all expected variables have configs."""
        pytest.importorskip("prefect")  # Skip if prefect not installed
        from server.pipeline.config import get_variable_config
        
        for var in ["sst", "sic", "sla", "chl", "kd490"]:
            config = get_variable_config(var)
            assert config is not None, f"Missing config for {var}"
            assert hasattr(config, "dtype")
            assert hasattr(config, "scale")


class TestAllECVDownloaders:
    """Comprehensive tests for all 6 ECV downloaders."""
    
    def test_sst_cog_encoding(self, sample_sst_cog: Path):
        """Test SST COG has correct int16 encoding."""
        import rasterio
        
        with rasterio.open(sample_sst_cog) as ds:
            assert ds.dtypes[0] == "int16"
            assert ds.nodata == -32768
            data = ds.read(1)
            # Valid SST range after encoding: -200 to 3500 (for -2 to 35°C)
            valid = data[data != -32768]
            assert valid.min() >= -500
            assert valid.max() <= 4000
    
    def test_sic_cog_encoding(self, sample_sic_cog: Path):
        """Test SIC COG has correct uint8 encoding."""
        import rasterio
        
        with rasterio.open(sample_sic_cog) as ds:
            assert ds.dtypes[0] == "uint8"
            assert ds.nodata == 255
            data = ds.read(1)
            # Valid SIC range: 0-100%
            valid = data[data != 255]
            assert valid.min() >= 0
            assert valid.max() <= 100
    
    def test_sla_cog_encoding(self, sample_sla_cog: Path):
        """Test SLA COG has correct int16 encoding."""
        import rasterio
        
        with rasterio.open(sample_sla_cog) as ds:
            assert ds.dtypes[0] == "int16"
            assert ds.nodata == -32768
    
    def test_chl_cog_encoding(self, sample_chl_cog: Path):
        """Test CHL COG has correct float32 encoding."""
        import rasterio
        
        with rasterio.open(sample_chl_cog) as ds:
            assert ds.dtypes[0] == "float32"
            data = ds.read(1)
            # CHL should have positive values only (where not NaN)
            valid = data[~np.isnan(data)]
            assert valid.min() > 0
    
    def test_kd490_cog_encoding(self, sample_kd490_cog: Path):
        """Test KD490 COG has correct float32 encoding."""
        import rasterio
        
        with rasterio.open(sample_kd490_cog) as ds:
            assert ds.dtypes[0] == "float32"
            data = ds.read(1)
            # KD490 typical range: 0.01-0.5 m^-1
            valid = data[~np.isnan(data)]
            assert valid.min() >= 0
            assert valid.max() <= 1.0
    
    def test_rrs_cog_is_rgba(self, sample_rrs_cog: Path):
        """Test RRS COG is RGBA format."""
        import rasterio
        
        with rasterio.open(sample_rrs_cog) as ds:
            assert ds.count == 4  # RGBA
            assert ds.dtypes[0] == "uint8"
            # Alpha band should have transparency for land
            alpha = ds.read(4)
            assert 0 in alpha  # Has transparent pixels
            assert 255 in alpha  # Has opaque pixels
    
    def test_all_cogs_have_crs(self, all_ecv_cogs: dict):
        """Test all ECVs have correct CRS (EPSG:4326)."""
        import rasterio
        
        for var, cog_path in all_ecv_cogs.items():
            with rasterio.open(cog_path) as ds:
                assert ds.crs is not None, f"{var} missing CRS"
                assert ds.crs.to_epsg() == 4326, f"{var} wrong CRS: {ds.crs}"
    
    def test_all_cogs_have_valid_bounds(self, all_ecv_cogs: dict):
        """Test all ECVs have valid global bounds."""
        import rasterio
        
        for var, cog_path in all_ecv_cogs.items():
            with rasterio.open(cog_path) as ds:
                bounds = ds.bounds
                assert bounds.left >= -180, f"{var} invalid west bound"
                assert bounds.right <= 180, f"{var} invalid east bound"
                assert bounds.bottom >= -90, f"{var} invalid south bound"
                assert bounds.top <= 90, f"{var} invalid north bound"
    
    def test_render_tile_for_each_ecv(self, all_ecv_cogs: dict):
        """Test tile rendering works for all ECVs."""
        from server.tile_server import render_tile
        
        for var, cog_path in all_ecv_cogs.items():
            if var == "rrs":
                # RRS uses RGB passthrough, different handling
                continue
            
            result = render_tile(
                str(cog_path),
                z=0, x=0, y=0,
                variable=var,
            )
            
            assert result is None or isinstance(result, bytes), f"Tile render failed for {var}"
            if result:
                assert result[:4] == b'\x89PNG', f"Invalid PNG for {var}"


class TestECVNetCDFLoading:
    """Tests for loading raw NetCDF files with earthkit."""
    
    def test_load_sst_netcdf(self, sample_sst_netcdf: Path):
        """Test loading SST NetCDF and reading data."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_sst_netcdf)
        
        assert "analysed_sst" in ds.data_vars
        assert ds["analysed_sst"].dims == ("time", "lat", "lon")
        # SST should be in Kelvin (> 200K)
        assert float(ds["analysed_sst"].mean()) > 200
    
    def test_load_sla_netcdf(self, sample_sla_netcdf: Path):
        """Test loading SLA NetCDF."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_sla_netcdf)
        
        assert "sla" in ds.data_vars
        # SLA should be in reasonable range (-0.5 to +0.5m)
        valid_data = ds["sla"].values[~np.isnan(ds["sla"].values)]
        assert valid_data.min() > -1.0
        assert valid_data.max() < 1.0
    
    def test_load_chl_netcdf(self, sample_chl_netcdf: Path):
        """Test loading CHL NetCDF."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_chl_netcdf)
        
        assert "CHL" in ds.data_vars
        # CHL should be positive
        valid_data = ds["CHL"].values[~np.isnan(ds["CHL"].values)]
        assert valid_data.min() > 0
    
    def test_load_kd490_netcdf(self, sample_kd490_netcdf: Path):
        """Test loading KD490 NetCDF."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_kd490_netcdf)
        
        assert "KD490" in ds.data_vars
    
    def test_load_sic_netcdf(self, sample_sic_netcdf: Path):
        """Test loading SIC NetCDF."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_sic_netcdf)
        
        assert "ice_conc" in ds.data_vars
        # SIC as fraction should be 0-1
        valid_data = ds["ice_conc"].values[~np.isnan(ds["ice_conc"].values)]
        assert valid_data.min() >= 0
        assert valid_data.max() <= 1.0
    
    def test_load_rrs_netcdf(self, sample_rrs_netcdf: Path):
        """Test loading RRS NetCDF with multiple bands."""
        from server.earthkit_integration import load_netcdf
        
        ds = load_netcdf(sample_rrs_netcdf)
        
        # Should have all 3 RRS bands
        assert "RRS443" in ds.data_vars
        assert "RRS555" in ds.data_vars
        assert "RRS670" in ds.data_vars
    
    def test_kelvin_to_celsius_conversion(self, sample_sst_netcdf: Path):
        """Test Kelvin to Celsius conversion for SST."""
        from server.earthkit_integration import load_netcdf, kelvin_to_celsius
        
        ds = load_netcdf(sample_sst_netcdf)
        sst_kelvin = ds["analysed_sst"]
        
        sst_celsius = kelvin_to_celsius(sst_kelvin)
        
        # Should now be in Celsius range (-2 to 35)
        valid = sst_celsius.values[~np.isnan(sst_celsius.values)]
        assert valid.min() > -5
        assert valid.max() < 40


class TestDatasetConfig:
    """Tests for datasets.json configuration."""
    
    def test_datasets_json_valid(self):
        """Test datasets.json is valid JSON."""
        import json
        
        datasets_path = Path(__file__).parent.parent / "server" / "datasets.json"
        
        with open(datasets_path, encoding="utf-8") as f:
            datasets = json.load(f)
        
        assert isinstance(datasets, dict)
        assert len(datasets) > 0
    
    def test_datasets_have_colormap(self):
        """Test each dataset has colormap config."""
        import json
        
        datasets_path = Path(__file__).parent.parent / "server" / "datasets.json"
        
        with open(datasets_path, encoding="utf-8") as f:
            datasets = json.load(f)
        
        for var_name, var_config in datasets.items():
            assert "colormap" in var_config or "cmap" in var_config, f"Missing colormap for {var_name}"
    
    def test_datasets_have_ranges(self):
        """Test each dataset has value range config."""
        import json
        
        datasets_path = Path(__file__).parent.parent / "server" / "datasets.json"
        
        with open(datasets_path, encoding="utf-8") as f:
            datasets = json.load(f)
        
        for var_name, var_config in datasets.items():
            # Should have either vmin/vmax or range
            has_range = ("vmin" in var_config and "vmax" in var_config) or "range" in var_config
            assert has_range, f"Missing value range for {var_name}"
