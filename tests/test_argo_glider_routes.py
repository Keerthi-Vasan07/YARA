"""
Regression tests for the isolated Argo/Glider FastAPI router
(argo_glider/backend/routes.py).

These tests exercise the router on its own, without booting the full YARA
ocean-data application, so they don't require the ocean pipeline's heavier
dependencies (rasterio/GDAL/xarray/Copernicus credentials, etc).

Run with:  pytest tests/test_argo_glider_routes.py
"""
from __future__ import annotations

from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from argo_glider.backend import routes as argo_glider_routes
from argo_glider.backend import glider_reader


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(argo_glider_routes.router)
    return TestClient(app)


class _FakePoint:
    def __init__(self) -> None:
        self.time = "2026-01-01T00:00:00Z"
        self.latitude = 1.0
        self.longitude = 2.0
        self.depth = 5.0
        self.temperature = 20.1
        self.salinity = 35.0
        self.pressure = 5.2
        self.glider_id = "g1"
        self.source = "IFREMER Glider FTP (dynamically discovered)"


class _FakeTrajectory:
    def __init__(self) -> None:
        self.glider_id = "g1"
        self.points = [_FakePoint()]
        self.source = "IFREMER Glider FTP (dynamically discovered)"


def test_gliders_endpoint_unwraps_reader_tuple(client: TestClient) -> None:
    """
    glider_reader.get_glider_trajectories() returns a
    (trajectories, statuses, discovery) tuple. The route must reshape this
    into {"gliders": [...], "statuses": [...], "discovery": {...}} so the
    frontend (which looks for a "gliders" key) actually receives the
    trajectories instead of a bare, unusable JSON tuple.
    """

    def fake_reader(force_refresh: bool = False):
        return (
            [_FakeTrajectory()],
            [{"file": "a.nc", "status": "ok", "points": 1}],
            {"method": "IFREMER FTP recursive NetCDF discovery"},
        )

    with mock.patch.object(glider_reader, "get_glider_trajectories", fake_reader):
        resp = client.get("/api/argo-glider/gliders")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"gliders", "statuses", "discovery"}
    assert len(body["gliders"]) == 1
    assert body["gliders"][0]["glider_id"] == "g1"
    assert body["gliders"][0]["points"][0]["latitude"] == 1.0


def test_gliders_endpoint_surfaces_source_failure(client: TestClient) -> None:
    """A total FTP failure must be visible in `statuses`, not silently
    swallowed as an empty-but-successful response."""

    def fake_reader_failure(force_refresh: bool = False):
        return (
            [],
            [{"status": "FTP connection error", "error": "timed out"}],
            {
                "method": "IFREMER FTP recursive NetCDF discovery",
                "candidate_file_count": 0,
            },
        )

    with mock.patch.object(glider_reader, "get_glider_trajectories", fake_reader_failure):
        resp = client.get("/api/argo-glider/gliders")

    assert resp.status_code == 200
    body = resp.json()
    assert body["gliders"] == []
    assert body["statuses"][0]["error"] == "timed out"


def test_health_endpoint_reports_both_readers(client: TestClient) -> None:
    resp = client.get("/api/argo-glider/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["argo_reader_available"] is True
    assert body["glider_reader_available"] is True
    assert body["errors"] == {}


def test_sources_endpoint_describes_both_modules(client: TestClient) -> None:
    resp = client.get("/api/argo-glider/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["argo"]["module"] == "argo_glider.backend.argo_reader"
    assert body["glider"]["module"] == "argo_glider.backend.glider_reader"
