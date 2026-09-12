"""
Comprehensive Unit Tests for YARA Master Multi-Format Scientific Ingestion & Playback.
"""

from pathlib import Path
import pytest
import numpy as np
from fastapi.testclient import TestClient

from server.main import app
from server.data_sources.local.detector import detect_dataset_format
from server.data_sources.local.common_model import DatasetFormat, TemporalResolution
from server.data_sources.local.netcdf_reader import NetCDFReader
from server.data_sources.local.registry import registry
from server.data_sources.local.time_utils import analyze_time_axis
from server.data_sources.local.coordinate_utils import normalize_longitude_180, normalize_grid_to_wgs84
from server.pipeline.frame_cache import frame_cache
from server.pipeline.playback_manager import playback_manager

SAMPLE_NC_PATH = Path("local_dataset/oisst-avhrr-v02r01.20250218.nc")


def test_format_detector_netcdf():
    """Verify format detector identifies NetCDF files."""
    assert SAMPLE_NC_PATH.exists(), "Sample NetCDF must exist"
    fmt, reason = detect_dataset_format(SAMPLE_NC_PATH)
    assert fmt == DatasetFormat.NETCDF
    assert "NetCDF" in reason


def test_coordinate_normalization():
    """Verify 0-360 to -180-180 and north-up grid sorting."""
    # 0 to 360 lon
    lons = np.array([0.0, 90.0, 180.0, 270.0, 359.0])
    lats = np.array([-80.0, 0.0, 80.0])  # ascending
    data = np.ones((3, 5), dtype=np.float32)

    norm_data, norm_lat, norm_lon, extent = normalize_grid_to_wgs84(data, lats, lons)

    # Lons must be [-180, 180] ascending
    assert norm_lon[0] >= -180.0
    assert norm_lon[-1] <= 180.0
    assert np.all(np.diff(norm_lon) >= 0)

    # Lats must be North-to-South descending (row 0 is North)
    assert norm_lat[0] > norm_lat[-1]
    assert extent.north == 80.0
    assert extent.south == -80.0


def test_time_axis_analysis():
    """Verify temporal resolution detection."""
    # Daily timestamps
    daily_times = ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"]
    res_daily = analyze_time_axis(daily_times)
    assert res_daily.resolution == TemporalResolution.DAILY
    assert res_daily.count == 3

    # Hourly timestamps
    hourly_times = ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"]
    res_hourly = analyze_time_axis(hourly_times)
    assert res_hourly.resolution == TemporalResolution.HOURLY
    assert res_hourly.count == 3

    # 3-hourly timestamps
    three_h_times = ["2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z", "2026-01-01T06:00:00Z"]
    res_3h = analyze_time_axis(three_h_times)
    assert res_3h.resolution == TemporalResolution.THREE_HOURLY

    # Single timestamp
    res_single = analyze_time_axis(["2026-01-01T12:00:00Z"])
    assert res_single.resolution == TemporalResolution.SINGLE


def test_netcdf_reader_inspection_and_slicing():
    """Verify NetCDF reader on real sample file."""
    reader = NetCDFReader(SAMPLE_NC_PATH)
    meta = reader.inspect()

    assert meta.id == "oisst-avhrr-v02r01.20250218"
    assert meta.format == DatasetFormat.NETCDF
    assert "sst" in meta.variables
    assert "anom" in meta.variables
    assert "ice" in meta.variables
    assert meta.default_variable == "sst"

    # Test reading frame slice
    slice_data = reader.read_frame("sst", 0)
    assert slice_data.data.shape == (720, 1440)
    assert slice_data.variable_name == "sst"
    assert slice_data.min_val >= -2.0
    assert slice_data.max_val <= 36.0

    # Test point query
    pt = reader.get_point_value(0.0, 0.0, "sst", 0)
    assert pt.is_valid is True
    assert pt.value is not None
    assert pt.matched_lat is not None
    assert pt.matched_lon is not None


def test_playback_frame_caching():
    """Verify frame rendering to PNG and two-tier caching."""
    registry.scan_directory(Path("local_dataset"))
    ds_id = "oisst-avhrr-v02r01.20250218"

    # Frame 1 rendering
    png_bytes = playback_manager.get_or_render_frame(ds_id, "sst", 0)
    assert len(png_bytes) > 1000
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Cache hit
    cached = frame_cache.get(ds_id, "sst", 0)
    assert cached == png_bytes


