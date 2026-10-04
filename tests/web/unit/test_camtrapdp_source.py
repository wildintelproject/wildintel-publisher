"""Unit tests for the /api/camtrapdp/fetch-archive and
/api/camtrapdp/resolve-local-source endpoints — camtrapdp_source_service's
actual fetch_camtrap_dp_archive/resolve_local_camtrapdp_source calls are
mocked out (no real network / no real local directory needed)."""
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
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
    from wildintel_publisher.web.main import app
    fake_path = Path("/tmp/fake-camtrapdp-archive")

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.fetch_camtrap_dp_archive", return_value=fake_path) as mock_fetch:
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
    from wildintel_publisher.web.main import app

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.fetch_camtrap_dp_archive", side_effect=RuntimeError("not a valid zip archive")):
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={"url": "https://example.org/datapackage.json"})
            task_id = start.json()["task_id"]

            body = _poll_fetch(client, task_id)

    assert body == {"status": "error", "path": None, "error": "not a valid zip archive"}


def test_fetch_archive_passes_clear_cache_through():
    from wildintel_publisher.web.main import app

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.fetch_camtrap_dp_archive", return_value=Path("/tmp/out")) as mock_fetch:
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={
                "url": "https://example.org/camtrapdp-remote.zip", "clear_cache": True,
            })
            _poll_fetch(client, start.json()["task_id"])

    assert mock_fetch.call_args.kwargs["clear_cache"] is True


def test_fetch_archive_persists_a_session_that_flips_to_fetched():
    from wildintel_publisher.web.main import app
    from wildintel_publisher.web.services import session_store

    fake_path = Path("/tmp/fake-camtrapdp-archive")
    with patch("wildintel_publisher.web.services.camtrapdp_source_service.fetch_camtrap_dp_archive", return_value=fake_path):
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={"url": "https://example.org/camtrapdp-remote.zip"})
            task_id = start.json()["task_id"]
            _poll_fetch(client, task_id)

    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "fetched"
    assert manifest["source_type"] == "archive"
    assert manifest["fetch"]["params"] == {"url": "https://example.org/camtrapdp-remote.zip", "clear_cache": False}
    assert manifest["fetch"]["input_dir"] == str(fake_path)


def test_resume_fetch_archive_replays_the_original_url():
    from wildintel_publisher.web.main import app
    from wildintel_publisher.web.services import session_store

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.fetch_camtrap_dp_archive", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            start = client.post("/api/camtrapdp/fetch-archive", json={"url": "https://example.org/camtrapdp-remote.zip"})
            task_id = start.json()["task_id"]
            _poll_fetch(client, task_id)

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.fetch_camtrap_dp_archive", return_value=Path("/tmp/out")) as mock_fetch:
        with TestClient(app) as client:
            resume = client.post(f"/api/camtrapdp/fetch-archive/{task_id}/resume")
            assert resume.status_code == 200, resume.text
            assert resume.json()["task_id"] == task_id
            body = _poll_fetch(client, task_id)

    assert body["status"] == "done"
    assert mock_fetch.call_args.args[0] == "https://example.org/camtrapdp-remote.zip"
    assert session_store.read_manifest(task_id)["phase"] == "fetched"


def test_resume_fetch_archive_rejects_an_unknown_task_id():
    response = _client().post("/api/camtrapdp/fetch-archive/does-not-exist/resume")
    assert response.status_code == 400


def test_resolve_local_source_returns_the_working_dir_and_a_fresh_task_id_on_success():
    with patch(
        "wildintel_publisher.web.services.camtrapdp_source_service.resolve_local_camtrapdp_source",
        return_value=Path("/app/sessions/xyz/source"),
    ) as mock_resolve:
        response = _client().post("/api/camtrapdp/resolve-local-source", json={"path": "/data/camtrapdp"})

    body = response.json()
    task_id = body.pop("taskId")
    assert task_id
    assert body == {
        "status": "valid", "workingDir": "/app/sessions/xyz/source", "sourceDir": "/data/camtrapdp", "error": None,
    }
    mock_resolve.assert_called_once()
    assert mock_resolve.call_args.args[0] == Path("/data/camtrapdp")
    # use_hash_subdir=False: this session's own output_dir is already
    # unique, so the working copy lands straight in it — no extra
    # <output_dir>/<hash-of-path> nesting (that's for the CLI's own
    # shared-output_dir usage — see resolve_local_camtrapdp_source).
    assert mock_resolve.call_args.kwargs == {"use_hash_subdir": False}


