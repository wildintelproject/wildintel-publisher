"""Unit tests for the /api/b2share/* endpoints — b2share_service's B2SHARE/
HuggingFace Hub calls are mocked out (no real network), but settings.toml
reads/writes go through the real wildintel_publisher.config
machinery, isolated to a throwaway HOME by conftest.py."""
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _poll_publish(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    """Polls GET /api/b2share/publish/{task_id} until it's no longer 'running'.

    Must be called with `client` opened as a context manager, same reason as
    test_trapper.py's own _poll_download helper."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/b2share/publish/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Publish task {task_id} did not finish within {timeout}s: {body}")


def _write_fake_metadata_json(output_dir: Path) -> None:
    """Real prepare_b2share_export copies metadata.json into its output_dir
    (see product.copy_metadata_json) — these tests mock prepare_b2share_export
    out entirely, so they need to replicate that side effect themselves for
    copy_prepared_output_files (called right after upload/release succeed)
    to find it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        '{"product_type": "camtrapdp", "title": "T", "description": "D", '
        '"license": {"id": "CC-BY-4.0", "name": "CC-BY-4.0", "url": ""}, '
        '"authors": [{"name": "A", "affiliation": ""}], "publish_history": []}',
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _reset_b2share_config():
    """Resets settings.toml to fresh defaults before each test — several
    tests here save a real B2SHARE token, and without this it'd leak into
    whichever test runs next."""
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    yield


def test_get_config_defaults_to_sandbox_and_no_token_when_unset():
    response = _client().get("/api/b2share/config")
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "sandbox"
    assert body["community_id"] is None
    assert body["has_token"] is False


def test_test_token_success_saves_config():
    fake_response = MagicMock(status_code=200)
    with patch("services.b2share_service.httpx.get", return_value=fake_response) as mock_get:
        response = _client().post("/api/b2share/test-token", json={"token": "b2_x", "environment": "production"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    # B2SHARE 404s on GET /api/records/ (trailing slash) but not on
    # /api/records — a real request against trng-b2share.eudat.eu confirmed
    # this, so pin the exact URL to stop the slash from creeping back in.
    assert mock_get.call_args.args[0] == "https://b2share.eudat.eu/api/records"

    config_response = _client().get("/api/b2share/config")
    body = config_response.json()
    assert body["environment"] == "production"
    assert body["has_token"] is True


def test_test_token_reports_400_when_nothing_saved():
    response = _client().post("/api/b2share/test-token", json={})
    assert response.status_code == 400


def test_test_token_maps_invalid_token_to_401():
    fake_response = MagicMock(status_code=401)
    with patch("services.b2share_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/b2share/test-token", json={"token": "b2_bad"})
    assert response.status_code == 401


def test_test_token_maps_unexpected_server_error_to_502():
    """A non-auth HTTP error (e.g. a 500 during a B2SHARE outage) must not be
    reported as 'incorrect or expired token' — it's a different problem the
    user can't fix by retyping the token."""
    fake_response = MagicMock(status_code=500)
    with patch("services.b2share_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/b2share/test-token", json={"token": "b2_x"})
    assert response.status_code == 502


def test_test_token_maps_network_error_to_502():
    with patch("services.b2share_service.httpx.get", side_effect=RuntimeError("connection refused")):
        response = _client().post("/api/b2share/test-token", json={"token": "b2_x"})
    assert response.status_code == 502


def test_publish_link_mode_requires_hfh_repo_id():
    response = _client().post("/api/b2share/publish", json={
        "input_dir": "/tmp/camtrapdp", "token": "b2_x", "community_id": "uuid-1", "mirror_images": False,
    })
    assert response.status_code == 400


def test_publish_requires_community_id():
    response = _client().post("/api/b2share/publish", json={"input_dir": "/tmp/camtrapdp", "token": "b2_x"})
    assert response.status_code == 400


def test_publish_mirror_mode_start_and_poll_until_done(tmp_path):
    """Default output_mode='prepared': prepare/upload/release must run
    against a throwaway temporary directory, and the user's configured
    output_dir must end up with only the core Camtrap DP files — none of the
    full local export's extras (README.md/LICENSE/CITATION.cff/
    checksums-sha256.txt/images/), which only ever exist in the temporary
    directory."""
    from main import app
    fake_output_dir = tmp_path / "b2share"
    fake_record = {"pid": "10.5072/b2share.123", "record_url": "https://b2share.eudat.eu/records/123"}

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        (output_dir / "datapackage.json").write_text("{}")
        (output_dir / "media.csv").write_text("id\n1")
        (output_dir / "README.md").write_text("# hi")
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.b2share_service.b2share_service.prepare_b2share_export", side_effect=fake_prepare) as mock_prepare,
        patch("services.b2share_service.b2share_service.upload_to_b2share", return_value={"record_id": "123"}) as mock_upload,
        patch("services.b2share_service.b2share_service.release_on_b2share", return_value=fake_record) as mock_release,
    ):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "token": "b2_x", "community_id": "uuid-1",
            })
            assert start.status_code == 200
            task_id = start.json()["task_id"]
            assert task_id

            body = _poll_publish(client, task_id)

    assert body == {
        "status": "done", "stage": "done", "pid": "10.5072/b2share.123",
        "record_url": "https://b2share.eudat.eu/records/123", "output_dir": str(fake_output_dir), "error": None,
    }
    assert {p.name for p in fake_output_dir.iterdir()} == {"datapackage.json", "media.csv", "metadata.json"}
    mock_prepare.assert_called_once()
    mock_upload.assert_called_once()
    mock_release.assert_called_once()
    assert mock_prepare.call_args.kwargs["input_dir"] == Path("/tmp/camtrapdp")
    build_dir = mock_prepare.call_args.kwargs["output_dir"]
    assert build_dir != fake_output_dir  # prepare must never touch the real output_dir directly
    assert not build_dir.exists()  # cleaned up once the publish finished
    assert mock_prepare.call_args.kwargs["self_contained"] is True  # default: mirror
    assert mock_prepare.call_args.kwargs["hfh_repo_id"] is None
    assert "self_contained" not in mock_upload.call_args.kwargs  # upload no longer branches on it
    assert mock_upload.call_args.kwargs["community_id"] == "uuid-1"


