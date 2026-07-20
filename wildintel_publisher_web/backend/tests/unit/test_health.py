"""Unit tests for the /api/health and /api/version endpoints."""
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def test_health_returns_ok():
    response = _client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_expected_shape():
    response = _client().get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"current", "latest", "update_available", "release_url"}
