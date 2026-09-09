"""Unit tests for /api/publish/* and services.publish_orchestrator — the
multi-repo "upload everything -> cross-reference DOIs -> lock everything"
flow (see the module's own docstring). Every CLI-level service call
(prepare_X_export/upload_to_X/release_on_X) is mocked out with a
side_effect that writes REAL files into the given build_dir, so
services.doi_populate's own real file-patching logic actually runs against
them — this is the behavior these tests care about, not just that mocks
got called."""
import json
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _write_product_files(output_dir: Path, *, homepage: str | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "datapackage.json").write_text("{}", encoding="utf-8")
    (output_dir / "media.csv").write_text("id\n1", encoding="utf-8")
    metadata = {
        "product_type": "camtrapdp", "title": "T", "description": "D", "version": "1.0",
        "license": {"id": "CC-BY-4.0", "name": "CC-BY-4.0", "url": ""},
        "authors": [{"name": "A", "affiliation": ""}], "publish_history": [], "homepage": homepage,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def _write_citation(output_dir: Path, data: dict) -> None:
    (output_dir / "CITATION.cff").write_text(yaml.safe_dump(data), encoding="utf-8")


def _read_citation(output_dir: Path) -> dict:
    return yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))


def _poll(client: TestClient, task_id: str, *, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/publish/{task_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"Publish-all task {task_id} did not finish within {timeout}s: {body}")


@pytest.fixture(autouse=True)
def _reset_config():
    from dynaconf import loaders
    from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)
    yield


def test_publish_all_single_hfh_repo_tags_and_releases(tmp_path):
    fake_output_dir = tmp_path / "hfh_out"
    calls = []

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        calls.append(("prepare", "hfh"))
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload(output_dir, *, repo_id, token, private, mirror_images):
        calls.append(("upload", "hfh"))
        return f"https://huggingface.co/datasets/{repo_id}"

    def fake_tag(*, repo_id, token, version):
        calls.append(("tag", "hfh"))

    def fake_release(*, repo_id, token, dry_run, verify_only):
        calls.append(("release", "hfh"))
        return True

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", side_effect=fake_tag),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", side_effect=fake_release),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{
                    "repo": "hfh", "output_dir": str(fake_output_dir), "repo_id": "alice/dataset",
                    "token": "hf_x", "mirror_images": True,
                }],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done"
    assert body["repos"]["hfh"]["status"] == "done"
    assert body["repos"]["hfh"]["repo_url"] == "https://huggingface.co/datasets/alice/dataset"
    assert calls == [("prepare", "hfh"), ("upload", "hfh"), ("tag", "hfh"), ("release", "hfh")]
    assert (fake_output_dir / "metadata.json").is_file()  # copy_prepared_output_files ran