def test_publish_link_mode_passes_through_hfh_repo_id(tmp_path):
    from main import app
    fake_output_dir = tmp_path / "b2share"

    with (
        patch("services.b2share_service.b2share_service.prepare_b2share_export", return_value=fake_output_dir) as mock_prepare,
        patch("services.b2share_service.b2share_service.upload_to_b2share", return_value={}),
        patch("services.b2share_service.b2share_service.release_on_b2share", return_value={"pid": "d", "record_url": "u"}),
    ):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir), "token": "b2_x",
                "community_id": "uuid-1", "mirror_images": False, "hfh_repo_id": "alice/dataset",
            })
            task_id = start.json()["task_id"]
            _poll_publish(client, task_id)

    assert mock_prepare.call_args.kwargs["self_contained"] is False
    assert mock_prepare.call_args.kwargs["hfh_repo_id"] == "alice/dataset"


def test_publish_output_mode_passthrough_reports_input_dir_as_output(tmp_path):
    from main import app
    fake_output_dir = tmp_path / "b2share"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.b2share_service.b2share_service.prepare_b2share_export", side_effect=fake_prepare),
        patch("services.b2share_service.b2share_service.upload_to_b2share", return_value={"record_id": "123"}),
        patch("services.b2share_service.b2share_service.release_on_b2share", return_value={"pid": "d", "record_url": "u"}),
    ):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "token": "b2_x", "community_id": "uuid-1", "output_mode": "passthrough",
            })
            task_id = start.json()["task_id"]
            body = _poll_publish(client, task_id)

    assert body["output_dir"] == "/tmp/camtrapdp"


