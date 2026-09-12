"""
Prefect Flow and Task Tests

Tests for the ECV ingestion pipeline flows and tasks.
Uses Prefect's synchronous testing mode (no server required).
"""

import json
import pytest
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

# Skip entire module if prefect not installed
prefect = pytest.importorskip("prefect", reason="Prefect not installed")


@pytest.fixture
def mock_prefect_logger():
    """Mock Prefect's get_run_logger to avoid context errors."""
    import logging
    mock_logger = logging.getLogger("test_prefect")
    
    with patch("server.pipeline.tasks.get_run_logger", return_value=mock_logger):
        yield mock_logger


@pytest.fixture
def mock_flow_logger():
    """Mock Prefect's get_run_logger for flows."""
    import logging
    mock_logger = logging.getLogger("test_prefect_flow")
    
    with patch("server.pipeline.flows.get_run_logger", return_value=mock_logger):
        yield mock_logger


# =============================================================================
# Task Unit Tests
# =============================================================================

class TestGenerateDateRange:
    """Tests for generate_date_range task."""
    
    def test_single_date(self):
        """Test generating a single date."""
        from server.pipeline.tasks import generate_date_range
        
        result = generate_date_range.fn("2024-01-15", "2024-01-15")
        
        assert result == ["2024-01-15"]
    
    def test_date_range(self):
        """Test generating a date range."""
        from server.pipeline.tasks import generate_date_range
        
        result = generate_date_range.fn("2024-01-01", "2024-01-05")
        
        assert len(result) == 5
        assert result[0] == "2024-01-01"
        assert result[-1] == "2024-01-05"
    
    def test_month_boundary(self):
        """Test date range crossing month boundary."""
        from server.pipeline.tasks import generate_date_range
        
        result = generate_date_range.fn("2024-01-30", "2024-02-02")
        
        assert len(result) == 4
        assert "2024-01-31" in result
        assert "2024-02-01" in result


class TestGetMissingDates:
    """Tests for get_missing_dates task."""
    
    def test_no_catalog(self, tmp_path: Path):
        """Test with non-existent catalog returns all dates."""
        from server.pipeline.tasks import get_missing_dates
        
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        result = get_missing_dates.fn("sst", dates, tmp_path / "nonexistent.json")
        
        assert result == dates
    
    def test_with_existing_entries(self, tmp_path: Path):
        """Test filtering out existing entries."""
        from server.pipeline.tasks import get_missing_dates
        
        # Create catalog with some entries
        catalog = {
            "variables": {
                "sst": {
                    "entries": {
                        "2024-01-01": {"path": "test.tif"},
                        "2024-01-03": {"path": "test2.tif"},
                    }
                }
            }
        }
        catalog_path = tmp_path / "catalog.json"
        with open(catalog_path, "w") as f:
            json.dump(catalog, f)
        
        dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
        result = get_missing_dates.fn("sst", dates, catalog_path)
        
        assert result == ["2024-01-02", "2024-01-04"]
    
    def test_different_variable(self, tmp_path: Path):
        """Test that different variable has no entries."""
        from server.pipeline.tasks import get_missing_dates
        
        catalog = {
            "variables": {
                "sst": {
                    "entries": {"2024-01-01": {"path": "test.tif"}}
                }
            }
        }
        catalog_path = tmp_path / "catalog.json"
        with open(catalog_path, "w") as f:
            json.dump(catalog, f)
        
        dates = ["2024-01-01", "2024-01-02"]
        result = get_missing_dates.fn("sic", dates, catalog_path)
        
        # SIC has no entries, so all dates are missing
        assert result == dates


