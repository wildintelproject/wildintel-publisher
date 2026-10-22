"""Unit tests for the /api/zenodo/* endpoints — zenodo_service's Zenodo/
HuggingFace Hub calls are mocked out (no real network), but settings.toml
reads/writes go through the real wildintel_publisher.core.config
machinery, isolated to a throwaway HOME by conftest.py."""
import time
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
    return TestClient(app)


def _poll_publish(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    """Polls GET /api/zenodo/publish/{task_id} until it's no longer 'running'.

    Must be called with `client` opened as a context manager, same reason as
    test_trapper.py's own _poll_download helper."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/zenodo/publish/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Publish task {task_id} did not finish within {timeout}s: {body}")


def _write_fake_metadata_json(output_dir: Path) -> None:
    """Real prepare_zenodo_export copies metadata.json into its output_dir
    (see product.copy_metadata_json) — these tests mock prepare_zenodo_export
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
def _reset_zenodo_config():
    """Resets settings.toml to fresh defaults before each test — several
    tests here save a real ZENODO token, and without this it'd leak into
    whichever test runs next."""
    from dynaconf import loaders
    from wildintel_publisher.core.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    yield


def test_get_config_defaults_to_sandbox_and_no_token_when_unset():
    response = _client().get("/api/zenodo/config")
    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "sandbox"
    assert body["communities"] is None
    assert body["has_token"] is False


def test_test_token_success_saves_config():
    fake_response = MagicMock(status_code=200)
    with patch("wildintel_publisher.web.services.zenodo_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/zenodo/test-token", json={"token": "zen_x", "environment": "production"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    config_response = _client().get("/api/zenodo/config")
    body = config_response.json()
    assert body["environment"] == "production"
    assert body["has_token"] is True


def test_test_token_reports_400_when_nothing_saved():
    response = _client().post("/api/zenodo/test-token", json={})
    assert response.status_code == 400


def test_test_token_maps_invalid_token_to_401():
    fake_response = MagicMock(status_code=401)
    with patch("wildintel_publisher.web.services.zenodo_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/zenodo/test-token", json={"token": "zen_bad"})
    assert response.status_code == 401


def test_test_token_maps_unexpected_server_error_to_502():
    """A non-auth HTTP error (e.g. a 500 during a Zenodo outage) must not be
    reported as 'incorrect or expired token' — it's a different problem the
    user can't fix by retyping the token."""
    fake_response = MagicMock(status_code=500)
    with patch("wildintel_publisher.web.services.zenodo_service.httpx.get", return_value=fake_response):
        response = _client().post("/api/zenodo/test-token", json={"token": "zen_x"})
    assert response.status_code == 502


def test_test_token_maps_network_error_to_502():
    with patch("wildintel_publisher.web.services.zenodo_service.httpx.get", side_effect=RuntimeError("connection refused")):
        response = _client().post("/api/zenodo/test-token", json={"token": "zen_x"})
    assert response.status_code == 502


def test_publish_link_mode_requires_hfh_repo_id():
    response = _client().post("/api/zenodo/publish", json={
        "input_dir": "/tmp/camtrapdp", "token": "zen_x", "mirror_images": False,
    })
    assert response.status_code == 400


def test_publish_mirror_mode_start_and_poll_until_done(tmp_path):
    """Default output_mode='prepared': prepare/upload/release must run
    against a throwaway temporary directory, and the user's configured
    output_dir must end up with only the core Camtrap DP files — none of the
    full local export's extras (README.md/LICENSE/CITATION.cff/
    checksums-sha256.txt/images/camtrapdp.zip), which only ever exist in the
    temporary directory."""
    from wildintel_publisher.web.main import app
    fake_output_dir = tmp_path / "zenodo"
    fake_record = {"doi": "10.5281/zenodo.123", "record_url": "https://zenodo.org/records/123"}

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        (output_dir / "datapackage.json").write_text("{}")
        (output_dir / "media.csv").write_text("id\n1")
        (output_dir / "README.md").write_text("# hi")
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.prepare_zenodo_export", side_effect=fake_prepare) as mock_prepare,
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.upload_to_zenodo", return_value={"deposition_id": 123}) as mock_upload,
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.release_on_zenodo", return_value=fake_record) as mock_release,
    ):
        with TestClient(app) as client:
            start = client.post("/api/zenodo/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir), "token": "zen_x",
            })
            assert start.status_code == 200
            task_id = start.json()["task_id"]
            assert task_id

            body = _poll_publish(client, task_id)

    assert body == {
        "status": "done", "stage": "done", "doi": "10.5281/zenodo.123", "record_url": "https://zenodo.org/records/123",
        "output_dir": str(fake_output_dir), "error": None,
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


def test_publish_link_mode_passes_through_hfh_repo_id(tmp_path):
    from wildintel_publisher.web.main import app
    fake_output_dir = tmp_path / "zenodo"

    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.prepare_zenodo_export", return_value=fake_output_dir) as mock_prepare,
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.upload_to_zenodo", return_value={}),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.release_on_zenodo", return_value={"doi": "d", "record_url": "u"}),
    ):
        with TestClient(app) as client:
            start = client.post("/api/zenodo/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir), "token": "zen_x",
                "mirror_images": False, "hfh_repo_id": "alice/dataset",
            })
            task_id = start.json()["task_id"]
            _poll_publish(client, task_id)

    assert mock_prepare.call_args.kwargs["self_contained"] is False
    assert mock_prepare.call_args.kwargs["hfh_repo_id"] == "alice/dataset"


