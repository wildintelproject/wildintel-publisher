"""Unit tests for the /api/gbif/* endpoints — gbif_service's GBIF Registry
API calls are mocked out (no real network), but settings.toml reads/writes
go through the real wildintel_publisher.config machinery, isolated to a
throwaway HOME by conftest.py.

Unlike HFH/Zenodo/B2SHARE there's no /api/gbif/publish endpoint: GBIF never
uploads anything of its own, so registering a dataset only happens as part
of a multi-repo publish (see services.publish_orchestrator) — covered by
test_publish_orchestrator.py, not here."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_gbif_config():
    """Resets settings.toml to fresh defaults before each test — several
    tests here save real GBIF credentials, and without this it'd leak into
    whichever test runs next."""
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    yield


def test_get_config_defaults_to_sandbox_and_no_credentials_when_unset():
    response = _client().get("/api/gbif/config")
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "sandbox"
    assert body["publishing_organization_key"] is None
    assert body["installation_key"] is None
    assert body["registry_language"] == "eng"
    assert body["has_credentials"] is False


def test_test_credentials_success_saves_config():
    fake_response = MagicMock(status_code=200)
    with patch("services.gbif_service.httpx.get", return_value=fake_response) as mock_get:
        response = _client().post("/api/gbif/test-credentials", json={
            "username": "alice", "password": "s3cret", "environment": "production",
        })
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert mock_get.call_args.kwargs["auth"] == ("alice", "s3cret")
    assert "api.gbif.org" in mock_get.call_args.args[0]

    config_response = _client().get("/api/gbif/config")
    body = config_response.json()
    assert body["environment"] == "production"
    assert body["has_credentials"] is True


def test_test_credentials_defaults_to_sandbox_host():
    fake_response = MagicMock(status_code=200)
    with patch("services.gbif_service.httpx.get", return_value=fake_response) as mock_get:
        response = _client().post("/api/gbif/test-credentials", json={"username": "alice", "password": "s3cret"})
    assert response.status_code == 200
    assert "api.gbif-test.org" in mock_get.call_args.args[0]


def test_test_credentials_reports_400_when_nothing_saved():
    response = _client().post("/api/gbif/test-credentials", json={})
    assert response.status_code == 400


def test_test_credentials_maps_invalid_credentials_to_401():
    fake_response = MagicMock(status_code=401)
    with patch("services.gbif_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/gbif/test-credentials", json={"username": "alice", "password": "bad"})
    assert response.status_code == 401


def test_test_credentials_maps_unexpected_server_error_to_502():
    """A non-auth HTTP error (e.g. a 500 during a GBIF outage) must not be
    reported as 'incorrect credentials' — it's a different problem the user
    can't fix by retyping the password."""
    fake_response = MagicMock(status_code=500)
    with patch("services.gbif_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/gbif/test-credentials", json={"username": "alice", "password": "s3cret"})
    assert response.status_code == 502


def test_test_credentials_maps_network_error_to_502():
    with patch("services.gbif_service.httpx.get", side_effect=RuntimeError("connection refused")):
        response = _client().post("/api/gbif/test-credentials", json={"username": "alice", "password": "s3cret"})
    assert response.status_code == 502


def test_test_credentials_falls_back_to_saved_credentials_when_blank():
    fake_response = MagicMock(status_code=200)
    with patch("services.gbif_service.httpx.get", return_value=fake_response):
        _client().post("/api/gbif/test-credentials", json={"username": "alice", "password": "s3cret"})

    with patch("services.gbif_service.httpx.get", return_value=fake_response) as mock_get:
        response = _client().post("/api/gbif/test-credentials", json={})
    assert response.status_code == 200
    assert mock_get.call_args.kwargs["auth"] == ("alice", "s3cret")
