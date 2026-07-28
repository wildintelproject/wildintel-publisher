"""Unit tests for the /api/hfh/* endpoints — hfh_service's HuggingFace Hub
calls are mocked out (no real network / no live HF account needed), but
settings.toml reads/writes go through the real wildintel_publisher.config
machinery, isolated to a throwaway HOME by conftest.py."""
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from huggingface_hub.errors import HfHubHTTPError


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _hf_hub_http_error(status_code: int) -> HfHubHTTPError:
    fake_response = httpx.Response(
        status_code=status_code, request=httpx.Request("GET", "https://huggingface.co/api/whoami-v2"),
    )
    return HfHubHTTPError(f"{status_code} Client Error", response=fake_response)


def _write_fake_metadata_json(output_dir: Path) -> None:
    """Real prepare_hfh_export copies metadata.json into its output_dir (see
    product.copy_metadata_json) — these tests mock prepare_hfh_export out
    entirely, so they need to replicate that side effect themselves for
    copy_prepared_output_files (called right after upload/release succeed)
    to find it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(
        '{"product_type": "camtrapdp", "title": "T", "description": "D", '
        '"license": {"id": "CC-BY-4.0", "name": "CC-BY-4.0", "url": ""}, '
        '"authors": [{"name": "A", "affiliation": ""}], "publish_history": []}',
        encoding="utf-8",
    )


def _poll_publish(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    """Polls GET /api/hfh/publish/{task_id} until it's no longer 'running'.

    Must be called with `client` opened as a context manager, same reason as
    test_trapper.py's own _poll_download helper."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/hfh/publish/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Publish task {task_id} did not finish within {timeout}s: {body}")


@pytest.fixture(autouse=True)
def _reset_hfh_config():
    """Resets settings.toml to fresh defaults before each test — several
    tests here save a real HFH token/repo_id, and without this they'd leak
    into whichever test runs next."""
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    yield


def test_get_config_defaults_to_none_and_no_token_when_unset():
    response = _client().get("/api/hfh/config")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] is None
    assert body["has_token"] is False