def test_api_endpoints():
    """Verify FastAPI local dataset endpoints."""
    client = TestClient(app)

    # 1. Active mode
    resp = client.get("/api/local-dataset/active")
    assert resp.status_code == 200
    assert "mode" in resp.json()

    # 2. List datasets
    resp = client.get("/api/local-dataset/list")
    assert resp.status_code == 200
    ds_list = resp.json()
    assert len(ds_list) >= 1

    ds_id = ds_list[0]["id"]

    # 3. Activate
    resp = client.post(f"/api/local-dataset/{ds_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["id"] == ds_id

    # 4. Metadata
    resp = client.get(f"/api/local-dataset/{ds_id}/metadata")
    assert resp.status_code == 200
    assert resp.json()["default_variable"] == "sst"

    # 5. Variables
    resp = client.get(f"/api/local-dataset/{ds_id}/variables")
    assert resp.status_code == 200
    assert "sst" in resp.json()["variables"]

    # 6. Times
    resp = client.get(f"/api/local-dataset/{ds_id}/times")
    assert resp.status_code == 200
    assert len(resp.json()["timestamps"]) >= 1

    # 7. Render frame PNG
    resp = client.get(f"/api/local-dataset/{ds_id}/frame?variable=sst&time_index=0")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 1000

    # 8. Point query (Atlantic ocean point: lat=0.0, lon=-20.0)
    resp = client.get(f"/api/local-dataset/{ds_id}/point?lat=0.0&lon=-20.0&variable=sst")
    assert resp.status_code == 200
    pdata = resp.json()
    assert pdata["is_valid"] is True
    assert pdata["value"] is not None

    # Land point (Central Africa: lat=10.0, lon=20.0 should be masked/invalid)
    resp_land = client.get(f"/api/local-dataset/{ds_id}/point?lat=10.0&lon=20.0&variable=sst")
    assert resp_land.status_code == 200
    assert resp_land.json()["is_valid"] is False

    # 9. Deactivate (switch back to Online)
    resp = client.post("/api/local-dataset/deactivate")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "online"


def test_zarr_discovery_and_activation():
    """Verify that .zarr directories in local_dataset/ are discovered, inspected, and rendered."""
    zarr_path = Path("local_dataset/oisst-avhrr-v02r01.20250219.zarr")
    if not zarr_path.exists():
        pytest.skip("Sample Zarr dataset not present")

    fmt, reason = detect_dataset_format(zarr_path)
    assert fmt == DatasetFormat.ZARR

    client = TestClient(app)
    resp = client.get("/api/local-dataset/list")
    assert resp.status_code == 200
    datasets = resp.json()

    zarr_ds = next((d for d in datasets if d["format"] == "zarr" and "oisst" in d["name"]), None)
    assert zarr_ds is not None, "Zarr dataset must be discovered in /api/local-dataset/list"
    assert zarr_ds["name"] == "oisst-avhrr-v02r01.20250219.zarr"
    assert "sst" in zarr_ds["variables"]
    assert "anom" in zarr_ds["variables"]
    assert "err" in zarr_ds["variables"]
    assert "ice" in zarr_ds["variables"]
    assert zarr_ds["file_size_bytes"] > 0

    # Activate Zarr
    act_resp = client.post(f"/api/local-dataset/{zarr_ds['id']}/activate")
    assert act_resp.status_code == 200

    # Render frame
    frame_resp = client.get(f"/api/local-dataset/{zarr_ds['id']}/frame?variable=sst&time_index=0")
    assert frame_resp.status_code == 200
    assert frame_resp.headers["content-type"] == "image/png"
    assert len(frame_resp.content) > 1000

    # Point query
    pt_resp = client.get(f"/api/local-dataset/{zarr_ds['id']}/point?lat=0.0&lon=-20.0&variable=sst")
    assert pt_resp.status_code == 200
    assert pt_resp.json()["is_valid"] is True
    assert pt_resp.json()["value"] is not None