def test_publish_output_mode_passthrough_reports_input_dir_as_output(tmp_path):
    from wildintel_publisher.web.main import app
    fake_output_dir = tmp_path / "zenodo"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.prepare_zenodo_export", side_effect=fake_prepare),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.upload_to_zenodo", return_value={"deposition_id": 123}),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.release_on_zenodo", return_value={"doi": "d", "record_url": "u"}),
    ):
        with TestClient(app) as client:
            start = client.post("/api/zenodo/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir), "token": "zen_x",
                "output_mode": "passthrough",
            })
            task_id = start.json()["task_id"]
            body = _poll_publish(client, task_id)

    assert body["output_dir"] == "/tmp/camtrapdp"


def test_publish_reports_error_status_on_failure(tmp_path):
    from wildintel_publisher.web.main import app

    with patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.prepare_zenodo_export", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            start = client.post("/api/zenodo/publish", json={"input_dir": "/tmp/camtrapdp", "token": "zen_x"})
            task_id = start.json()["task_id"]

            body = _poll_publish(client, task_id)

    assert body == {
        "status": "error", "stage": "preparing", "doi": None, "record_url": None, "output_dir": None, "error": "boom",
    }


def test_publish_falls_back_to_saved_token_when_blank(tmp_path):
    from wildintel_publisher.web.main import app

    fake_response = MagicMock(status_code=200)
    with patch("wildintel_publisher.web.services.zenodo_service.httpx.get", return_value=fake_response):
        _client().post("/api/zenodo/test-token", json={"token": "zen_saved"})

    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.prepare_zenodo_export", return_value=None),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.upload_to_zenodo", return_value={}) as mock_upload,
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.release_on_zenodo", return_value={"doi": "d", "record_url": "u"}),
    ):
        with TestClient(app) as client:
            start = client.post("/api/zenodo/publish", json={"input_dir": "/tmp/camtrapdp"})
            task_id = start.json()["task_id"]
            _poll_publish(client, task_id)

    assert mock_upload.call_args.kwargs["token"] == "zen_saved"


def test_depositions_returns_the_results():
    fake_depositions = [{"id": "111", "title": "Camera Trap Survey v1"}, {"id": "222", "title": "(untitled)"}]
    with patch(
        "wildintel_publisher.web.services.zenodo_service.zenodo_service.search_my_depositions", return_value=fake_depositions,
    ) as mock_search:
        response = _client().post("/api/zenodo/depositions", json={
            "environment": "sandbox", "token": "zen_x", "query": "camera trap",
        })
    assert response.status_code == 200
    assert response.json() == fake_depositions
    mock_search.assert_called_once_with("https://sandbox.zenodo.org/api", "zen_x", query="camera trap")


def test_depositions_requires_a_token_when_none_saved():
    response = _client().post("/api/zenodo/depositions", json={"environment": "sandbox"})
    assert response.status_code == 400


def test_depositions_maps_runtime_error_to_400():
    with patch(
        "wildintel_publisher.web.services.zenodo_service.zenodo_service.search_my_depositions",
        side_effect=RuntimeError("List existing Zenodo depositions failed. HTTP status=401."),
    ):
        response = _client().post("/api/zenodo/depositions", json={"environment": "sandbox", "token": "zen_bad"})
    assert response.status_code == 400


PUBLISHED_DEPOSITION = {
    "id": 123, "submitted": True, "state": "done", "doi": "10.5281/zenodo.123",
    "links": {"record_html": "https://sandbox.zenodo.org/records/123"},
}

SYNC_BODY = {
    "environment": "sandbox", "deposition_id": 123, "token": "zen_x",
    "hfh_repo_id": "alice/dataset", "hfh_token": "hf_x",
}


def _fake_hub_download(files: dict[str, str]):
    """hf_hub_download stand-in: writes the repo's `files` into local_dir, or raises EntryNotFoundError."""
    from huggingface_hub.utils import EntryNotFoundError

    def download(*, filename, local_dir, **kwargs):
        if filename not in files:
            raise EntryNotFoundError(filename)
        (Path(local_dir) / filename).write_text(files[filename], encoding="utf-8")
    return download