def test_resolve_local_source_persists_a_session_that_lands_on_fetched():
    """Regression test: a Local Directory source used to skip session_store
    entirely (see services.session_store's own docstring) — the working
    copy lived in a generic, path-keyed scratch folder that a later,
    unrelated resolve of the SAME path could recreate from scratch,
    silently discarding a metadata.json a preprocessing step had already
    written into it. Every source now gets a session, this one included."""
    from wildintel_publisher.web.services import session_store

    with patch(
        "wildintel_publisher.web.services.camtrapdp_source_service.resolve_local_camtrapdp_source",
        return_value=Path("/app/sessions/xyz/source/abc123"),
    ):
        response = _client().post("/api/camtrapdp/resolve-local-source", json={"path": "/data/camtrapdp"})
    task_id = response.json()["taskId"]

    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "fetched"
    assert manifest["status"] == "done"
    assert manifest["product_type"] == "camtrapdp"
    assert manifest["source_type"] == "local"
    assert manifest["fetch"]["source_type"] == "local"
    assert manifest["fetch"]["params"] == {"path": "/data/camtrapdp"}
    assert manifest["fetch"]["input_dir"] == "/app/sessions/xyz/source/abc123"


def test_resolve_local_source_reuses_the_given_session_task_id_instead_of_minting_a_new_one():
    """The frontend re-resolves on every debounced path edit (see
    LocalDirectoryForm's own live preview) — passing back the taskId a
    prior call already minted must land in the SAME session, not litter a
    fresh one per keystroke."""
    from wildintel_publisher.web.services import session_store

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.resolve_local_camtrapdp_source", return_value=Path("/app/sessions/xyz/source/abc123")):
        first = _client().post("/api/camtrapdp/resolve-local-source", json={"path": "/data/camtrapdp"})
    task_id = first.json()["taskId"]

    with patch("wildintel_publisher.web.services.camtrapdp_source_service.resolve_local_camtrapdp_source", return_value=Path("/app/sessions/xyz/source/def456")) as mock_resolve:
        second = _client().post(
            "/api/camtrapdp/resolve-local-source", json={"path": "/data/camtrapdp-renamed", "session_task_id": task_id},
        )

    assert second.json()["taskId"] == task_id
    manifest = session_store.read_manifest(task_id)
    assert manifest["fetch"]["params"] == {"path": "/data/camtrapdp-renamed"}
    assert manifest["fetch"]["input_dir"] == "/app/sessions/xyz/source/def456"
    # The second call's own output_dir was still derived from this SAME
    # session_dir — not a freshly minted one.
    assert mock_resolve.call_args.args[1] == session_store.session_dir(task_id) / "source"


def test_resolve_local_source_reports_invalid_status_on_failure():
    with patch(
        "wildintel_publisher.web.services.camtrapdp_source_service.resolve_local_camtrapdp_source",
        side_effect=RuntimeError("datapackage.json not found."),
    ):
        response = _client().post("/api/camtrapdp/resolve-local-source", json={"path": "/not/a/camtrapdp"})

    body = response.json()
    task_id = body.pop("taskId")
    assert task_id
    assert body == {
        "status": "invalid", "workingDir": None, "sourceDir": "/not/a/camtrapdp", "error": "datapackage.json not found.",
    }


def test_resolve_local_source_persists_the_error_but_keeps_the_session_resumable():
    """A failed local resolve still gets a session (see
    resolve_local_source's own docstring) — status "error" lets the web
    app's "resume this?" screen offer another attempt against the exact
    same task_id, pre-filling the path the user already typed."""
    from wildintel_publisher.web.services import session_store

    with patch(
        "wildintel_publisher.web.services.camtrapdp_source_service.resolve_local_camtrapdp_source",
        side_effect=RuntimeError("datapackage.json not found."),
    ):
        response = _client().post("/api/camtrapdp/resolve-local-source", json={"path": "/not/a/camtrapdp"})
    task_id = response.json()["taskId"]

    manifest = session_store.read_manifest(task_id)
    assert manifest["status"] == "error"
    assert manifest["error"] == "datapackage.json not found."
    assert manifest["source_type"] == "local"
    assert manifest["fetch"]["params"] == {"path": "/not/a/camtrapdp"}
    assert task_id in {s["task_id"] for s in session_store.list_sessions()}
