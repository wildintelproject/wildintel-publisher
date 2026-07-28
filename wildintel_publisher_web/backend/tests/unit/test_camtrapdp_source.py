"""Unit tests for the /api/camtrapdp/fetch-archive endpoints —
camtrapdp_source_service's actual fetch_camtrap_dp_archive call is mocked
out (no real network / no live archive needed)."""
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _poll_fetch(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    """Polls GET /api/camtrapdp/fetch-archive/{task_id} until it's no longer
    'running' — see test_trapper.py's own _poll_download for why `client`
    must be opened as a context manager."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/camtrapdp/fetch-archive/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Fetch task {task_id} did not finish within {timeout}s: {body}")


def test_fetch_archive_status_unknown_task_returns_404():
    response = _client().get("/api/camtrapdp/fetch-archive/does-not-exist")
    assert response.status_code == 404


def test_fetch_archive_start_and_poll_until_done():
    from main import app
    fake_path = Path("/tmp/fake-camtrapdp-archive")

    with patch("services.camtrapdp_source_service.fetch_camtrap_dp_archive", return_value=fake_path) as mock_fetch:
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={
                "url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
            })
            assert start.status_code == 200
            task_id = start.json()["task_id"]
            assert task_id

            body = _poll_fetch(client, task_id)

    assert body == {"status": "done", "path": str(fake_path), "error": None}
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.args[0] == "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip"
    assert mock_fetch.call_args.kwargs["clear_cache"] is False


def test_fetch_archive_reports_error_status_on_failure():
    from main import app

    with patch("services.camtrapdp_source_service.fetch_camtrap_dp_archive", side_effect=RuntimeError("not a valid zip archive")):
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={"url": "https://example.org/datapackage.json"})
            task_id = start.json()["task_id"]

            body = _poll_fetch(client, task_id)

    assert body == {"status": "error", "path": None, "error": "not a valid zip archive"}


def test_fetch_archive_passes_clear_cache_through():
    from main import app

    with patch("services.camtrapdp_source_service.fetch_camtrap_dp_archive", return_value=Path("/tmp/out")) as mock_fetch:
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={
                "url": "https://example.org/camtrapdp-remote.zip", "clear_cache": True,
            })
            _poll_fetch(client, start.json()["task_id"])

    assert mock_fetch.call_args.kwargs["clear_cache"] is True
