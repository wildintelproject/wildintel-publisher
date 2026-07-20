"""Unit tests for the /api/trapper/* endpoints — trapper_service's Trapper
calls are mocked out (no real network / no live Trapper server needed), but
settings.toml reads/writes go through the real wildintel_publisher.config
machinery, isolated to a throwaway HOME by conftest.py."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from trapper_client import err


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _poll_download(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    """Polls GET /api/trapper/download/{task_id} until it's no longer 'running'.

    Must be called with `client` opened as a context manager (`with
    TestClient(app) as client:`) — a bare TestClient() spins up a fresh,
    short-lived event loop per call, which orphans the background
    asyncio.create_task before it ever runs; the context-manager form keeps
    one event loop alive across calls so the task can actually progress."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/trapper/download/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Download task {task_id} did not finish within {timeout}s: {body}")


CREDS = {"url": "https://trapper.example", "username": "u", "password": "p"}


@pytest.fixture(autouse=True)
def _reset_trapper_config():
    """Resets settings.toml to fresh defaults before each test — several
    tests here save real TRAPPER credentials via /test-connection, and
    without this they'd leak into whichever test runs next."""
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    yield


def test_get_config_defaults_to_none_and_no_password_when_unset():
    response = _client().get("/api/trapper/config")
    assert response.status_code == 200
    assert response.json() == {"base_url": None, "user_name": None, "has_password": False}


def test_test_connection_success():
    with patch("services.trapper_service.test_connection", return_value={"ok": True, "research_projects_count": 3}):
        response = _client().post("/api/trapper/test-connection", json=CREDS)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "research_projects_count": 3}


def test_test_connection_saves_credentials_on_success():
    with patch("services.trapper_service.test_connection", return_value={"ok": True, "research_projects_count": 3}):
        response = _client().post("/api/trapper/test-connection", json=CREDS)
    assert response.status_code == 200

    config_response = _client().get("/api/trapper/config")
    assert config_response.json() == {"base_url": "https://trapper.example", "user_name": "u", "has_password": True}


def test_test_connection_does_not_save_credentials_on_failure():
    with patch("services.trapper_service.test_connection", side_effect=err.UnauthorizedError("bad credentials")):
        _client().post("/api/trapper/test-connection", json=CREDS)

    config_response = _client().get("/api/trapper/config")
    assert config_response.json()["base_url"] is None


def test_test_connection_falls_back_to_saved_credentials_when_fields_blank():
    with patch("services.trapper_service.test_connection", return_value={"ok": True, "research_projects_count": 3}):
        _client().post("/api/trapper/test-connection", json=CREDS)

    with patch("services.trapper_service.test_connection", return_value={"ok": True, "research_projects_count": 5}) as mock_test:
        response = _client().post("/api/trapper/test-connection", json={"url": None, "username": None, "password": None})

    assert response.status_code == 200
    mock_test.assert_called_once_with("https://trapper.example", "u", "p")


def test_test_connection_reports_missing_fields_when_nothing_saved():
    response = _client().post("/api/trapper/test-connection", json={})
    assert response.status_code == 400
    assert "Missing Trapper" in response.json()["detail"]


def test_test_connection_maps_unauthorized_to_401():
    with patch("services.trapper_service.test_connection", side_effect=err.UnauthorizedError("bad credentials")):
        response = _client().post("/api/trapper/test-connection", json=CREDS)
    assert response.status_code == 401
    assert "Incorrect Trapper username or password" in response.json()["detail"]


def test_test_connection_maps_forbidden_to_403():
    with patch("services.trapper_service.test_connection", side_effect=err.ForbiddenError("no access")):
        response = _client().post("/api/trapper/test-connection", json=CREDS)
    assert response.status_code == 403


def test_test_connection_maps_connect_error_to_502():
    import httpx
    with patch("services.trapper_service.test_connection", side_effect=httpx.ConnectError("refused")):
        response = _client().post("/api/trapper/test-connection", json=CREDS)
    assert response.status_code == 502


