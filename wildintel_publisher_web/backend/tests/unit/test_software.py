"""Unit tests for the /api/software/clone endpoints —
software_service's actual clone_repository call is mocked out (no real
network / no git needed)."""
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _poll_clone(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    """Polls GET /api/software/clone/{task_id} until it's no longer
    'running' — see test_trapper.py's own _poll_download for why `client`
    must be opened as a context manager."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/software/clone/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Clone task {task_id} did not finish within {timeout}s: {body}")


def test_clone_status_unknown_task_returns_404():
    response = _client().get("/api/software/clone/does-not-exist")
    assert response.status_code == 404


def test_clone_start_and_poll_until_done():
    from main import app
    fake_path = Path("/tmp/fake-software-clone")

    # This exercises a real bug that was present until now: the /clone
    # route was a plain `def`, so software_service.start_clone_task's own
    # asyncio.create_task() had no running event loop to attach to (FastAPI
    # runs sync `def` routes in a worker thread) — the task was silently
    # dropped and this poll would hang forever. Must be `async def`, same
    # as trapper.py's own /download route.
    with patch("services.software_service.clone_repository", return_value=fake_path) as mock_clone:
        with TestClient(app) as client:
            start = client.post("/api/software/clone", json={"url": "https://github.com/user/repo.git"})
            assert start.status_code == 200
            task_id = start.json()["task_id"]
            assert task_id

            body = _poll_clone(client, task_id)

    assert body == {"status": "done", "path": str(fake_path), "error": None}
    mock_clone.assert_called_once()
    assert mock_clone.call_args.args[0] == "https://github.com/user/repo.git"
    assert mock_clone.call_args.kwargs["clear_cache"] is False


def test_clone_reports_error_status_on_failure():
    from main import app

    with patch("services.software_service.clone_repository", side_effect=RuntimeError("git clone failed")):
        with TestClient(app) as client:
            start = client.post("/api/software/clone", json={"url": "https://github.com/user/repo.git"})
            task_id = start.json()["task_id"]

            body = _poll_clone(client, task_id)

    assert body == {"status": "error", "path": None, "error": "git clone failed"}