def test_test_token_success_saves_only_the_username_and_the_token():
    """Only the username/org part of repo_id gets remembered — the dataset
    name itself is per-product (see product.missing_required_fields's
    title, which the wizard now slugifies to prefill the repository name
    field instead), so it would be wrong to carry it over to the next
    product published through the wizard."""
    with patch("services.hfh_service.whoami", return_value={"name": "alice"}):
        response = _client().post("/api/hfh/test-token", json={"repo_id": "alice/dataset", "token": "hf_x"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "username": "alice", "version_conflict": False}

    config_response = _client().get("/api/hfh/config")
    body = config_response.json()
    assert body["username"] == "alice"
    assert body["has_token"] is True


def test_test_token_warns_when_the_version_was_already_published(tmp_path):
    """A heads-up before the user even starts publishing — the real
    enforcement happens in hfh.upload_to_huggingface's own tag_exists
    check, this is just so they can notice and bump the version first."""
    with patch("services.hfh_service.whoami", return_value={"name": "alice"}), \
         patch("wildintel_publisher.services.hfh.tag_exists", return_value=True) as mock_tag_exists:
        response = _client().post("/api/hfh/test-token", json={
            "repo_id": "alice/dataset", "token": "hf_x", "version": "1.0",
        })
    assert response.status_code == 200
    assert response.json() == {"ok": True, "username": "alice", "version_conflict": True}
    mock_tag_exists.assert_called_once_with("alice/dataset", "1.0", "hf_x")


def test_test_token_reports_no_conflict_when_the_version_is_new():
    with patch("services.hfh_service.whoami", return_value={"name": "alice"}), \
         patch("wildintel_publisher.services.hfh.tag_exists", return_value=False):
        response = _client().post("/api/hfh/test-token", json={
            "repo_id": "alice/dataset", "token": "hf_x", "version": "2.0",
        })
    assert response.status_code == 200
    assert response.json()["version_conflict"] is False


def test_test_token_skips_the_version_check_when_version_is_not_given():
    with patch("services.hfh_service.whoami", return_value={"name": "alice"}), \
         patch("wildintel_publisher.services.hfh.tag_exists") as mock_tag_exists:
        response = _client().post("/api/hfh/test-token", json={"repo_id": "alice/dataset", "token": "hf_x"})
    assert response.status_code == 200
    assert response.json()["version_conflict"] is False
    mock_tag_exists.assert_not_called()


def test_test_token_reports_400_when_nothing_saved():
    response = _client().post("/api/hfh/test-token", json={})
    assert response.status_code == 400


def test_test_token_maps_invalid_token_to_401():
    with patch("services.hfh_service.whoami", side_effect=_hf_hub_http_error(401)):
        response = _client().post("/api/hfh/test-token", json={"token": "hf_bad"})
    assert response.status_code == 401


def test_test_token_maps_unexpected_hf_hub_error_to_502():
    """A non-auth HTTP error from Hugging Face Hub (e.g. a 500 during an
    outage) must not be reported as 'incorrect or expired token' — it's a
    different problem the user can't fix by retyping the token."""
    with patch("services.hfh_service.whoami", side_effect=_hf_hub_http_error(500)):
        response = _client().post("/api/hfh/test-token", json={"token": "hf_x"})
    assert response.status_code == 502


def test_test_token_maps_network_error_to_502():
    """A connection failure (no internet, DNS issue, etc.) must not be
    reported as 'incorrect or expired token' either."""
    with patch("services.hfh_service.whoami", side_effect=RuntimeError("connection refused")):
        response = _client().post("/api/hfh/test-token", json={"token": "hf_x"})
    assert response.status_code == 502


def test_publish_requires_repo_id():
    with patch("services.hfh_service.whoami", return_value={"name": "alice"}):
        _client().post("/api/hfh/test-token", json={"token": "hf_x"})

    response = _client().post("/api/hfh/publish", json={"input_dir": "/tmp/camtrapdp"})
    assert response.status_code == 400


def test_publish_start_and_poll_until_done(tmp_path):
    """Default output_mode='prepared': prepare/upload/release must run
    against a throwaway temporary directory, and the user's configured
    output_dir must end up with the core Camtrap DP files (with
    prepare/upload's modifications applied) plus README.md — kept, along
    with CITATION.cff/checksums-sha256.txt (not written by this test's fake
    prepare, so absent from the assertion below), so a later Sync DOI/PID
    can patch its own "## Citation" section (see hfh_service.
    KEPT_EXTRA_FILES) — LICENSE/images/the local zip are the only real
    exclusions, which only ever exist in the temporary directory."""
    from main import app
    fake_output_dir = tmp_path / "hfh"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        (output_dir / "datapackage.json").write_text("{}")
        (output_dir / "media.csv").write_text("id\n1")
        (output_dir / "README.md").write_text("# hi")
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.hfh_service.hfh_service.prepare_hfh_export", side_effect=fake_prepare) as mock_prepare,
        patch("services.hfh_service.hfh_service.upload_to_huggingface", return_value="https://huggingface.co/datasets/alice/dataset") as mock_upload,
        patch("services.hfh_service.hfh_service.tag_release_on_huggingface", return_value=None) as mock_tag,
        patch("services.hfh_service.hfh_service.release_on_huggingface", return_value=True) as mock_release,
    ):
        with TestClient(app) as client:
            start = client.post("/api/hfh/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "repo_id": "alice/dataset", "token": "hf_x",
            })
            assert start.status_code == 200
            task_id = start.json()["task_id"]
            assert task_id

            body = _poll_publish(client, task_id)

    assert body == {
        "status": "done", "stage": "done", "repo_url": "https://huggingface.co/datasets/alice/dataset",
        "output_dir": str(fake_output_dir), "error": None,
    }
    assert {p.name for p in fake_output_dir.iterdir()} == {"datapackage.json", "media.csv", "metadata.json", "README.md"}
    mock_prepare.assert_called_once()
    mock_upload.assert_called_once()
    mock_tag.assert_called_once()
    assert mock_tag.call_args.kwargs["version"] == "1.0"  # from build_dir's own (fake) metadata.json
    mock_release.assert_called_once()
    assert mock_prepare.call_args.kwargs["input_dir"] == Path("/tmp/camtrapdp")
    build_dir = mock_prepare.call_args.kwargs["output_dir"]
    assert build_dir != fake_output_dir  # prepare must never touch the real output_dir directly
    assert not build_dir.exists()  # cleaned up once the publish finished
    assert mock_prepare.call_args.kwargs["mirror_images"] is True  # default: mirror
    assert mock_upload.call_args.kwargs["mirror_images"] is True


def test_publish_passes_through_link_mode(tmp_path):
    from main import app
    fake_output_dir = tmp_path / "hfh"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.hfh_service.hfh_service.prepare_hfh_export", side_effect=fake_prepare) as mock_prepare,
        patch("services.hfh_service.hfh_service.upload_to_huggingface", return_value="url") as mock_upload,
        patch("services.hfh_service.hfh_service.tag_release_on_huggingface", return_value=None),
        patch("services.hfh_service.hfh_service.release_on_huggingface", return_value=True),
    ):
        with TestClient(app) as client:
            start = client.post("/api/hfh/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "repo_id": "alice/dataset", "token": "hf_x", "mirror_images": False,
            })
            task_id = start.json()["task_id"]
            _poll_publish(client, task_id)

    assert mock_prepare.call_args.kwargs["mirror_images"] is False
    assert mock_upload.call_args.kwargs["mirror_images"] is False