def test_publish_all_uploads_every_repo_before_locking_any(tmp_path):
    calls = []

    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, *, repo_id, token, private, mirror_images):
        calls.append("upload-hfh")
        return "https://huggingface.co/datasets/alice/dataset"

    def fake_prepare_zenodo(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_zenodo(output_dir, **kwargs):
        calls.append("upload-zenodo")
        (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")

    def fake_release_zenodo(output_dir, *, token):
        calls.append("release-zenodo")
        return {"doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1"}

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", side_effect=lambda **k: calls.append("tag-hfh")),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", side_effect=lambda **k: calls.append("release-hfh")),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done"
    # both uploads happen before either lock — never interleaved per-repo
    assert calls.index("upload-hfh") < calls.index("release-zenodo")
    assert calls.index("upload-zenodo") < calls.index("tag-hfh")


def test_publish_all_passes_media_dir_only_to_the_first_repo(tmp_path):
    """media_dir (only meaningfully different from input_dir for a local
    Camtrap DP source — see services.camtrapdp_source.
    resolve_local_camtrapdp_source) must reach the FIRST repo's own
    prepare_*_export call, and NOT the second one's: from there on,
    current_input_dir is the previous repo's own build_dir, which already
    has any local media mirrored into it if applicable."""
    captured = {}

    def fake_prepare_hfh(*, input_dir, output_dir, media_dir=None, **kwargs):
        captured["hfh"] = media_dir
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_prepare_zenodo(*, input_dir, output_dir, media_dir=None, **kwargs):
        captured["zenodo"] = media_dir
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", return_value="https://huggingface.co/datasets/alice/dataset"),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface"),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=lambda output_dir, **k: (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", return_value={"doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1"}),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/local-source/working",
                "media_dir": "/tmp/original",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done"
    assert captured["hfh"] == Path("/tmp/original")
    assert captured["zenodo"] is None


def test_publish_all_passes_archive_size_options_through_to_zenodo_and_b2share(tmp_path):
    captured = {}

    def fake_prepare_zenodo(*, input_dir, output_dir, **kwargs):
        captured["zenodo"] = kwargs
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")

    def fake_release_zenodo(output_dir, *, token):
        return {"doi": None, "record_url": "https://zenodo.org/records/1"}

    def fake_prepare_b2share(*, input_dir, output_dir, **kwargs):
        captured["b2share"] = kwargs
        _write_product_files(output_dir)

    def fake_upload_b2share(output_dir, **kwargs):
        (output_dir / "b2share_record.json").write_text(json.dumps({"pid": None}), encoding="utf-8")

    def fake_release_b2share(output_dir, *, token):
        return {"pid": None, "record_url": "https://b2share.eudat.eu/records/1"}

    with (
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
        patch("services.publish_orchestrator.b2share_cli.prepare_b2share_export", side_effect=fake_prepare_b2share),
        patch("services.publish_orchestrator.b2share_cli.upload_to_b2share", side_effect=fake_upload_b2share),
        patch("services.publish_orchestrator.b2share_cli.release_on_b2share", side_effect=fake_release_b2share),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [
                    {
                        "repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x",
                        "environment": "sandbox", "fit_archive_size": False, "max_zip_file": 10, "min_image_edge": 800,
                    },
                    {
                        "repo": "b2share", "output_dir": str(_tmp(tmp_path, "b2share")), "token": "b2_x",
                        "environment": "sandbox", "community_id": "comm-1",
                        # left at defaults — fit_archive_size True, max_zip_file unset
                    },
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done"
    assert captured["zenodo"]["fit_archive_size"] is False
    assert captured["zenodo"]["max_zip_bytes"] == 10 * 1024 ** 3
    assert captured["zenodo"]["min_image_edge"] == 800
    assert captured["b2share"]["fit_archive_size"] is True
    assert captured["b2share"]["max_zip_bytes"] is None
    assert captured["b2share"]["min_image_edge"] == 640


def _tmp(tmp_path, name):
    return tmp_path / name


def test_publish_all_cross_references_dois_and_reuploads_changed_citation(tmp_path):
    upload_counts = {"zenodo": 0, "b2share": 0}

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        upload_counts["zenodo"] += 1
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
            (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": "10.5281/zenodo.1"}), encoding="utf-8")

    def fake_upload_b2share(output_dir, **kwargs):
        upload_counts["b2share"] += 1
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1", "url": "https://doi.org/10.1234/b2share.1"})
            (output_dir / "b2share_record.json").write_text(json.dumps({"pid": "10.1234/b2share.1", "pid_kind": "doi"}), encoding="utf-8")

    def fake_release_zenodo(output_dir, *, token):
        return {"doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1"}

    def fake_release_b2share(output_dir, *, token):
        return {"pid": "10.1234/b2share.1", "pid_kind": "doi", "record_url": "https://b2share.eudat.eu/records/1"}

    with (
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
        patch("services.publish_orchestrator.b2share_cli.prepare_b2share_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.b2share_cli.upload_to_b2share", side_effect=fake_upload_b2share),
        patch("services.publish_orchestrator.b2share_cli.release_on_b2share", side_effect=fake_release_b2share),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                    {"repo": "b2share", "output_dir": str(_tmp(tmp_path, "b2share")), "token": "b2_x", "community_id": "uuid-1", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done"
    assert body["repos"]["zenodo"]["doi"] == "10.5281/zenodo.1"
    assert body["repos"]["b2share"]["pid"] == "10.1234/b2share.1"
    # each upload_to_X ran twice: once in the upload phase, once again to
    # push the citation the populate phase patched in.
    assert upload_counts == {"zenodo": 2, "b2share": 2}


def test_publish_all_gives_hfh_the_explicitly_chosen_primary_doi(tmp_path):
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    def fake_prepare_repo(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})
            (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": "10.5281/zenodo.1"}), encoding="utf-8")

    def fake_upload_b2share(output_dir, **kwargs):
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1"})
            (output_dir / "b2share_record.json").write_text(json.dumps({"pid": "10.1234/b2share.1", "pid_kind": "doi"}), encoding="utf-8")

    hfh_citations_seen = []

    def spying_upload_hfh(output_dir, **kwargs):
        # Captures CITATION.cff's content at each call — the build_dir
        # itself is deleted once the whole task finishes, so it can't be
        # read back afterwards; this call happens once in the upload phase
        # and again in the populate phase's re-upload (if content changed).
        hfh_citations_seen.append(_read_citation(output_dir))
        return fake_upload_hfh(output_dir, **kwargs)

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=spying_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_repo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", return_value={"doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1"}),
        patch("services.publish_orchestrator.b2share_cli.prepare_b2share_export", side_effect=fake_prepare_repo),
        patch("services.publish_orchestrator.b2share_cli.upload_to_b2share", side_effect=fake_upload_b2share),
        patch("services.publish_orchestrator.b2share_cli.release_on_b2share", return_value={"pid": "10.1234/b2share.1", "pid_kind": "doi", "record_url": "https://b2share.eudat.eu/records/1"}),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "primary_doi_source": "b2share",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                    {"repo": "b2share", "output_dir": str(_tmp(tmp_path, "b2share")), "token": "b2_x", "community_id": "uuid-1", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert len(hfh_citations_seen) == 2  # upload phase, then populate's re-upload
    hfh_citation = hfh_citations_seen[-1]
    assert hfh_citation["doi"] == "10.1234/b2share.1"
    assert hfh_citation["identifiers"] == [
        {"type": "doi", "value": "https://doi.org/10.5281/zenodo.1", "description": "Zenodo DOI"},
    ]


def test_publish_all_stops_the_sequence_on_the_first_failure(tmp_path):
    def failing_prepare(*, input_dir, output_dir, **kwargs):
        raise RuntimeError("boom")

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=failing_prepare),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export") as mock_zenodo_prepare,
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "error"
    assert "boom" in body["error"]
    mock_zenodo_prepare.assert_not_called()


def test_publish_all_dry_run_never_touches_a_real_repo_but_still_populates_dois(tmp_path):
    """dry_run=True: no token/repo_id/community_id required, no upload_to_X/
    release_on_X/save_config call ever happens, yet Zenodo/B2SHARE still end
    up with a (fake) DOI/PID and HFH's CITATION.cff still gets cross-
    referenced with it — proving populate() ran for real against the
    simulated records."""

    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_prepare_repo(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    never_called = [
        "services.publish_orchestrator.hfh_cli.upload_to_huggingface",
        "services.publish_orchestrator.hfh_cli.tag_release_on_huggingface",
        "services.publish_orchestrator.hfh_cli.release_on_huggingface",
        "services.publish_orchestrator.zenodo_cli.upload_to_zenodo",
        "services.publish_orchestrator.zenodo_cli.release_on_zenodo",
        "services.publish_orchestrator.b2share_cli.upload_to_b2share",
        "services.publish_orchestrator.b2share_cli.release_on_b2share",
        "services.hfh_service.save_config", "services.zenodo_service.save_config", "services.b2share_service.save_config",
    ]
    with ExitStack() as stack:
        stack.enter_context(patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh))
        stack.enter_context(patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_repo))
        stack.enter_context(patch("services.publish_orchestrator.b2share_cli.prepare_b2share_export", side_effect=fake_prepare_repo))
        mocks = [stack.enter_context(patch(target)) for target in never_called]

        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "dry_run": True,
                "primary_doi_source": "zenodo",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh"))},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo"))},
                    {"repo": "b2share", "output_dir": str(_tmp(tmp_path, "b2share"))},
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    for mock in mocks:
        mock.assert_not_called()

    assert body["repos"]["hfh"]["repo_url"].startswith("https://huggingface.co/datasets/dry-run/")
    assert body["repos"]["zenodo"]["doi"].startswith("10.0000/dry-run/zenodo.")
    assert body["repos"]["b2share"]["pid"].startswith("10.0000/dry-run/b2share.")

    # HFH never has a DOI of its own — populate() made Zenodo's the primary
    # one (per primary_doi_source above) and B2SHARE's an alternate.
    hfh_citation = _read_citation(Path(body["repos"]["hfh"]["output_dir"]))
    assert hfh_citation["doi"] == body["repos"]["zenodo"]["doi"]
    assert hfh_citation["identifiers"] == [
        {"type": "doi", "value": f"https://doi.org/{body['repos']['b2share']['pid']}", "description": "B2SHARE (EUDAT) DOI"},
    ]


def test_publish_all_requires_at_least_one_repo():
    with _client() as client:
        response = client.post("/api/publish/start", json={"input_dir": "/tmp/camtrapdp", "repos": []})
    assert response.status_code == 400


def test_publish_all_requires_hfh_repo_id():
    with _client() as client:
        response = client.post("/api/publish/start", json={
            "input_dir": "/tmp/camtrapdp",
            "repos": [{"repo": "hfh", "token": "hf_x"}],
        })
    assert response.status_code == 400


def test_publish_all_requires_b2share_community_id():
    with _client() as client:
        response = client.post("/api/publish/start", json={
            "input_dir": "/tmp/camtrapdp",
            "repos": [{"repo": "b2share", "token": "b2_x", "environment": "sandbox"}],
        })
    assert response.status_code == 400


def test_publish_all_requires_gbif_archive_url():
    with _client() as client:
        response = client.post("/api/publish/start", json={
            "input_dir": "/tmp/camtrapdp",
            "repos": [{
                "repo": "gbif", "publishing_organization_key": "org-1", "installation_key": "inst-1",
                "username": "alice", "password": "s3cret",
            }],
        })
    assert response.status_code == 400


def test_publish_all_requires_gbif_organization_and_installation_keys():
    with _client() as client:
        response = client.post("/api/publish/start", json={
            "input_dir": "/tmp/camtrapdp",
            "repos": [{
                "repo": "gbif", "archive_url": "https://example.org/datapackage.json",
                "username": "alice", "password": "s3cret",
            }],
        })
    assert response.status_code == 400


def test_publish_all_requires_gbif_credentials():
    with _client() as client:
        response = client.post("/api/publish/start", json={
            "input_dir": "/tmp/camtrapdp",
            "repos": [{
                "repo": "gbif", "archive_url": "https://example.org/datapackage.json",
                "publishing_organization_key": "org-1", "installation_key": "inst-1",
            }],
        })
    assert response.status_code == 400


def test_publish_all_requires_hfh_before_gbif_when_both_selected():
    """The wizard's own toggleRepo already forces this order client-side —
    enforced again here so a request bypassing the wizard UI can't silently
    end up with a stale/wrong GBIF registration (see publish_orchestrator's
    own input_dirs chaining, which only picks up Hugging Face Hub's
    mirror-mode metadata.json updates if it already had its turn)."""
    with _client() as client:
        response = client.post("/api/publish/start", json={
            "input_dir": "/tmp/camtrapdp",
            "repos": [
                {
                    "repo": "gbif", "archive_url": "https://example.org/camtrapdp-remote.zip",
                    "publishing_organization_key": "org-1", "installation_key": "inst-1",
                    "username": "alice", "password": "s3cret",
                },
                {"repo": "hfh", "repo_id": "alice/dataset", "token": "hf_x"},
            ],
        })
    assert response.status_code == 400
    assert "before GBIF" in response.json()["detail"]


def test_publish_all_single_gbif_repo_registers_dataset(tmp_path):
    """GBIF never prepares/uploads files of its own (see the module's own
    docstring) — its one real network call happens directly in the lock
    phase, reading title/description/license straight from the task's
    ORIGINAL input_dir (its own build_dir is never populated)."""
    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with patch(
        "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
        return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/abc-123"},
    ) as mock_register:
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [{
                    "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                    "archive_url": "https://example.org/datapackage.json",
                    "publishing_organization_key": "org-1", "installation_key": "inst-1",
                    "username": "alice", "password": "s3cret", "environment": "sandbox",
                }],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert body["repos"]["gbif"]["status"] == "done"
    assert body["repos"]["gbif"]["repo_url"] == "https://registry.gbif-test.org/dataset/abc-123"
    mock_register.assert_called_once()
    assert mock_register.call_args.args[0] == "https://example.org/datapackage.json"
    assert mock_register.call_args.args[1] == _tmp(tmp_path, "gbif")
    assert mock_register.call_args.kwargs["title"] == "T"
    assert mock_register.call_args.kwargs["publishing_organization_key"] == "org-1"
    assert body["repos"]["gbif"]["doi"] is None  # most organizations don't get one automatically


def test_publish_all_gbif_surfaces_a_doi_when_gbif_returns_one(tmp_path):
    """Some organizations have their own DataCite arrangement configured
    with GBIF, which makes it auto-mint a DOI on registration (see
    gbif.register_gbif_dataset) — when present, it must reach the frontend
    so it can offer to sync it into HFH's own CITATION.cff."""
    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with patch(
        "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
        return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/abc-123", "doi": "10.21373/eet8jz"},
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [{
                    "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                    "archive_url": "https://example.org/datapackage.json",
                    "publishing_organization_key": "org-1", "installation_key": "inst-1",
                    "username": "alice", "password": "s3cret", "environment": "sandbox",
                }],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["repos"]["gbif"]["doi"] == "10.21373/eet8jz"
    # No HFH in this run to auto-sync into — the manual "Sync DOI" section
    # is the only way, same as before this field existed.
    assert body["repos"]["gbif"]["doi_synced_to_hfh"] is None


def test_publish_all_hfh_then_gbif_auto_syncs_doi_into_hfh_citation(tmp_path):
    """Unlike Zenodo/B2SHARE (cross-referenced automatically by the populate
    phase, before HFH ever gets tagged), GBIF only learns its own DOI during
    its own lock call, which always runs after HFH's — so the orchestrator
    syncs it in as one extra best-effort step once every repo's lock phase
    has run (see publish_orchestrator's own docstring)."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)
    hfh_output_dir = _tmp(tmp_path, "hfh")
    gbif_output_dir = _tmp(tmp_path, "gbif")

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch(
            "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
            return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/xyz", "doi": "10.21373/eet8jz"},
        ),
        patch(
            "services.publish_orchestrator.gbif_service.sync_doi_to_hfh",
            return_value={"doi": "10.21373/eet8jz", "repo_url": "https://huggingface.co/datasets/alice/dataset"},
        ) as mock_sync,
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [
                    {"repo": "hfh", "output_dir": str(hfh_output_dir), "repo_id": "alice/dataset", "token": "hf_x"},
                    {
                        "repo": "gbif", "output_dir": str(gbif_output_dir),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "username": "alice", "password": "s3cret", "environment": "sandbox",
                    },
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert body["repos"]["gbif"]["doi"] == "10.21373/eet8jz"
    assert body["repos"]["gbif"]["doi_synced_to_hfh"] is True
    mock_sync.assert_called_once_with(
        gbif_output_dir=gbif_output_dir, hfh_output_dir=hfh_output_dir,
        hfh_repo_id="alice/dataset", hfh_token="hf_x",
    )


def test_publish_all_hfh_then_gbif_registers_the_homepage_hfh_just_set(tmp_path):
    """GBIF's own build_dir is never populated (see _upload_one), so its
    _lock_one reads metadata.json for title/description/homepage from this
    repo's own input_dir in the chain — NOT the publish task's original
    input_dir. If HFH just published in mirror mode ahead of it, HFH's own
    upload_to_huggingface already updated metadata.json's "homepage" to its
    real dataset URL (see product.write_homepage) — GBIF's registration must
    see that update, not the stale/missing value the original input_dir
    still has."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        # Simulates upload_to_huggingface's own product.write_homepage call.
        meta_path = output_dir / "metadata.json"
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data["homepage"] = "https://huggingface.co/datasets/alice/dataset"
        meta_path.write_text(json.dumps(data), encoding="utf-8")
        return "https://huggingface.co/datasets/alice/dataset"

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)  # homepage=None here — the ORIGINAL, pre-HFH state
    hfh_output_dir = _tmp(tmp_path, "hfh")
    gbif_output_dir = _tmp(tmp_path, "gbif")

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch(
            "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
            return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/xyz", "doi": None},
        ) as mock_register,
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [
                    {"repo": "hfh", "output_dir": str(hfh_output_dir), "repo_id": "alice/dataset", "token": "hf_x"},
                    {
                        "repo": "gbif", "output_dir": str(gbif_output_dir),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "username": "alice", "password": "s3cret", "environment": "sandbox",
                    },
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert mock_register.call_args.kwargs["homepage"] == "https://huggingface.co/datasets/alice/dataset"


def test_publish_all_hfh_then_gbif_auto_sync_failure_does_not_fail_the_whole_run(tmp_path):
    """Best-effort: if the auto-sync itself errors (e.g. the HFH upload
    fails), the overall publish still finishes 'done' — the wizard's manual
    'Sync DOI' section stays available for the user to retry by hand."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch(
            "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
            return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/xyz", "doi": "10.21373/eet8jz"},
        ),
        patch(
            "services.publish_orchestrator.gbif_service.sync_doi_to_hfh",
            side_effect=RuntimeError("Hugging Face Hub upload failed"),
        ),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {
                        "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "username": "alice", "password": "s3cret", "environment": "sandbox",
                    },
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert body["repos"]["gbif"]["doi_synced_to_hfh"] is False


def test_publish_all_gbif_dry_run_fakes_a_dataset_url_without_network(tmp_path):
    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with patch("services.publish_orchestrator.gbif_cli.register_gbif_dataset") as mock_register:
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir), "dry_run": True,
                "repos": [{"repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")), "environment": "sandbox"}],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    mock_register.assert_not_called()
    assert body["repos"]["gbif"]["repo_url"].startswith("https://registry.gbif-test.org/dataset/dry-run-")


def test_publish_all_hfh_then_gbif_chains_without_breaking_doi_populate(tmp_path):
    """GBIF has no CITATION.cff of its own — this proves doi_populate.populate()
    (which only knows about hfh/zenodo/b2share) never even sees it, and that
    chaining past a GBIF step doesn't try to extract core files out of its
    (never populated) build_dir."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch(
            "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
            return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/xyz"},
        ) as mock_register,
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {
                        "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/datapackage.json",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "username": "alice", "password": "s3cret", "environment": "sandbox",
                    },
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert body["repos"]["hfh"]["repo_url"] == "https://huggingface.co/datasets/alice/dataset"
    assert body["repos"]["gbif"]["repo_url"] == "https://registry.gbif-test.org/dataset/xyz"
    mock_register.assert_called_once()


# ── resumable sessions ───────────────────────────────────────────────────────

def test_publish_all_success_deletes_the_session_dir(tmp_path):
    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", return_value="https://huggingface.co/datasets/alice/dataset"),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface"),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            task_id = start.json()["task_id"]
            body = _poll(client, task_id)

    assert body["status"] == "done"
    from wildintel_publisher.config import get_sessions_dir
    assert not (get_sessions_dir() / task_id).exists()


def test_publish_all_error_persists_a_secret_free_session_manifest(tmp_path):
    """The whole point of the session persisted on disk (see
    publish_orchestrator's own docstring) is to make resume_publish_all_task
    possible — but it must never carry the credentials the request was
    started with; resuming always requires the user to re-enter them."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    def failing_prepare_zenodo(*, input_dir, output_dir, **kwargs):
        raise RuntimeError("boom")

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface"),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=failing_prepare_zenodo),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_secret"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_secret", "environment": "sandbox"},
                ],
            })
            task_id = start.json()["task_id"]
            body = _poll(client, task_id)

    assert body["status"] == "error"

    from wildintel_publisher.config import get_sessions_dir
    session_dir = get_sessions_dir() / task_id
    assert session_dir.is_dir()  # kept on disk — never deleted for a failed task
    assert (session_dir / "hfh-build").is_dir()  # the already-finished repo's own build_dir survives too

    manifest = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    assert manifest["repo_status"]["hfh"]["stage"] == "uploaded"
    assert manifest["repo_status"]["zenodo"]["status"] == "error"
    for repo_cfg in manifest["repos"]:
        assert "token" not in repo_cfg
    manifest_text = json.dumps(manifest)
    assert "hf_secret" not in manifest_text
    assert "zen_secret" not in manifest_text


def test_publish_all_sessions_list_finds_the_interrupted_task(tmp_path):
    def failing_prepare(*, input_dir, output_dir, **kwargs):
        raise RuntimeError("boom")

    with patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=failing_prepare):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            task_id = start.json()["task_id"]
            _poll(client, task_id)

            sessions_response = client.get("/api/publish/sessions")
            assert sessions_response.status_code == 200
            sessions = sessions_response.json()

    assert isinstance(sessions, list)
    assert task_id in [s["task_id"] for s in sessions]


def test_discard_session_removes_it_from_disk(tmp_path):
    def failing_prepare(*, input_dir, output_dir, **kwargs):
        raise RuntimeError("boom")

    from wildintel_publisher.config import get_sessions_dir

    with patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=failing_prepare):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            task_id = start.json()["task_id"]
            _poll(client, task_id)
            assert (get_sessions_dir() / task_id).exists()

            discard = client.delete(f"/api/publish/sessions/{task_id}")
            assert discard.status_code == 200, discard.text

    assert not (get_sessions_dir() / task_id).exists()


def test_resume_publish_all_task_rejects_a_different_repo_list(tmp_path):
    def failing_prepare(*, input_dir, output_dir, **kwargs):
        raise RuntimeError("boom")

    with patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=failing_prepare):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            task_id = start.json()["task_id"]
            _poll(client, task_id)

            resume = client.post(f"/api/publish/sessions/{task_id}/resume", json={
                "repos": [{"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"}],
            })

    assert resume.status_code == 400


def test_resume_publish_all_task_skips_the_already_done_repo_and_completes(tmp_path):
    """A repo whose stage was already "done" before the interruption (here:
    hfh, which finished before zenodo's own prepare blew up) must never be
    re-prepared/re-uploaded on resume — its build_dir survives untouched
    under the session dir, and only the not-yet-finished repo actually
    re-runs."""
    calls: list[str] = []

    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        calls.append("prepare-hfh")
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        calls.append("upload-hfh")
        return "https://huggingface.co/datasets/alice/dataset"

    zenodo_attempts = {"count": 0}

    def fake_prepare_zenodo(*, input_dir, output_dir, **kwargs):
        zenodo_attempts["count"] += 1
        calls.append("prepare-zenodo")
        if zenodo_attempts["count"] == 1:
            raise RuntimeError("network blip")
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        calls.append("upload-zenodo")
        (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")

    def fake_release_zenodo(output_dir, *, token):
        calls.append("release-zenodo")
        return {"doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1"}

    hfh_output_dir = _tmp(tmp_path, "hfh")
    zenodo_output_dir = _tmp(tmp_path, "zenodo")
    repos = [
        {"repo": "hfh", "output_dir": str(hfh_output_dir), "repo_id": "alice/dataset", "token": "hf_x"},
        {"repo": "zenodo", "output_dir": str(zenodo_output_dir), "token": "zen_x", "environment": "sandbox"},
    ]

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", side_effect=lambda **k: calls.append("tag-hfh")),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", side_effect=lambda **k: calls.append("release-hfh")),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={"input_dir": "/tmp/camtrapdp", "repos": repos})
            task_id = start.json()["task_id"]
            body = _poll(client, task_id)
            assert body["status"] == "error", body
            assert body["repos"]["hfh"]["stage"] == "uploaded"
            assert body["repos"]["zenodo"]["status"] == "error"

            resume = client.post(f"/api/publish/sessions/{task_id}/resume", json={"repos": repos})
            assert resume.status_code == 200, resume.text
            resumed_task_id = resume.json()["task_id"]
            assert resumed_task_id == task_id  # resume continues the SAME task, not a new one

            resumed_body = _poll(client, resumed_task_id)

    assert resumed_body["status"] == "done", resumed_body
    assert resumed_body["repos"]["zenodo"]["doi"] == "10.5281/zenodo.1"
    # hfh, already "done" before the interruption, is never re-run.
    assert calls.count("prepare-hfh") == 1
    assert calls.count("upload-hfh") == 1
    # zenodo re-runs from scratch: the failed attempt, then the resumed one.
    assert calls.count("prepare-zenodo") == 2

    from wildintel_publisher.config import get_sessions_dir
    assert not (get_sessions_dir() / task_id).exists()  # cleaned up on the eventual success