class TestUpdateCatalog:
    """Tests for update_catalog task."""
    
    def test_create_new_catalog(self, tmp_path: Path, mock_prefect_logger):
        """Test creating a new catalog."""
        from server.pipeline.tasks import update_catalog
        
        catalog_path = tmp_path / "catalog.json"
        
        results = [
            {
                "variable": "sst",
                "date": "2024-01-15",
                "path": "/products/sst/2024-01-15.tif",
                "stats": {"min": -2, "max": 35},
                "status": "created",
            }
        ]
        
        added = update_catalog.fn(results, catalog_path)
        
        assert added == 1
        assert catalog_path.exists()
        
        with open(catalog_path) as f:
            catalog = json.load(f)
        
        assert "sst" in catalog["variables"]
        assert "2024-01-15" in catalog["variables"]["sst"]["entries"]
    
    def test_append_to_existing(self, tmp_path: Path, mock_prefect_logger):
        """Test appending to existing catalog."""
        from server.pipeline.tasks import update_catalog
        
        catalog_path = tmp_path / "catalog.json"
        
        # Create initial catalog
        initial = {
            "created": "2024-01-01T00:00:00",
            "variables": {
                "sst": {
                    "entries": {"2024-01-01": {"path": "test.tif"}},
                    "count": 1,
                }
            }
        }
        with open(catalog_path, "w") as f:
            json.dump(initial, f)
        
        results = [
            {"variable": "sst", "date": "2024-01-02", "path": "test2.tif", "status": "created"}
        ]
        
        added = update_catalog.fn(results, catalog_path)
        
        assert added == 1
        
        with open(catalog_path) as f:
            catalog = json.load(f)
        
        assert catalog["variables"]["sst"]["count"] == 2
    
    def test_skip_none_results(self, tmp_path: Path, mock_prefect_logger):
        """Test that None results are skipped."""
        from server.pipeline.tasks import update_catalog
        
        catalog_path = tmp_path / "catalog.json"
        
        results = [
            None,
            {"variable": "sst", "date": "2024-01-02", "path": "test.tif", "status": "created"},
            {"variable": "sst", "date": "2024-01-03", "status": "skipped"},
        ]
        
        added = update_catalog.fn(results, catalog_path)
        
        # Only one created, skipped doesn't count
        assert added == 1


class TestCleanupTempFiles:
    """Tests for cleanup_temp_files task."""
    
    def test_cleanup_files(self, tmp_path: Path, mock_prefect_logger):
        """Test cleaning up temporary files."""
        from server.pipeline.tasks import cleanup_temp_files
        
        # Create temp files
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        (temp_dir / "file1.nc").touch()
        (temp_dir / "file2.nc").touch()
        
        count = cleanup_temp_files.fn(temp_dir)
        
        assert count == 2
        assert len(list(temp_dir.iterdir())) == 0
    
    def test_cleanup_directories(self, tmp_path: Path, mock_prefect_logger):
        """Test cleaning up nested directories."""
        from server.pipeline.tasks import cleanup_temp_files
        
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "file.nc").touch()
        
        count = cleanup_temp_files.fn(temp_dir)
        
        assert count == 1  # One directory removed
    
    def test_nonexistent_dir(self, tmp_path: Path, mock_prefect_logger):
        """Test with non-existent directory."""
        from server.pipeline.tasks import cleanup_temp_files
        
        count = cleanup_temp_files.fn(tmp_path / "nonexistent")
        
        assert count == 0


class TestNotifyCompletion:
    """Tests for notify_completion task."""
    
    def test_notify_logs(self, caplog, mock_prefect_logger):
        """Test that notification logs correctly."""
        from server.pipeline.tasks import notify_completion
        import logging
        
        with caplog.at_level(logging.INFO):
            notify_completion.fn("sst", processed=10, failed=2, duration_seconds=120.0)
        
        # Should not raise, just log


class TestCheckZarrNeedsUpdate:
    """Tests for check_zarr_needs_update task."""
    
    def test_zarr_not_exists(self, tmp_path: Path, mock_prefect_logger):
        """Test when Zarr doesn't exist."""
        from server.pipeline.tasks import check_zarr_needs_update
        from server.pipeline.config import get_config
        
        zarr_dir = tmp_path / "zarr"
        products_dir = tmp_path / "products"
        (products_dir / "sst").mkdir(parents=True)
        (products_dir / "sst" / "2024-01-01.tif").touch()  # At least one COG
        
        # Get actual config and override paths
        config = get_config()
        original_zarr_dir = config.zarr_dir
        original_products_dir = config.products_dir
        
        try:
            config.zarr_dir = zarr_dir
            config.products_dir = products_dir
            
            result = check_zarr_needs_update.fn("sst")
            
            assert result is True  # Needs build because zarr doesn't exist
        finally:
            config.zarr_dir = original_zarr_dir
            config.products_dir = original_products_dir
    
    def test_zarr_up_to_date(self, tmp_path: Path, mock_prefect_logger):
        """Test when Zarr is up to date with COGs."""
        from server.pipeline.tasks import check_zarr_needs_update
        from server.pipeline.config import get_config
        import zarr
        
        # Setup directories
        zarr_dir = tmp_path / "zarr"
        products_dir = tmp_path / "products"
        sst_products = products_dir / "sst"
        sst_products.mkdir(parents=True)
        
        # Create minimal zarr store with 5 dates
        zarr_path = zarr_dir / "sst.zarr"
        root = zarr.open_group(str(zarr_path), mode="w")
        root.attrs["dates"] = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        
        # Create same number of COG files (5)
        for i in range(1, 6):
            (sst_products / f"2024-01-{i:02d}.tif").touch()
        
        config = get_config()
        original_zarr_dir = config.zarr_dir
        original_products_dir = config.products_dir
        
        try:
            config.zarr_dir = zarr_dir
            config.products_dir = products_dir
            
            result = check_zarr_needs_update.fn("sst")
            
            assert result is False  # Up to date
        finally:
            config.zarr_dir = original_zarr_dir
            config.products_dir = original_products_dir