def test_research_projects_returns_results():
    fake_results = [{"pk": 1, "name": "Project A", "acronym": "PA"}]
    with patch("services.trapper_service.list_research_projects", return_value=fake_results):
        response = _client().post("/api/trapper/research-projects", json=CREDS)
    assert response.status_code == 200
    assert response.json() == {"results": fake_results}


def test_classification_projects_requires_research_project_pk():
    response = _client().post("/api/trapper/classification-projects", json=CREDS)
    assert response.status_code == 422  # missing research_project_pk


def test_classification_projects_returns_results():
    fake_results = [{"pk": 10, "name": "Classif A", "is_active": True}]
    with patch("services.trapper_service.list_classification_projects", return_value=fake_results) as mock_list:
        response = _client().post("/api/trapper/classification-projects", json={**CREDS, "research_project_pk": 1})
    assert response.status_code == 200
    assert response.json() == {"results": fake_results}
    mock_list.assert_called_once_with("https://trapper.example", "u", "p", 1)


def test_deployments_returns_results():
    fake_results = [{"pk": 100, "deployment_id": "r0007-dona_0018", "location_id": "L1"}]
    with patch("services.trapper_service.list_deployments", return_value=fake_results) as mock_list:
        response = _client().post("/api/trapper/deployments", json={**CREDS, "classification_project_pk": 10})
    assert response.status_code == 200
    assert response.json() == {"results": fake_results}
    mock_list.assert_called_once_with("https://trapper.example", "u", "p", 10)


def test_download_status_unknown_task_returns_404():
    response = _client().get("/api/trapper/download/does-not-exist")
    assert response.status_code == 404


def test_download_start_and_poll_until_done():
    from main import app
    fake_path = Path("/tmp/fake-camtrapdp-output")

    with patch("services.trapper_service.fetch_camtrapdp_package", return_value=fake_path) as mock_fetch:
        with TestClient(app) as client:
            start = client.post("/api/trapper/download", json={**CREDS, "project_id": 1, "deployment_id": "r0007-dona_0018"})
            assert start.status_code == 200
            task_id = start.json()["task_id"]
            assert task_id

            body = _poll_download(client, task_id)

    assert body == {"status": "done", "path": str(fake_path), "error": None}
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args.kwargs
    assert call_kwargs["trapper_url"] == "https://trapper.example"
    assert call_kwargs["trapper_user"] == "u"
    assert call_kwargs["trapper_password"] == "p"
    assert call_kwargs["project_id"] == 1
    assert call_kwargs["deployment_id"] == "r0007-dona_0018"
    assert call_kwargs["clear_cache"] is False


def test_download_reports_error_status_on_failure():
    from main import app

    with patch("services.trapper_service.fetch_camtrapdp_package", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            start = client.post("/api/trapper/download", json={**CREDS, "project_id": 1, "deployment_id": "d1"})
            task_id = start.json()["task_id"]

            body = _poll_download(client, task_id)

    assert body == {"status": "error", "path": None, "error": "boom"}


def test_download_falls_back_to_saved_credentials_when_fields_blank():
    from main import app

    with patch("services.trapper_service.test_connection", return_value={"ok": True, "research_projects_count": 1}):
        _client().post("/api/trapper/test-connection", json=CREDS)

    with patch("services.trapper_service.fetch_camtrapdp_package", return_value=Path("/tmp/x")) as mock_fetch:
        with TestClient(app) as client:
            start = client.post("/api/trapper/download", json={
                "url": None, "username": None, "password": None, "project_id": 1, "deployment_id": "d1",
            })
            task_id = start.json()["task_id"]
            _poll_download(client, task_id)

    call_kwargs = mock_fetch.call_args.kwargs
    assert call_kwargs["trapper_url"] == "https://trapper.example"
    assert call_kwargs["trapper_user"] == "u"
    assert call_kwargs["trapper_password"] == "p"