def test_publish_output_mode_passthrough_reports_input_dir_as_output(tmp_path):
    from main import app
    fake_output_dir = tmp_path / "hfh"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.hfh_service.hfh_service.prepare_hfh_export", side_effect=fake_prepare),
        patch("services.hfh_service.hfh_service.upload_to_huggingface", return_value="url") as mock_upload,
        patch("services.hfh_service.hfh_service.tag_release_on_huggingface", return_value=None),
        patch("services.hfh_service.hfh_service.release_on_huggingface", return_value=True),
    ):
        with TestClient(app) as client:
            start = client.post("/api/hfh/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "repo_id": "alice/dataset", "token": "hf_x", "output_mode": "passthrough",
            })
            task_id = start.json()["task_id"]
            body = _poll_publish(client, task_id)

    assert body["output_dir"] == "/tmp/camtrapdp"
    mock_upload.assert_called_once()


def test_publish_output_mode_downloaded_fetches_from_the_repo(tmp_path):
    from main import app
    fake_output_dir = tmp_path / "hfh"

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with (
        patch("services.hfh_service.hfh_service.prepare_hfh_export", side_effect=fake_prepare),
        patch("services.hfh_service.hfh_service.upload_to_huggingface", return_value="url"),
        patch("services.hfh_service.hfh_service.tag_release_on_huggingface", return_value=None),
        patch("services.hfh_service.hfh_service.release_on_huggingface", return_value=True),
        patch("services.hfh_service.snapshot_download") as mock_snapshot_download,
    ):
        with TestClient(app) as client:
            start = client.post("/api/hfh/publish", json={
                "input_dir": "/tmp/camtrapdp", "output_dir": str(fake_output_dir),
                "repo_id": "alice/dataset", "token": "hf_x", "output_mode": "downloaded",
            })
            task_id = start.json()["task_id"]
            body = _poll_publish(client, task_id)

    expected_download_dir = str(fake_output_dir.parent / f"{fake_output_dir.name}-downloaded")
    assert body["output_dir"] == expected_download_dir
    mock_snapshot_download.assert_called_once_with(
        repo_id="alice/dataset", repo_type="dataset", token="hf_x", local_dir=expected_download_dir,
    )


def test_publish_reports_error_status_on_failure(tmp_path):
    from main import app

    with patch("services.hfh_service.hfh_service.prepare_hfh_export", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            start = client.post("/api/hfh/publish", json={
                "input_dir": "/tmp/camtrapdp", "repo_id": "alice/dataset", "token": "hf_x",
            })
            task_id = start.json()["task_id"]

            body = _poll_publish(client, task_id)

    assert body == {"status": "error", "stage": "preparing", "repo_url": None, "output_dir": None, "error": "boom"}


def test_publish_falls_back_to_saved_token_when_blank(tmp_path):
    from main import app

    with patch("services.hfh_service.whoami", return_value={"name": "alice"}):
        _client().post("/api/hfh/test-token", json={"token": "hf_saved"})

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_fake_metadata_json(output_dir)
        return output_dir

    with patch("services.hfh_service.hfh_service.prepare_hfh_export", side_effect=fake_prepare), \
         patch("services.hfh_service.hfh_service.upload_to_huggingface", return_value="url") as mock_upload, \
         patch("services.hfh_service.hfh_service.tag_release_on_huggingface", return_value=None), \
         patch("services.hfh_service.hfh_service.release_on_huggingface", return_value=True):
        with TestClient(app) as client:
            start = client.post("/api/hfh/publish", json={"input_dir": "/tmp/camtrapdp", "repo_id": "alice/dataset"})
            task_id = start.json()["task_id"]
            _poll_publish(client, task_id)

    assert mock_upload.call_args.kwargs["token"] == "hf_saved"


def test_copy_prepared_output_files_keeps_readme_alongside_citation_and_checksums(tmp_path):
    """Regression test: KEPT_EXTRA_FILES used to only list CITATION.cff and
    checksums-sha256.txt — README.md was dropped, so a later Sync DOI/PID
    could patch its own "## Citation" section (see common.
    patch_readme_citation_url) on a local copy, but there was nothing to
    re-upload: the file simply didn't exist in the user's configured
    output_dir, so it silently never changed on Hugging Face Hub either."""
    from services.hfh_service import copy_prepared_output_files

    build_dir = tmp_path / "build"
    _write_fake_metadata_json(build_dir)
    (build_dir / "datapackage.json").write_text("{}", encoding="utf-8")
    (build_dir / "CITATION.cff").write_text("cff", encoding="utf-8")
    (build_dir / "checksums-sha256.txt").write_text("sums", encoding="utf-8")
    (build_dir / "README.md").write_text("# hi", encoding="utf-8")
    (build_dir / "LICENSE").write_text("license", encoding="utf-8")

    target_dir = tmp_path / "output"
    copy_prepared_output_files(output_dir=build_dir, target_dir=target_dir)

    names = {p.name for p in target_dir.iterdir()}
    assert {"CITATION.cff", "checksums-sha256.txt", "README.md"} <= names
    assert "LICENSE" not in names