def test_publish_output_mode_downloaded_fetches_files_from_b2share(tmp_path):
    from main import app
    fake_output_dir = tmp_path / "b2share"
    fake_record_with_files = {"files": [{"key": "README.md", "links": {"self": "https://b2share.eudat.eu/files/readme"}}]}
    fake_file_response = MagicMock(status_code=200, content=b"# hello")
    fake_file_response.raise_for_status.return_value = None

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.b2share_service.b2share_service.prepare_b2share_export", side_effect=fake_prepare),
        patch("services.b2share_service.b2share_service.upload_to_b2share", return_value={"record_id": "123"}),
        patch(
            "services.b2share_service.b2share_service.release_on_b2share",
            return_value={"pid": "10.5072/b2share.123", "record_url": "u", "record_id": "123"},
        ),
        patch("services.b2share_service.b2share_service.get_record", return_value=fake_record_with_files),
        patch("services.b2share_service.httpx.get", return_value=fake_file_response) as mock_get,
    ):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "token": "b2_x", "community_id": "uuid-1", "output_mode": "downloaded",
            })
            task_id = start.json()["task_id"]
            body = _poll_publish(client, task_id)

    expected_download_dir = fake_output_dir.parent / f"{fake_output_dir.name}-downloaded"
    assert body["output_dir"] == str(expected_download_dir)
    assert (expected_download_dir / "README.md").read_bytes() == b"# hello"
    mock_get.assert_called_once()


def test_publish_output_mode_downloaded_falls_back_to_prepared_when_pid_pending(tmp_path):
    """If B2SHARE hasn't assigned a PID yet (pending moderator approval),
    there's nothing published to download from — the prepared directory is
    reported instead."""
    from main import app
    fake_output_dir = tmp_path / "b2share"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.b2share_service.b2share_service.prepare_b2share_export", side_effect=fake_prepare),
        patch("services.b2share_service.b2share_service.upload_to_b2share", return_value={"record_id": "123"}),
        patch(
            "services.b2share_service.b2share_service.release_on_b2share",
            return_value={"pid": None, "record_url": "u", "record_id": "123"},
        ),
        patch("services.b2share_service.b2share_service.get_record") as mock_get_record,
    ):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "token": "b2_x", "community_id": "uuid-1", "output_mode": "downloaded",
            })
            task_id = start.json()["task_id"]
            body = _poll_publish(client, task_id)

    assert body["output_dir"] == str(fake_output_dir)
    mock_get_record.assert_not_called()


def test_publish_reports_error_status_on_failure(tmp_path):
    from main import app

    with patch("services.b2share_service.b2share_service.prepare_b2share_export", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={
                "input_dir": "/tmp/camtrapdp", "token": "b2_x", "community_id": "uuid-1",
            })
            task_id = start.json()["task_id"]

            body = _poll_publish(client, task_id)

    assert body == {
        "status": "error", "stage": "preparing", "pid": None, "record_url": None, "output_dir": None, "error": "boom",
    }


def test_publish_falls_back_to_saved_token_and_community_when_blank(tmp_path):
    from main import app

    fake_response = MagicMock(status_code=200)
    with patch("services.b2share_service.httpx.get", return_value=fake_response):
        _client().post("/api/b2share/test-token", json={"token": "b2_saved"})

    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, load_settings
    settings = load_settings()
    settings.B2SHARE.community_id = "uuid-saved"
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)

    with (
        patch("services.b2share_service.b2share_service.prepare_b2share_export", return_value=None),
        patch("services.b2share_service.b2share_service.upload_to_b2share", return_value={}) as mock_upload,
        patch("services.b2share_service.b2share_service.release_on_b2share", return_value={"pid": "d", "record_url": "u"}),
    ):
        with TestClient(app) as client:
            start = client.post("/api/b2share/publish", json={"input_dir": "/tmp/camtrapdp"})
            task_id = start.json()["task_id"]
            _poll_publish(client, task_id)

    assert mock_upload.call_args.kwargs["token"] == "b2_saved"
    assert mock_upload.call_args.kwargs["community_id"] == "uuid-saved"


