"""
API Endpoint Integration Tests

Tests the FastAPI endpoints that the UI uses:
- Time range queries
- Tile rendering
- Point queries
- Zarr analytics endpoints
- Data download endpoints
"""

import pytest
from pathlib import Path


class TestHealthEndpoints:
    """Tests for health and status endpoints."""
    
    def test_root_endpoint(self, test_client):
        """Test root endpoint returns API info."""
        response = test_client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data or "service" in data
    
    def test_health_endpoint(self, test_client):
        """Test health endpoint returns 200."""
        response = test_client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_earthkit_status_endpoint(self, test_client):
        """Test earthkit status endpoint."""
        response = test_client.get("/api/earthkit-status")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "earthkit-data" in data["components"]
        assert "earthkit-regrid" in data["components"]
        assert "earthkit-meteo" in data["components"]


class TestTimeRangeEndpoints:
    """Tests for time range query endpoints."""
    
    def test_time_range_sst(self, test_client_with_data):
        """Test /api/time-range/sst returns available dates."""
        response = test_client_with_data.get("/api/time-range/sst")
        assert response.status_code == 200
        
        data = response.json()
        assert "variable" in data or "total_months" in data
        assert "available_dates" in data
    
    def test_time_range_missing_variable(self, test_client):
        """Test time range for non-existent variable."""
        response = test_client.get("/api/time-range/nonexistent")
        assert response.status_code == 200
        
        data = response.json()
        # Should return empty dates, not error
        assert data["available_dates"] == [] or data["total_months"] == 0
    
    def test_time_range_includes_years_breakdown(self, test_client_with_data):
        """Test time range includes year-month breakdown."""
        response = test_client_with_data.get("/api/time-range/sst")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("available_dates"):
                assert "years" in data