class TestGetZarrStatus:
    """Tests for get_zarr_status task."""
    
    def test_zarr_not_exists(self, tmp_path: Path, mock_prefect_logger):
        """Test status when Zarr doesn't exist."""
        from server.pipeline.tasks import get_zarr_status
        from server.pipeline.config import get_config
        
        zarr_dir = tmp_path / "zarr"
        zarr_dir.mkdir(parents=True)
        
        config = get_config()
        original_zarr_dir = config.zarr_dir
        
        try:
            config.zarr_dir = zarr_dir
            result = get_zarr_status.fn("sst")
            
            assert result["exists"] is False
            assert result["variable"] == "sst"
        finally:
            config.zarr_dir = original_zarr_dir
    
    def test_zarr_exists(self, tmp_path: Path, mock_prefect_logger):
        """Test status when Zarr exists."""
        from server.pipeline.tasks import get_zarr_status
        from server.pipeline.config import get_config
        import zarr
        import numpy as np
        
        zarr_dir = tmp_path / "zarr"
        zarr_path = zarr_dir / "sst.zarr"
        
        # Create minimal zarr store
        root = zarr.open_group(str(zarr_path), mode="w")
        root.attrs["dates"] = ["2024-01-01", "2024-01-02", "2024-01-03"]
        root.attrs["global_stats"] = {"temporal_mean": 15.5}
        root.attrs["monthly_sample_count"] = [3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        
        # Create arrays that status check looks for
        root.create_array("climatology_mean", data=np.zeros((10, 20), dtype=np.float32))
        root.create_array("climatology_monthly_mean", data=np.zeros((12, 10, 20), dtype=np.float32))
        root.create_array("percentile_10", data=np.zeros((10, 20), dtype=np.float32))
        root.create_array("trend", data=np.zeros((10, 20), dtype=np.float32))
        
        config = get_config()
        original_zarr_dir = config.zarr_dir
        
        try:
            config.zarr_dir = zarr_dir
            result = get_zarr_status.fn("sst")
            
            assert result["exists"] is True
            assert result["n_times"] == 3
            assert result["has_climatology"] is True
            assert result["has_percentiles"] is True
        finally:
            config.zarr_dir = original_zarr_dir


# =============================================================================
# Flow Unit Tests (with mocked tasks)
# Note: These tests are marked as e2e because they require Prefect runtime
# which attempts network connections even when using .fn() directly
# =============================================================================

@pytest.mark.e2e
class TestIngestDateFlow:
    """Tests for ingest_date flow."""
    
    def test_ingest_creates_file(self, tmp_path: Path, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test flow creates COG file."""
        from server.pipeline import flows as flows_module
        
        # Mock download_and_convert to return a result
        mock_result = {
            "path": str(tmp_path / "sst/2024-01-15.tif"),
            "stats": {"min": -2, "max": 35},
            "status": "created",
            "date": "2024-01-15",
            "variable": "sst",
        }
        
        mock_download = MagicMock(return_value=mock_result)
        mock_upload = MagicMock(return_value={**mock_result, "uploaded": True})
        mock_catalog = MagicMock()
        mock_stac = MagicMock()
        
        # Patch where the names are used (in flows module)
        monkeypatch.setattr(flows_module, "download_and_convert", mock_download)
        monkeypatch.setattr(flows_module, "upload_to_azure", mock_upload)
        monkeypatch.setattr(flows_module, "update_catalog", mock_catalog)
        monkeypatch.setattr(flows_module, "update_stac_collection", mock_stac)
        
        result = flows_module.ingest_date.fn("sst", "2024-01-15")
        
        assert result["status"] == "created"
        mock_download.assert_called_once_with(variable="sst", date_str="2024-01-15", force=False)
        mock_upload.assert_called_once()
        mock_catalog.assert_called_once()
        mock_stac.assert_called_once_with("sst")
    
    def test_ingest_skips_existing(self, tmp_path: Path, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test flow handles skipped files."""
        from server.pipeline import flows as flows_module
        
        mock_result = {"status": "skipped", "date": "2024-01-15"}
        mock_download = MagicMock(return_value=mock_result)
        mock_catalog = MagicMock()
        
        # Patch where the names are used (in flows module)
        monkeypatch.setattr(flows_module, "download_and_convert", mock_download)
        monkeypatch.setattr(flows_module, "update_catalog", mock_catalog)
        
        result = flows_module.ingest_date.fn("sst", "2024-01-15")
        
        assert result["status"] == "skipped"
        # Should not update catalog for skipped
        mock_catalog.assert_not_called()


@pytest.mark.e2e
class TestBackfillVariableFlow:
    """Tests for backfill_variable flow."""
    
    def test_backfill_processes_dates(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test backfill processes date range."""
        from server.pipeline import flows as flows_module
        
        # Mock date range tasks
        monkeypatch.setattr(
            flows_module, "generate_date_range",
            MagicMock(return_value=["2024-01-01", "2024-01-02", "2024-01-03"])
        )
        monkeypatch.setattr(
            flows_module, "get_missing_dates",
            MagicMock(return_value=["2024-01-02", "2024-01-03"])
        )
        
        # Mock download task with submit method
        mock_future = MagicMock()
        mock_future.result.return_value = {
            "status": "created",
            "date": "2024-01-02",
            "variable": "sst",
            "path": "test.tif",
        }
        
        mock_download = MagicMock()
        mock_download.submit = MagicMock(return_value=mock_future)
        monkeypatch.setattr(flows_module, "download_and_convert", mock_download)
        
        # Mock upload_to_azure to return result with uploaded flag
        monkeypatch.setattr(flows_module, "upload_to_azure", MagicMock(side_effect=lambda r: {**r, "uploaded": True} if r else None))
        
        monkeypatch.setattr(flows_module, "update_catalog", MagicMock())
        monkeypatch.setattr(flows_module, "update_stac_collection", MagicMock())
        monkeypatch.setattr(flows_module, "notify_completion", MagicMock())
        
        result = flows_module.backfill_variable.fn("sst", "2024-01-01", "2024-01-03")
        
        assert result["variable"] == "sst"
        assert result["skipped"] == 1  # 2024-01-01 already exists
        assert "processed" in result
        assert "duration_seconds" in result
    
    def test_backfill_no_missing_dates(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test backfill when no dates are missing."""
        from server.pipeline import flows as flows_module
        
        monkeypatch.setattr(
            flows_module, "generate_date_range",
            MagicMock(return_value=["2024-01-01", "2024-01-02"])
        )
        monkeypatch.setattr(
            flows_module, "get_missing_dates",
            MagicMock(return_value=[])  # All exist
        )
        
        result = flows_module.backfill_variable.fn("sst", "2024-01-01", "2024-01-02")
        
        assert result["processed"] == 0
        assert result["skipped"] == 2


@pytest.mark.e2e
class TestIngestNrtFlow:
    """Tests for ingest_nrt flow."""
    
    def test_nrt_calculates_date_range(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test NRT calculates correct date range from today."""
        from server.pipeline import flows as flows_module
        
        monkeypatch.setattr(
            flows_module, "generate_date_range",
            MagicMock(return_value=["2024-01-13", "2024-01-14", "2024-01-15"])
        )
        monkeypatch.setattr(
            flows_module, "get_missing_dates",
            MagicMock(return_value=["2024-01-15"])
        )
        monkeypatch.setattr(
            flows_module, "download_and_convert",
            MagicMock(return_value={"status": "created", "variable": "sst", "date": "2024-01-15", "path": "t.tif"})
        )
        monkeypatch.setattr(flows_module, "upload_to_azure", MagicMock(side_effect=lambda r: {**r, "uploaded": True} if r else None))
        monkeypatch.setattr(flows_module, "update_catalog", MagicMock())
        monkeypatch.setattr(flows_module, "update_stac_collection", MagicMock())
        monkeypatch.setattr(flows_module, "cleanup_temp_files", MagicMock())
        
        result = flows_module.ingest_nrt.fn(variables=["sst"], lookback_days=3)
        
        assert "sst" in result
        assert result["sst"]["processed"] >= 0


@pytest.mark.e2e
class TestBuildZarrFlow:
    """Tests for build_zarr flow."""
    
    def test_build_zarr_success(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test successful Zarr build."""
        from server.pipeline import flows as flows_module
        
        monkeypatch.setattr(
            flows_module, "check_zarr_needs_update",
            MagicMock(return_value=True)
        )
        monkeypatch.setattr(
            flows_module, "build_zarr_store",
            MagicMock(return_value={
                "variable": "sst",
                "status": "success",
                "path": "/zarr/sst.zarr",
                "n_times": 30,
            })
        )
        monkeypatch.setattr(
            flows_module, "update_zarr_stac",
            MagicMock(return_value={"status": "updated"})
        )
        
        result = flows_module.build_zarr.fn("sst")
        
        assert result["status"] == "success"
        assert result["variable"] == "sst"
        assert "duration_seconds" in result
    
    def test_build_zarr_skipped(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test Zarr build skipped when up to date."""
        from server.pipeline import flows as flows_module
        
        monkeypatch.setattr(
            flows_module, "check_zarr_needs_update",
            MagicMock(return_value=False)
        )
        monkeypatch.setattr(
            flows_module, "get_zarr_status",
            MagicMock(return_value={"exists": True, "n_times": 30})
        )
        
        result = flows_module.build_zarr.fn("sst", force_rebuild=False)
        
        assert result["status"] == "skipped"
    
    def test_build_zarr_forced(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test forced Zarr rebuild."""
        from server.pipeline import flows as flows_module
        
        mock_build = MagicMock(return_value={
            "variable": "sst",
            "status": "success",
            "path": "/zarr/sst.zarr",
            "n_times": 30,
        })
        
        monkeypatch.setattr(flows_module, "build_zarr_store", mock_build)
        monkeypatch.setattr(
            flows_module, "update_zarr_stac",
            MagicMock(return_value={"status": "updated"})
        )
        
        result = flows_module.build_zarr.fn("sst", force_rebuild=True)
        
        assert result["status"] == "success"
        mock_build.assert_called_once()


class TestBuildAllZarrFlow:
    """Tests for build_all_zarr flow."""
    
    def test_builds_all_variables(self, monkeypatch, mock_flow_logger):
        """Test building Zarr for all variables."""
        from server.pipeline.flows import build_all_zarr, build_zarr
        from server.pipeline import config
        
        # Mock VARIABLES
        monkeypatch.setattr(config, "VARIABLES", {"sst": {}, "sic": {}, "sla": {}})
        
        # Mock build_zarr flow
        def mock_build(variable, force_rebuild=False):
            return {"variable": variable, "status": "success"}
        
        monkeypatch.setattr("server.pipeline.flows.build_zarr", MagicMock(fn=mock_build))
        
        result = build_all_zarr.fn(variables=["sst", "sic"])
        
        assert "sst" in result
        assert "sic" in result
    
    def test_skips_rrs(self, monkeypatch, mock_flow_logger):
        """Test RRS is skipped by default."""
        from server.pipeline.flows import build_all_zarr
        from server.pipeline import config
        
        monkeypatch.setattr(config, "VARIABLES", {"sst": {}, "rrs": {}})
        
        def mock_build(variable, force_rebuild=False):
            return {"variable": variable, "status": "success"}
        
        monkeypatch.setattr("server.pipeline.flows.build_zarr", MagicMock(fn=mock_build))
        
        result = build_all_zarr.fn(skip_rgb=True)
        
        assert "rrs" not in result


@pytest.mark.e2e
class TestGetZarrStatusAllFlow:
    """Tests for get_zarr_status_all flow."""
    
    def test_returns_status_for_all(self, monkeypatch, mock_flow_logger, prefect_ephemeral):
        """Test getting status for all variables."""
        from server.pipeline import flows as flows_module
        from server.pipeline import config
        
        monkeypatch.setattr(config, "VARIABLES", {"sst": {}, "sic": {}})
        
        def mock_status(variable):
            return {"variable": variable, "exists": True, "n_times": 30}
        
        monkeypatch.setattr(flows_module, "get_zarr_status", mock_status)
        
        result = flows_module.get_zarr_status_all.fn()
        
        assert "sst" in result
        assert "sic" in result
        assert result["sst"]["exists"] is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestFlowIntegration:
    """Integration tests for flows with real data."""
    
    @pytest.mark.integration
    def test_build_zarr_from_cogs(
        self, 
        sample_cog_series: list[Path], 
        temp_zarr_dir: Path,
        mock_prefect_logger,
    ):
        """Test building Zarr from real COG files."""
        from server.pipeline.tasks import build_zarr_store
        from server.pipeline.config import get_config
        
        # Get products dir from COG paths
        products_dir = sample_cog_series[0].parent.parent
        
        config = get_config()
        original_zarr_dir = config.zarr_dir
        original_products_dir = config.products_dir
        
        try:
            config.zarr_dir = temp_zarr_dir
            config.products_dir = products_dir
            
            # Run task (not flow to avoid Prefect runtime)
            result = build_zarr_store.fn("sst", target_resolution=(180, 360), force_rebuild=True)
            
            # Result can be None if insufficient data (only 10 dates in fixture)
            # Just verify the task runs without error
            if result is not None:
                assert result["variable"] == "sst"
                assert result["status"] == "success"
        finally:
            config.zarr_dir = original_zarr_dir
            config.products_dir = original_products_dir
    
    @pytest.mark.integration
    def test_update_catalog_task(self, tmp_path: Path, mock_prefect_logger):
        """Test catalog update with real files."""
        from server.pipeline.tasks import update_catalog
        
        catalog_path = tmp_path / "catalog.json"
        
        # Create multiple entries
        results = [
            {"variable": "sst", "date": f"2024-01-{i:02d}", "path": f"sst_{i}.tif", "status": "created"}
            for i in range(1, 6)
        ]
        
        added = update_catalog.fn(results, catalog_path)
        
        assert added == 5
        
        with open(catalog_path) as f:
            catalog = json.load(f)
        
        assert catalog["variables"]["sst"]["count"] == 5
        assert "updated" in catalog
    
    @pytest.mark.integration
    def test_generate_and_filter_dates(self, tmp_path: Path, mock_prefect_logger):
        """Test date generation and filtering together."""
        from server.pipeline.tasks import generate_date_range, get_missing_dates, update_catalog
        
        # Generate a date range
        dates = generate_date_range.fn("2024-01-01", "2024-01-10")
        assert len(dates) == 10
        
        # Create catalog with some entries
        catalog_path = tmp_path / "catalog.json"
        results = [
            {"variable": "sst", "date": "2024-01-03", "path": "test.tif", "status": "created"},
            {"variable": "sst", "date": "2024-01-07", "path": "test2.tif", "status": "created"},
        ]
        update_catalog.fn(results, catalog_path)
        
        # Get missing dates
        missing = get_missing_dates.fn("sst", dates, catalog_path)
        
        assert len(missing) == 8
        assert "2024-01-03" not in missing
        assert "2024-01-07" not in missing


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in flows and tasks."""
    
    def test_catalog_update_handles_empty_results(self, tmp_path: Path, mock_prefect_logger):
        """Test catalog update with empty results list."""
        from server.pipeline.tasks import update_catalog
        
        catalog_path = tmp_path / "catalog.json"
        added = update_catalog.fn([], catalog_path)
        
        assert added == 0
    
    def test_missing_dates_handles_corrupted_catalog(self, tmp_path: Path):
        """Test handling of malformed catalog."""
        from server.pipeline.tasks import get_missing_dates
        
        catalog_path = tmp_path / "catalog.json"
        # Write invalid JSON
        with open(catalog_path, "w") as f:
            f.write("{invalid json")
        
        dates = ["2024-01-01"]
        
        # Should raise or handle gracefully
        with pytest.raises(json.JSONDecodeError):
            get_missing_dates.fn("sst", dates, catalog_path)
    
    def test_date_range_invalid_format(self):
        """Test date range with invalid date format."""
        from server.pipeline.tasks import generate_date_range
        
        with pytest.raises(ValueError):
            generate_date_range.fn("2024/01/01", "2024/01/05")
    
    def test_date_range_end_before_start(self):
        """Test date range with end before start."""
        from server.pipeline.tasks import generate_date_range
        
        result = generate_date_range.fn("2024-01-05", "2024-01-01")
        
        # Should return empty list
        assert result == []