def test_sync_pid_success_with_pid(tmp_path):
    with (
        patch("services.b2share_service.b2share_service.sync_pid_to_hfh", return_value="10.5072/b2share.123") as mock_sync,
        patch("services.b2share_service.upload_file") as mock_upload_file,
    ):
        response = _client().post("/api/b2share/sync-pid", json={
            "b2share_output_dir": str(tmp_path / "b2share"),
            "hfh_output_dir": str(tmp_path / "hfh"),
            "hfh_repo_id": "alice/dataset",
            "hfh_token": "hf_x",
        })

    assert response.status_code == 200
    assert response.json() == {"pid": "10.5072/b2share.123", "repo_url": "https://huggingface.co/datasets/alice/dataset"}
    mock_sync.assert_called_once_with(b2share_output_dir=tmp_path / "b2share", hfh_output_dir=tmp_path / "hfh")
    mock_upload_file.assert_not_called()  # no CITATION.cff/checksums exist under tmp_path in this test


def test_sync_pid_uploads_the_changed_files_when_present(tmp_path):
    hfh_output_dir = tmp_path / "hfh"
    hfh_output_dir.mkdir()
    (hfh_output_dir / "CITATION.cff").write_text("cff", encoding="utf-8")
    (hfh_output_dir / "README.md").write_text("readme", encoding="utf-8")
    (hfh_output_dir / "checksums-sha256.txt").write_text("sums", encoding="utf-8")

    with (
        patch("services.b2share_service.b2share_service.sync_pid_to_hfh", return_value="10.5072/b2share.123"),
        patch("services.b2share_service.upload_file") as mock_upload_file,
    ):
        response = _client().post("/api/b2share/sync-pid", json={
            "b2share_output_dir": str(tmp_path / "b2share"),
            "hfh_output_dir": str(hfh_output_dir),
            "hfh_repo_id": "alice/dataset",
            "hfh_token": "hf_x",
        })

    assert response.status_code == 200
    assert mock_upload_file.call_count == 3
    uploaded_names = {call.kwargs["path_in_repo"] for call in mock_upload_file.call_args_list}
    assert uploaded_names == {"CITATION.cff", "README.md", "checksums-sha256.txt"}


def test_sync_pid_returns_none_pid_when_pending_moderator_approval(tmp_path):
    """B2SHARE-specific: unlike Zenodo, publishing doesn't guarantee an
    immediate PID/DOI — it can be pending community moderator approval."""
    with (
        patch("services.b2share_service.b2share_service.sync_pid_to_hfh", return_value=None),
        patch("services.b2share_service.upload_file") as mock_upload_file,
    ):
        response = _client().post("/api/b2share/sync-pid", json={
            "b2share_output_dir": str(tmp_path / "b2share"),
            "hfh_output_dir": str(tmp_path / "hfh"),
            "hfh_repo_id": "alice/dataset",
            "hfh_token": "hf_x",
        })

    assert response.status_code == 200
    assert response.json()["pid"] is None
    mock_upload_file.assert_not_called()


def test_sync_pid_maps_runtime_error_to_400(tmp_path):
    with patch("services.b2share_service.b2share_service.sync_pid_to_hfh", side_effect=RuntimeError("not prepared")):
        response = _client().post("/api/b2share/sync-pid", json={
            "b2share_output_dir": str(tmp_path / "b2share"),
            "hfh_output_dir": str(tmp_path / "hfh"),
            "hfh_repo_id": "alice/dataset",
            "hfh_token": "hf_x",
        })

    assert response.status_code == 400
    assert "not prepared" in response.json()["detail"]


def test_sync_pid_requires_hfh_token_when_none_saved(tmp_path):
    response = _client().post("/api/b2share/sync-pid", json={
        "b2share_output_dir": str(tmp_path / "b2share"),
        "hfh_output_dir": str(tmp_path / "hfh"),
        "hfh_repo_id": "alice/dataset",
    })
    assert response.status_code == 400