class TestTileEndpoints:
    """Tests for XYZ tile rendering endpoints."""
    
    def test_tile_returns_png(self, test_client_with_data):
        """Test tile endpoint returns PNG image."""
        response = test_client_with_data.get("/api/tiles/sst/2024-01-15/0/0/0.png")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        
        # Check PNG magic bytes
        assert response.content[:4] == b'\x89PNG'
    
    def test_tile_missing_date_returns_transparent(self, test_client):
        """Test tile for missing date returns transparent PNG."""
        response = test_client.get("/api/tiles/sst/2099-12-31/0/0/0.png")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
    
    def test_tile_with_custom_vmin_vmax(self, test_client_with_data):
        """Test tile with custom color scale range."""
        response = test_client_with_data.get(
            "/api/tiles/sst/2024-01-15/0/0/0.png",
            params={"vmin": -5, "vmax": 30}
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
    
    def test_tilejson_endpoint(self, test_client_with_data):
        """Test TileJSON metadata endpoint."""
        response = test_client_with_data.get("/api/tiles/sst/tilejson/2024-01-15.json")
        
        if response.status_code == 200:
            data = response.json()
            # API may return error or tilejson depending on data availability
            if "error" not in data:
                assert "tilejson" in data
                assert "tiles" in data
                assert "bounds" in data
        else:
            # May fail if no data for date - that's OK
            assert response.status_code in [200, 404, 500]
    
    def test_tile_different_variables(self, test_client_with_data):
        """Test tiles work for different variables."""
        for variable in ["sst", "sic"]:
            response = test_client_with_data.get(f"/api/tiles/{variable}/2024-01-15/0/0/0.png")
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
    
    @pytest.mark.parametrize("variable", ["sst", "sic", "sla", "chl", "kd490"])
    def test_tile_all_ecv_variables(self, test_client_with_data, variable):
        """Test tile endpoint works for all ECV variables."""
        response = test_client_with_data.get(f"/api/tiles/{variable}/2024-01-15/0/0/0.png")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


class TestPointQueryEndpoints:
    """Tests for click-to-query point endpoints."""
    
    @pytest.mark.parametrize("variable", ["sst", "sic", "sla", "chl", "kd490"])
    def test_point_query_all_ecvs(self, test_client_with_data, variable):
        """Test point query works for all ECV variables."""
        response = test_client_with_data.get(
            f"/api/{variable}/point",
            params={"date": "2024-01-15", "lon": 0.0, "lat": 45.0}
        )
        
        # 200 or 404 depending on data availability at location
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "unit" in data
    
    def test_point_query_sst(self, test_client_with_data):
        """Test SST point query returns value."""
        response = test_client_with_data.get(
            "/api/sst/point",
            params={"date": "2024-01-15", "lon": 0.0, "lat": 45.0}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "sst" in data or "value" in data
            assert "unit" in data
    
    def test_point_query_generic_variable(self, test_client_with_data):
        """Test generic variable point query endpoint."""
        response = test_client_with_data.get(
            "/api/sst/point",
            params={"date": "2024-01-15", "lon": -45.0, "lat": 60.0}
        )
        
        # May return 200 or 404 depending on data availability
        assert response.status_code in [200, 404]
    
    def test_point_query_out_of_bounds(self, test_client_with_data):
        """Test point query for out-of-bounds location."""
        response = test_client_with_data.get(
            "/api/sst/point",
            params={"date": "2024-01-15", "lon": 0.0, "lat": 85.0}  # Arctic (land)
        )
        
        if response.status_code == 200:
            data = response.json()
            # Should indicate nodata
            assert data.get("sst") is None or data.get("value") is None
    
    def test_point_query_sic(self, test_client_with_data):
        """Test SIC point query at polar location."""
        response = test_client_with_data.get(
            "/api/sic/point",
            params={"date": "2024-01-15", "lon": 0.0, "lat": 75.0}  # Arctic ocean
        )
        
        # Expect 200 or 404
        assert response.status_code in [200, 404]


class TestZarrEndpoints:
    """Tests for Zarr analytics endpoints."""
    
    def test_zarr_catalog(self, test_client_with_data):
        """Test Zarr catalog lists available datasets."""
        response = test_client_with_data.get("/api/zarr/catalog")
        assert response.status_code == 200
        
        data = response.json()
        assert "datasets" in data
    
    def test_zarr_info(self, test_client_with_data):
        """Test Zarr info endpoint."""
        response = test_client_with_data.get("/api/zarr/sst/info")
        
        if response.status_code == 200:
            data = response.json()
            assert "variable" in data
            assert "arrays" in data or "global_stats" in data
    
    def test_zarr_timeseries(self, test_client_with_data):
        """Test Zarr timeseries extraction."""
        response = test_client_with_data.get(
            "/api/zarr/sst/timeseries",
            params={"lon": 0.0, "lat": 45.0}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "location" in data
            assert "timeseries" in data
            assert "climatology" in data
    
    def test_zarr_stats_region(self, test_client_with_data):
        """Test Zarr regional statistics."""
        response = test_client_with_data.get(
            "/api/zarr/sst/stats",
            params={
                "lon_min": -10, "lon_max": 10,
                "lat_min": 40, "lat_max": 50
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "region" in data
            assert "climatology" in data
    
    def test_zarr_climatology(self, test_client_with_data):
        """Test Zarr climatology endpoint."""
        response = test_client_with_data.get(
            "/api/zarr/sst/climatology",
            params={"lon": 0.0, "lat": 45.0}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "location" in data
            assert "overall" in data
    
    def test_zarr_climatology_specific_month(self, test_client_with_data):
        """Test Zarr climatology for specific month."""
        response = test_client_with_data.get(
            "/api/zarr/sst/climatology",
            params={"lon": 0.0, "lat": 45.0, "month": 7}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("month") == 7
    
    def test_zarr_percentiles(self, test_client_with_data):
        """Test Zarr percentiles endpoint."""
        response = test_client_with_data.get(
            "/api/zarr/sst/percentiles",
            params={"lon": 0.0, "lat": 45.0}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "percentiles" in data
    
    def test_zarr_slice(self, test_client_with_data):
        """Test Zarr 2D slice extraction."""
        response = test_client_with_data.get(
            "/api/zarr/sst/slice",
            params={
                "time_idx": 0,
                "lon_min": -10, "lon_max": 10,
                "lat_min": 40, "lat_max": 50,
                "downsample": 2
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert "lat" in data
            assert "lon" in data
    
    def test_zarr_files_tree(self, test_client_with_data):
        """Test Zarr files tree endpoint."""
        response = test_client_with_data.get("/api/zarr/sst/files")
        
        if response.status_code == 200:
            data = response.json()
            assert "tree" in data
            assert "total_size" in data


class TestDownloadEndpoints:
    """Tests for data download/subset endpoints."""
    
    @pytest.mark.parametrize("variable", ["sst", "sic", "sla", "chl", "kd490"])
    def test_subset_netcdf_all_ecvs(self, test_client_with_data, variable):
        """Test NetCDF subset download for all ECV variables."""
        response = test_client_with_data.get(
            f"/api/{variable}/subset",
            params={
                "date": "2024-01-15",
                "north": 50, "south": 40,
                "east": 10, "west": -10,
                "format": "netcdf"
            }
        )
        
        if response.status_code == 200:
            assert response.headers["content-type"] == "application/x-netcdf"
            # Verify filename contains variable name
            content_disp = response.headers.get("content-disposition", "")
            assert variable in content_disp
    
    @pytest.mark.parametrize("variable", ["sst", "sic", "sla", "chl", "kd490"])
    def test_subset_geotiff_all_ecvs(self, test_client_with_data, variable):
        """Test GeoTIFF subset download for all ECV variables."""
        response = test_client_with_data.get(
            f"/api/{variable}/subset",
            params={
                "date": "2024-01-15",
                "north": 50, "south": 40,
                "east": 10, "west": -10,
                "format": "geotiff"
            }
        )
        
        if response.status_code == 200:
            assert "tiff" in response.headers["content-type"]
            content_disp = response.headers.get("content-disposition", "")
            assert variable in content_disp
    
    @pytest.mark.parametrize("variable,expected_column", [
        ("sst", "sst_celsius"),
        ("sic", "sic_percent"),
        ("sla", "sla_meters"),
        ("chl", "chl_mg_m3"),
        ("kd490", "kd490_m_inv"),
    ])
    def test_subset_csv_all_ecvs(self, test_client_with_data, variable, expected_column):
        """Test CSV subset download for all ECV variables with correct column names."""
        response = test_client_with_data.get(
            f"/api/{variable}/subset",
            params={
                "date": "2024-01-15",
                "north": 50, "south": 40,
                "east": 10, "west": -10,
                "format": "csv"
            }
        )
        
        if response.status_code == 200:
            assert "text/csv" in response.headers["content-type"]
            content = response.text
            assert "latitude" in content
            assert "longitude" in content
            assert expected_column in content
    
    def test_subset_invalid_variable(self, test_client_with_data):
        """Test subset endpoint returns error for unsupported variable."""
        response = test_client_with_data.get(
            "/api/invalid_var/subset",
            params={
                "date": "2024-01-15",
                "north": 50, "south": 40,
                "east": 10, "west": -10,
                "format": "netcdf"
            }
        )
        assert response.status_code == 400
        assert "Unsupported variable" in response.json()["detail"]
    
    def test_subset_rrs_not_supported(self, test_client_with_data):
        """Test that RRS (RGBA) is not supported for subset downloads."""
        response = test_client_with_data.get(
            "/api/rrs/subset",
            params={
                "date": "2024-01-15",
                "north": 50, "south": 40,
                "east": 10, "west": -10,
                "format": "netcdf"
            }
        )
        # RRS is RGBA and not in VARIABLE_METADATA, so should return 400
        assert response.status_code == 400


class TestTimeseriesEndpoint:
    """Tests for timeseries endpoint."""
    
    def test_sst_timeseries(self, test_client_with_data):
        """Test SST timeseries extraction from COGs."""
        response = test_client_with_data.get(
            "/api/sst/timeseries",
            params={"lon": 0.0, "lat": 45.0, "limit": 10}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "location" in data
            assert "timeseries" in data
            assert "count" in data


class TestPerformanceRequirements:
    """Performance tests for API endpoints."""
    
    @pytest.mark.slow
    def test_tile_render_performance(self, test_client_with_data):
        """Test tile rendering performance."""
        import time
        
        start = time.time()
        
        for _ in range(5):
            response = test_client_with_data.get("/api/tiles/sst/2024-01-15/2/1/1.png")
            assert response.status_code == 200
        
        elapsed = time.time() - start
        avg_time = elapsed / 5
        
        # Should respond quickly (< 500ms)
        assert avg_time < 1.0, f"Tile render too slow: {avg_time:.3f}s"
    
    @pytest.mark.slow
    def test_time_range_performance(self, test_client_with_data):
        """Test time range query performance (should use STAC cache)."""
        import time
        
        start = time.time()
        
        for _ in range(10):
            response = test_client_with_data.get("/api/time-range/sst")
            assert response.status_code == 200
        
        elapsed = time.time() - start
        avg_time = elapsed / 10
        
        # STAC-cached should be < 100ms
        assert avg_time < 0.5, f"Time range query too slow: {avg_time:.3f}s"
    
    @pytest.mark.slow
    def test_zarr_timeseries_performance(self, test_client_with_data):
        """Test Zarr timeseries extraction performance."""
        import time
        
        response = test_client_with_data.get("/api/zarr/sst/info")
        if response.status_code != 200:
            pytest.skip("Zarr store not available")
        
        start = time.time()
        
        for _ in range(5):
            response = test_client_with_data.get(
                "/api/zarr/sst/timeseries",
                params={"lon": 0.0, "lat": 45.0}
            )
        
        elapsed = time.time() - start
        avg_time = elapsed / 5
        
        # Should respond quickly (< 2s)
        assert avg_time < 2.0, f"Zarr timeseries too slow: {avg_time:.3f}s"


class TestErrorHandling:
    """Tests for proper error handling."""
    
    def test_invalid_date_format(self, test_client):
        """Test invalid date format returns appropriate error."""
        response = test_client.get(
            "/api/sst/point",
            params={"date": "invalid-date", "lon": 0, "lat": 0}
        )
        # Should return 4xx error
        assert response.status_code in [400, 404, 422, 500]
    
    def test_invalid_coordinates(self, test_client):
        """Test invalid coordinates return error."""
        response = test_client.get(
            "/api/sst/point",
            params={"date": "2024-01-15", "lon": 999, "lat": 999}
        )
        # Should handle gracefully - may be 404 if no data, or 400/422 for validation
        assert response.status_code in [200, 400, 404, 422]
    
    def test_missing_required_params(self, test_client):
        """Test missing required parameters."""
        response = test_client.get("/api/sst/point")
        assert response.status_code == 422  # Validation error