def test_sync_doi_success():
    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.get_deposition", return_value=PUBLISHED_DEPOSITION),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.sync_doi_to_hfh", return_value="10.5281/zenodo.123") as mock_sync,
        patch("wildintel_publisher.web.services.hfh_service.hf_hub_download", side_effect=_fake_hub_download({"CITATION.cff": "cff"})),
        patch("wildintel_publisher.web.services.hfh_service.upload_file") as mock_upload_file,
    ):
        response = _client().post("/api/zenodo/sync-doi", json=SYNC_BODY)

    assert response.status_code == 200, response.text
    assert response.json() == {"doi": "10.5281/zenodo.123", "repo_url": "https://huggingface.co/datasets/alice/dataset"}
    mock_sync.assert_called_once()
    assert {c.kwargs["path_in_repo"] for c in mock_upload_file.call_args_list} == {"CITATION.cff"}


def test_sync_doi_edits_the_files_in_the_hub_repo_and_keeps_its_other_checksums():
    """No local export folder: the three files come from the Hub repo, the
    changed ones go back, and the repo's checksums keep every other line."""
    repo_files = {
        "CITATION.cff": "old cff", "README.md": "old readme",
        "checksums-sha256.txt": "aaa  data.yaml\nbbb  CITATION.cff\nccc  README.md\n",
    }
    uploaded = {}

    def fake_core_sync(*, zenodo_output_dir, hfh_output_dir):
        (hfh_output_dir / "CITATION.cff").write_text("new cff", encoding="utf-8")
        (hfh_output_dir / "README.md").write_text("new readme", encoding="utf-8")
        return "10.5281/zenodo.123"

    def fake_upload(*, path_or_fileobj, path_in_repo, **kwargs):
        uploaded[path_in_repo] = Path(path_or_fileobj).read_text(encoding="utf-8")

    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.get_deposition", return_value=PUBLISHED_DEPOSITION),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.sync_doi_to_hfh", side_effect=fake_core_sync),
        patch("wildintel_publisher.web.services.hfh_service.hf_hub_download", side_effect=_fake_hub_download(repo_files)),
        patch("wildintel_publisher.web.services.hfh_service.upload_file", side_effect=fake_upload),
    ):
        response = _client().post("/api/zenodo/sync-doi", json=SYNC_BODY)

    assert response.status_code == 200, response.text
    assert uploaded["CITATION.cff"] == "new cff" and uploaded["README.md"] == "new readme"
    from wildintel_publisher.core.services.common import sha256_file
    lines = uploaded["checksums-sha256.txt"].splitlines()
    assert lines[0] == "aaa  data.yaml"
    assert lines[1].endswith("  CITATION.cff") and not lines[1].startswith("bbb")
    assert lines[2].endswith("  README.md") and not lines[2].startswith("ccc")


def test_sync_doi_does_not_invent_checksums_when_the_repo_has_none():
    uploaded = []

    def fake_core_sync(*, zenodo_output_dir, hfh_output_dir):
        (hfh_output_dir / "checksums-sha256.txt").write_text("only two files", encoding="utf-8")  # what write_checksums would leave
        return "10.5281/zenodo.123"

    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.get_deposition", return_value=PUBLISHED_DEPOSITION),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.sync_doi_to_hfh", side_effect=fake_core_sync),
        patch("wildintel_publisher.web.services.hfh_service.hf_hub_download", side_effect=_fake_hub_download({"CITATION.cff": "cff"})),
        patch("wildintel_publisher.web.services.hfh_service.upload_file", side_effect=lambda **kw: uploaded.append(kw["path_in_repo"])),
    ):
        response = _client().post("/api/zenodo/sync-doi", json=SYNC_BODY)

    assert response.status_code == 200, response.text
    assert "checksums-sha256.txt" not in uploaded


def test_sync_doi_fails_when_the_hub_repo_has_no_citation():
    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.get_deposition", return_value=PUBLISHED_DEPOSITION),
        patch("wildintel_publisher.web.services.hfh_service.hf_hub_download", side_effect=_fake_hub_download({})),
        patch("wildintel_publisher.web.services.hfh_service.upload_file") as mock_upload_file,
    ):
        response = _client().post("/api/zenodo/sync-doi", json=SYNC_BODY)

    assert response.status_code == 400
    assert "CITATION.cff" in response.json()["detail"]
    mock_upload_file.assert_not_called()


def test_sync_doi_maps_runtime_error_to_400():
    with (
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.get_deposition", return_value=PUBLISHED_DEPOSITION),
        patch("wildintel_publisher.web.services.hfh_service.hf_hub_download", side_effect=_fake_hub_download({"CITATION.cff": "cff"})),
        patch("wildintel_publisher.web.services.zenodo_service.zenodo_service.sync_doi_to_hfh", side_effect=RuntimeError("not published yet")),
    ):
        response = _client().post("/api/zenodo/sync-doi", json=SYNC_BODY)

    assert response.status_code == 400
    assert "not published yet" in response.json()["detail"]


def test_sync_doi_requires_hfh_token_when_none_saved():
    body = {k: v for k, v in SYNC_BODY.items() if k != "hfh_token"}
    response = _client().post("/api/zenodo/sync-doi", json=body)
    assert response.status_code == 400
