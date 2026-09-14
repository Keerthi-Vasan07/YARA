from fastapi.testclient import TestClient

from server.main import app


def test_yara_backend_imports_and_core_health():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_argo_glider_health_does_not_break_yara():
    client = TestClient(app)
    response = client.get("/api/argo-glider/health")
    assert response.status_code in (200, 503)
