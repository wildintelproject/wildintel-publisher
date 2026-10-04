"""Unit tests for the /api/software/clone endpoints —
software_service's actual clone_repository call is mocked out (no real
network / no git needed)."""
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
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
    from wildintel_publisher.web.main import app
    fake_path = Path("/tmp/fake-software-clone")

    # This exercises a real bug that was present until now: the /clone
    # route was a plain `def`, so software_service.start_clone_task's own
    # asyncio.create_task() had no running event loop to attach to (FastAPI
    # runs sync `def` routes in a worker thread) — the task was silently
    # dropped and this poll would hang forever. Must be `async def`, same
    # as trapper.py's own /download route.
    with patch("wildintel_publisher.web.services.software_service.clone_repository", return_value=fake_path) as mock_clone:
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
    from wildintel_publisher.web.main import app

    with patch("wildintel_publisher.web.services.software_service.clone_repository", side_effect=RuntimeError("git clone failed")):
        with TestClient(app) as client:
            start = client.post("/api/software/clone", json={"url": "https://github.com/user/repo.git"})
            task_id = start.json()["task_id"]

            body = _poll_clone(client, task_id)

    assert body == {"status": "error", "path": None, "error": "git clone failed"}


def test_clone_persists_a_session_that_flips_to_fetched():
    from wildintel_publisher.web.main import app
    from wildintel_publisher.web.services import session_store

    fake_path = Path("/tmp/fake-software-clone")
    with patch("wildintel_publisher.web.services.software_service.clone_repository", return_value=fake_path):
        with TestClient(app) as client:
            start = client.post("/api/software/clone", json={"url": "https://github.com/user/repo.git"})
            task_id = start.json()["task_id"]
            _poll_clone(client, task_id)

    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "fetched"
    assert manifest["source_type"] == "git"
    assert manifest["product_type"] == "software"
    assert manifest["fetch"]["params"] == {"url": "https://github.com/user/repo.git", "clear_cache": False}
    assert manifest["fetch"]["input_dir"] == str(fake_path)


def test_resume_clone_replays_the_original_url():
    from wildintel_publisher.web.main import app
    from wildintel_publisher.web.services import session_store

    with patch("wildintel_publisher.web.services.software_service.clone_repository", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            start = client.post("/api/software/clone", json={"url": "https://github.com/user/repo.git"})
            task_id = start.json()["task_id"]
            _poll_clone(client, task_id)

    with patch("wildintel_publisher.web.services.software_service.clone_repository", return_value=Path("/tmp/out")) as mock_clone:
        with TestClient(app) as client:
            resume = client.post(f"/api/software/clone/{task_id}/resume")
            assert resume.status_code == 200, resume.text
            assert resume.json()["task_id"] == task_id
            body = _poll_clone(client, task_id)

    assert body["status"] == "done"
    assert mock_clone.call_args.args[0] == "https://github.com/user/repo.git"
    assert session_store.read_manifest(task_id)["phase"] == "fetched"


def test_resume_clone_rejects_an_unknown_task_id():
    response = _client().post("/api/software/clone/does-not-exist/resume")
    assert response.status_code == 400
