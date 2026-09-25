"""Unit tests for /api/publish/* and services.publish_orchestrator — the
multi-repo "upload everything -> cross-reference DOIs -> lock everything"
flow (see the module's own docstring). Every CLI-level service call
(prepare_X_export/upload_to_X/release_on_X) is mocked out with a
side_effect that writes REAL files into the given build_dir, so
services.doi_populate's own real file-patching logic actually runs against
them — this is the behavior these tests care about, not just that mocks
got called."""
import asyncio
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


def _write_checksums(output_dir: Path, *filenames: str) -> None:
    """doi_populate.populate()/gbif_service.sync_doi_to_hfh now UPDATE
    (never recreate from scratch) an already-published checksums-sha256.txt
    — see common.update_checksums_entries, used precisely because
    output_dir might not have the rest of the export's own files
    physically present locally anymore by the time either runs. A real
    prepare_*_export always writes one before upload; these fake mocks
    have to seed it explicitly for the same reason."""
    import hashlib
    lines = ["deadbeef  media.csv"]
    for filename in filenames:
        digest = hashlib.sha256((output_dir / filename).read_bytes()).hexdigest()
        lines.append(f"{digest}  {filename}")
    (output_dir / "checksums-sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def test_publish_all_finalizes_every_repo_before_locking_any(tmp_path):
    """_finalize_one runs right after phase 2's populate broadcast, for
    every repo, before phase 3 locks any of them — so phase 3 never needs
    the full build_dir."""
    calls = []

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_zenodo(output_dir, **kwargs):
        (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", return_value="https://huggingface.co/datasets/alice/dataset"),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", side_effect=lambda **k: calls.append("tag-hfh")),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", side_effect=lambda **k: calls.append("release-hfh")),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch(
            "services.publish_orchestrator.zenodo_cli.release_on_zenodo",
            side_effect=lambda output_dir, *, token: calls.append("release-zenodo") or {"doi": "10.5281/zenodo.1"},
        ),
        patch(
            "services.publish_orchestrator.hfh_service.copy_prepared_output_files",
            side_effect=lambda **k: calls.append("finalize-hfh"),
        ),
        patch(
            "services.publish_orchestrator.zenodo_service.copy_prepared_output_files",
            side_effect=lambda **k: calls.append("finalize-zenodo"),
        ),
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

    assert body["status"] == "done", body
    assert calls == ["finalize-hfh", "finalize-zenodo", "tag-hfh", "release-hfh", "release-zenodo"]


def test_publish_all_deletes_build_dirs_before_locking_and_releases_from_the_small_record(tmp_path):
    """Once finalized, a repo's build_dir (and the shared media cache) is
    gone — phase 3 releases Zenodo from _resolve_lock_dir's own copy of its
    record, and the released record then lands in the user's output_dir,
    replacing the pre-release copy _finalize_one put there."""
    seen = {}

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_zenodo(output_dir, **kwargs):
        (output_dir / "zenodo_record.json").write_text(
            json.dumps({"deposition_id": 7, "doi": None, "published": False}), encoding="utf-8",
        )

    def fake_release_zenodo(output_dir, *, token):
        session_dir = output_dir.parent
        seen["lock_dir"] = output_dir.name
        seen["record"] = json.loads((output_dir / "zenodo_record.json").read_text(encoding="utf-8"))
        seen["build_dirs_left"] = sorted(p.name for p in session_dir.glob("*-build"))
        seen["chain_dirs_left"] = sorted(p.name for p in session_dir.glob("chain-after-*"))
        seen["media_cache_left"] = (session_dir / "media-cache").exists()
        record = {**seen["record"], "doi": "10.5281/zenodo.7", "record_url": "https://zenodo.org/records/7", "published": True}
        (output_dir / "zenodo_record.json").write_text(json.dumps(record), encoding="utf-8")
        return record

    zenodo_output_dir = _tmp(tmp_path, "zenodo")
    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", return_value="https://huggingface.co/datasets/alice/dataset"),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface"),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(zenodo_output_dir), "token": "zen_x", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert seen["lock_dir"] == "zenodo-lock"
    assert seen["record"]["deposition_id"] == 7
    assert seen["build_dirs_left"] == []
    assert seen["chain_dirs_left"] == []
    assert seen["media_cache_left"] is False
    final_record = json.loads((zenodo_output_dir / "zenodo_record.json").read_text(encoding="utf-8"))
    assert final_record["published"] is True
    assert final_record["doi"] == "10.5281/zenodo.7"


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


def test_publish_all_shares_one_media_cache_dir_across_every_repo(tmp_path):
    """Unlike media_dir (only the first repo — see the test above),
    media_cache_dir must reach EVERY repo's own prepare_*_export call, and
    be the exact same directory each time — see
    common.download_public_images's own docstring for why that's what lets
    a later repo skip re-fetching a file an earlier one already mirrored."""
    captured = {}

    def fake_prepare_hfh(*, input_dir, output_dir, media_cache_dir=None, **kwargs):
        captured["hfh"] = media_cache_dir
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_prepare_zenodo(*, input_dir, output_dir, media_cache_dir=None, **kwargs):
        captured["zenodo"] = media_cache_dir
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
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                ],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done"
    assert captured["hfh"] is not None
    assert captured["hfh"] == captured["zenodo"]
    assert captured["hfh"].name == "media-cache"


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


# ── output_mode-aware chain (_extract_chain_input/_download_repo_copy) ──────

# ── checksums-sha256.txt cache (_get_checksums_for_populate) ────────────

def test_cache_checksums_copies_build_dirs_own_file_into_the_session_cache(tmp_path):
    from services.publish_orchestrator import _cache_checksums, _checksums_cache_path

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    (build_dir / "checksums-sha256.txt").write_text("deadbeef  CITATION.cff\n", encoding="utf-8")

    _cache_checksums(session_dir, "hfh", build_dir)

    cached = _checksums_cache_path(session_dir, "hfh")
    assert cached.read_text(encoding="utf-8") == "deadbeef  CITATION.cff\n"


def test_cache_checksums_is_a_no_op_when_build_dir_has_none_yet(tmp_path):
    """GBIF's own build_dir is never populated (see _upload_one) — must not
    raise."""
    from services.publish_orchestrator import _cache_checksums, _checksums_cache_path

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    empty_build_dir = tmp_path / "gbif-build"
    empty_build_dir.mkdir()

    _cache_checksums(session_dir, "gbif", empty_build_dir)  # must not raise

    assert not _checksums_cache_path(session_dir, "gbif").exists()


def test_get_checksums_for_populate_prefers_the_cache(tmp_path):
    from services.publish_orchestrator import _cache_checksums, _get_checksums_for_populate

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    (build_dir / "checksums-sha256.txt").write_text("cached  CITATION.cff\n", encoding="utf-8")
    _cache_checksums(session_dir, "hfh", build_dir)
    # build_dir's own copy since changed — proves the CACHE snapshot wins,
    # not whatever build_dir currently has.
    (build_dir / "checksums-sha256.txt").write_text("changed-after-caching  CITATION.cff\n", encoding="utf-8")

    result = asyncio.run(_get_checksums_for_populate({"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir))

    assert result.read_text(encoding="utf-8") == "cached  CITATION.cff\n"


def test_get_checksums_for_populate_falls_back_to_build_dir_when_uncached(tmp_path):
    from services.publish_orchestrator import _get_checksums_for_populate

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    (build_dir / "checksums-sha256.txt").write_text("from-build-dir  CITATION.cff\n", encoding="utf-8")

    result = asyncio.run(_get_checksums_for_populate({"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir))

    assert result == build_dir / "checksums-sha256.txt"


def test_get_checksums_for_populate_downloads_when_neither_cache_nor_build_dir_has_it(tmp_path):
    """The last-resort tier — build_dir exists (e.g. GBIF's own, or one
    genuinely missing the file) but has no checksums-sha256.txt of its
    own, and neither does the cache."""
    from services.publish_orchestrator import _get_checksums_for_populate

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()

    def fake_download(*, repo_id, token, target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "checksums-sha256.txt").write_text("downloaded  CITATION.cff\n", encoding="utf-8")

    with patch("services.publish_orchestrator.hfh_service.download_from_repo", side_effect=fake_download) as mock_download:
        result = asyncio.run(_get_checksums_for_populate(
            {"repo": "hfh", "repo_id": "alice/dataset", "token": "hf_x"}, session_dir=session_dir, build_dir=build_dir,
        ))

    mock_download.assert_called_once()
    assert result.read_text(encoding="utf-8") == "downloaded  CITATION.cff\n"


# ── CITATION.cff/README.md populate-dir cache ────────────────────────────

def test_cache_citation_and_readme_copies_both_files_into_the_session_cache(tmp_path):
    from services.publish_orchestrator import _cache_citation_and_readme, _populate_cache_dir

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})
    (build_dir / "README.md").write_text("# Title", encoding="utf-8")

    _cache_citation_and_readme(session_dir, "hfh", build_dir)

    cache_dir = _populate_cache_dir(session_dir, "hfh")
    assert yaml.safe_load((cache_dir / "CITATION.cff").read_text(encoding="utf-8")) == {"cff-version": "1.2.0"}
    assert (cache_dir / "README.md").read_text(encoding="utf-8") == "# Title"


def test_cache_citation_and_readme_only_copies_whichever_file_actually_exists(tmp_path):
    """A repo whose export never produced a README.md (e.g. a stripped-down
    test double) still gets its CITATION.cff cached — no crash, no
    README.md conjured out of nowhere."""
    from services.publish_orchestrator import _cache_citation_and_readme, _populate_cache_dir

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})

    _cache_citation_and_readme(session_dir, "hfh", build_dir)

    cache_dir = _populate_cache_dir(session_dir, "hfh")
    assert (cache_dir / "CITATION.cff").is_file()
    assert not (cache_dir / "README.md").exists()


def test_cache_citation_and_readme_is_a_no_op_for_gbif(tmp_path):
    from services.publish_orchestrator import _cache_citation_and_readme, _populate_cache_dir

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    empty_build_dir = tmp_path / "gbif-build"
    empty_build_dir.mkdir()

    _cache_citation_and_readme(session_dir, "gbif", empty_build_dir)  # must not raise

    assert not _populate_cache_dir(session_dir, "gbif").exists()


def test_resolve_populate_file_prefers_the_cache(tmp_path):
    from services.publish_orchestrator import _cache_citation_and_readme, _resolve_populate_file

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})
    _cache_citation_and_readme(session_dir, "hfh", build_dir)
    # build_dir's own copy changed after caching — proves the cached
    # snapshot wins, not whatever build_dir currently has.
    _write_citation(build_dir, {"cff-version": "1.2.0", "doi": "changed-after-caching"})

    result = asyncio.run(_resolve_populate_file(
        {"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir, filename="CITATION.cff",
    ))

    assert yaml.safe_load(result.read_text(encoding="utf-8")) == {"cff-version": "1.2.0"}


def test_resolve_populate_file_falls_back_to_build_dir_when_uncached(tmp_path):
    from services.publish_orchestrator import _resolve_populate_file

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})

    result = asyncio.run(_resolve_populate_file(
        {"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir, filename="CITATION.cff",
    ))

    assert result == build_dir / "CITATION.cff"


def test_resolve_populate_file_downloads_when_allowed_and_neither_cache_nor_build_dir_has_it(tmp_path):
    from services.publish_orchestrator import _resolve_populate_file

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()

    def fake_download(*, repo_id, token, target_dir):
        target_dir.mkdir(parents=True, exist_ok=True)
        _write_citation(target_dir, {"cff-version": "1.2.0", "doi": "downloaded"})

    with patch("services.publish_orchestrator.hfh_service.download_from_repo", side_effect=fake_download) as mock_download:
        result = asyncio.run(_resolve_populate_file(
            {"repo": "hfh", "repo_id": "alice/dataset", "token": "hf_x"},
            session_dir=session_dir, build_dir=build_dir, filename="CITATION.cff",
        ))

    mock_download.assert_called_once()
    assert yaml.safe_load(result.read_text(encoding="utf-8"))["doi"] == "downloaded"


def test_resolve_populate_file_skips_the_download_when_not_allowed(tmp_path):
    """README.md is patched only if present (see
    common.patch_readme_citation_url) — a cache/build_dir miss just means
    this repo's export never produced one, not that it needs fetching
    back, so callers resolving it (see _resolve_populate_dir) pass
    allow_download=False instead of triggering a real remote round-trip."""
    from services.publish_orchestrator import _resolve_populate_file

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()

    with patch("services.publish_orchestrator.hfh_service.download_from_repo") as mock_download:
        result = asyncio.run(_resolve_populate_file(
            {"repo": "hfh", "repo_id": "alice/dataset", "token": "hf_x"},
            session_dir=session_dir, build_dir=build_dir, filename="README.md", allow_download=False,
        ))

    mock_download.assert_not_called()
    assert result is None


def test_resolve_populate_file_returns_none_when_even_the_download_lacks_it(tmp_path):
    from services.publish_orchestrator import _resolve_populate_file

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()

    with patch("services.publish_orchestrator.hfh_service.download_from_repo"):
        result = asyncio.run(_resolve_populate_file(
            {"repo": "hfh", "repo_id": "alice/dataset", "token": "hf_x"},
            session_dir=session_dir, build_dir=build_dir, filename="README.md",
        ))

    assert result is None


def test_resolve_populate_dir_materializes_citation_readme_and_own_record(tmp_path):
    from services.publish_orchestrator import _resolve_populate_dir

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "zenodo-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})
    (build_dir / "README.md").write_text("# Title", encoding="utf-8")
    (build_dir / "zenodo_record.json").write_text(json.dumps({"deposition_id": 42}), encoding="utf-8")

    populate_dir = asyncio.run(_resolve_populate_dir(
        {"repo": "zenodo"}, session_dir=session_dir, build_dir=build_dir,
    ))

    assert populate_dir == session_dir / "zenodo-populate"
    assert yaml.safe_load((populate_dir / "CITATION.cff").read_text(encoding="utf-8")) == {"cff-version": "1.2.0"}
    assert (populate_dir / "README.md").read_text(encoding="utf-8") == "# Title"
    assert json.loads((populate_dir / "zenodo_record.json").read_text(encoding="utf-8")) == {"deposition_id": 42}


def test_resolve_populate_dir_omits_the_record_file_for_a_repo_without_one(tmp_path):
    """HFH never has a record file of its own (see _RECORD_FILENAME_BY_REPO)
    — must not raise trying to find one."""
    from services.publish_orchestrator import _resolve_populate_dir

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})

    populate_dir = asyncio.run(_resolve_populate_dir(
        {"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir,
    ))

    assert (populate_dir / "CITATION.cff").is_file()
    assert not list(populate_dir.glob("*_record.json"))


def test_resolve_populate_dir_reuses_an_already_resolved_dir_instead_of_discarding_its_patch(tmp_path):
    """GBIF's own DOI-sync-to-HFH step (see the module's own docstring)
    patches this same populate_dir BEFORE doi_populate.populate() resolves
    it again for its own cross-referencing pass — re-resolving from
    cache/build_dir at that point would silently discard GBIF's patch."""
    from services.publish_orchestrator import _resolve_populate_dir

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    _write_citation(build_dir, {"cff-version": "1.2.0"})

    first = asyncio.run(_resolve_populate_dir({"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir))
    # Simulates an earlier patch already applied to the resolved dir.
    _write_citation(first, {"cff-version": "1.2.0", "doi": "10.21373/eet8jz"})

    second = asyncio.run(_resolve_populate_dir({"repo": "hfh"}, session_dir=session_dir, build_dir=build_dir))

    assert second == first
    assert yaml.safe_load((second / "CITATION.cff").read_text(encoding="utf-8"))["doi"] == "10.21373/eet8jz"


def test_copy_populate_patches_back_copies_citation_readme_and_checksums_into_build_dir(tmp_path):
    from services.publish_orchestrator import _copy_populate_patches_back

    populate_dir = tmp_path / "hfh-populate"
    populate_dir.mkdir()
    _write_citation(populate_dir, {"cff-version": "1.2.0", "doi": "10.21373/eet8jz"})
    (populate_dir / "README.md").write_text("# Patched", encoding="utf-8")
    checksums_path = tmp_path / "checksums-cache" / "hfh.txt"
    checksums_path.parent.mkdir(parents=True)
    checksums_path.write_text("deadbeef  CITATION.cff\n", encoding="utf-8")
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()

    _copy_populate_patches_back(populate_dir, checksums_path, build_dir)

    assert yaml.safe_load((build_dir / "CITATION.cff").read_text(encoding="utf-8"))["doi"] == "10.21373/eet8jz"
    assert (build_dir / "README.md").read_text(encoding="utf-8") == "# Patched"
    assert (build_dir / "checksums-sha256.txt").read_text(encoding="utf-8") == "deadbeef  CITATION.cff\n"


def test_copy_populate_patches_back_skips_whichever_file_is_missing(tmp_path):
    """populate_dir may only have CITATION.cff (README.md was never part of
    this repo's export, see _resolve_populate_dir) — must not raise trying
    to copy back a README.md that was never resolved."""
    from services.publish_orchestrator import _copy_populate_patches_back

    populate_dir = tmp_path / "hfh-populate"
    populate_dir.mkdir()
    _write_citation(populate_dir, {"cff-version": "1.2.0"})
    checksums_path = tmp_path / "missing-checksums.txt"
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()

    _copy_populate_patches_back(populate_dir, checksums_path, build_dir)  # must not raise

    assert (build_dir / "CITATION.cff").is_file()
    assert not (build_dir / "README.md").exists()
    assert not (build_dir / "checksums-sha256.txt").exists()


# ── session-level canonical metadata.json ────────────────────────────────

def test_seed_session_metadata_copies_from_input_dir_once(tmp_path):
    from services.publish_orchestrator import _seed_session_metadata

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    input_dir = tmp_path / "input"
    _write_product_files(input_dir)  # title: "T"

    _seed_session_metadata(session_dir, input_dir)

    seeded = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert seeded["title"] == "T"


def test_seed_session_metadata_never_overwrites_an_already_seeded_copy(tmp_path):
    """Safe to call on every _run invocation, including a resume — must
    never clobber a copy _capture_session_metadata has since evolved with
    the ORIGINAL, now-stale input_dir content."""
    from services.publish_orchestrator import _seed_session_metadata

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "Already evolved"}), encoding="utf-8")
    input_dir = tmp_path / "input"
    _write_product_files(input_dir)  # title: "T"

    _seed_session_metadata(session_dir, input_dir)

    seeded = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert seeded["title"] == "Already evolved"


def test_capture_session_metadata_pulls_forward_a_repos_own_update(tmp_path):
    """The whole point: whatever a repo's own upload changed in ITS OWN
    metadata.json (e.g. product.write_homepage) survives in the session's
    canonical copy even once that repo's own build_dir is gone."""
    from services.publish_orchestrator import _capture_session_metadata

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "T", "homepage": None}), encoding="utf-8")
    build_dir = tmp_path / "hfh-build"
    _write_product_files(build_dir, homepage="https://huggingface.co/datasets/alice/dataset")

    _capture_session_metadata(session_dir, build_dir)

    captured = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert captured["homepage"] == "https://huggingface.co/datasets/alice/dataset"


def test_capture_session_metadata_is_a_no_op_for_gbif(tmp_path):
    """GBIF's own build_dir is never populated (see _upload_one) — no
    metadata.json to pull forward, and this must not raise."""
    from services.publish_orchestrator import _capture_session_metadata

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "T"}), encoding="utf-8")
    empty_build_dir = tmp_path / "gbif-build"
    empty_build_dir.mkdir()

    _capture_session_metadata(session_dir, empty_build_dir)  # must not raise

    assert json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))["title"] == "T"


# ── HFH's own hfh_record.json (_read_hfh_version) ────────────────────────

def test_read_hfh_version_prefers_the_record_file_over_metadata_json(tmp_path):
    from services.publish_orchestrator import _read_hfh_version

    build_dir = tmp_path / "build"
    _write_product_files(build_dir)  # metadata.json's own version: "1.0"
    (build_dir / "hfh_record.json").write_text(
        json.dumps({"repo_id": "alice/dataset", "version": "2.0", "tagged": False}), encoding="utf-8",
    )

    assert _read_hfh_version(build_dir) == "2.0"


def test_read_hfh_version_falls_back_to_the_session_once_build_dir_is_gone(tmp_path):
    from services.publish_orchestrator import _read_hfh_version

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(
        json.dumps({"version": "1.0", "repos": {"hfh": {"version": "9.9"}}}), encoding="utf-8",
    )
    assert _read_hfh_version(tmp_path / "hfh-build-gone", session_dir) == "9.9"

    (session_dir / "metadata.json").write_text(json.dumps({"version": "2.0", "repos": {}}), encoding="utf-8")
    assert _read_hfh_version(tmp_path / "hfh-build-gone", session_dir) == "2.0"


def test_read_hfh_version_falls_back_to_metadata_json_when_record_missing(tmp_path):
    """A session started before hfh_record.json existed, resumed now."""
    from services.publish_orchestrator import _read_hfh_version

    build_dir = tmp_path / "build"
    _write_product_files(build_dir)  # metadata.json's own version: "1.0"

    assert _read_hfh_version(build_dir) == "1.0"


def test_publish_all_hfh_lock_phase_tags_with_the_record_files_own_version(tmp_path):
    """End-to-end proof that _lock_one reads the version to tag from
    hfh_record.json (written by the real upload_to_huggingface during
    phase 1), not from build_dir's own metadata.json — even though both
    exist here, with DIFFERENT values, so a wrong read would tag the wrong
    version."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)  # metadata.json's own version: "1.0" — must NOT be tagged
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        (output_dir / "hfh_record.json").write_text(
            json.dumps({"repo_id": "alice/dataset", "version": "9.9", "tagged": False}), encoding="utf-8",
        )
        return "https://huggingface.co/datasets/alice/dataset"

    tagged_versions = []

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch(
            "services.publish_orchestrator.hfh_cli.tag_release_on_huggingface",
            side_effect=lambda **k: tagged_versions.append(k["version"]),
        ),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert tagged_versions == ["9.9"]


def test_extract_chain_input_prepared_reads_core_files_and_metadata_from_the_same_dir(tmp_path):
    from services.publish_orchestrator import _extract_chain_input

    build_dir = tmp_path / "build"
    _write_product_files(build_dir)
    chain_dir = tmp_path / "chain"

    result = asyncio.run(_extract_chain_input(build_dir, chain_dir, metadata_source=build_dir))

    assert result == chain_dir
    assert (chain_dir / "metadata.json").is_file()
    assert (chain_dir / "media.csv").is_file()
    assert not (chain_dir / "CITATION.cff").exists()  # never part of the "core" extraction


def test_extract_chain_input_downloaded_takes_core_files_from_one_dir_and_metadata_from_another(tmp_path):
    """The whole point of separating core_source from metadata_source (see
    the module's own docstring): a real downloaded-back copy never has
    metadata.json (excluded from every upload), so it has to come from the
    repo's own build_dir regardless of where the core files themselves
    came from."""
    from services.publish_orchestrator import _extract_chain_input

    build_dir = tmp_path / "build"
    _write_product_files(build_dir)

    downloaded_dir = tmp_path / "downloaded"
    _write_product_files(downloaded_dir)
    (downloaded_dir / "metadata.json").unlink()  # never present in a real downloaded copy
    (downloaded_dir / "media.csv").write_text("id\ndownloaded-marker", encoding="utf-8")

    chain_dir = tmp_path / "chain"
    result = asyncio.run(_extract_chain_input(downloaded_dir, chain_dir, metadata_source=build_dir))

    assert (result / "metadata.json").is_file()  # came from build_dir
    assert "downloaded-marker" in (result / "media.csv").read_text(encoding="utf-8")  # came from downloaded_dir


def test_download_repo_copy_hfh_uses_repo_id_and_token(tmp_path):
    from services.publish_orchestrator import _download_repo_copy

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    target_dir = tmp_path / "downloaded"
    with patch("services.publish_orchestrator.hfh_service.download_from_repo") as mock_download:
        asyncio.run(_download_repo_copy(
            {"repo": "hfh", "repo_id": "alice/dataset", "token": "hf_x"},
            session_dir=session_dir, build_dir=tmp_path / "unused-build", target_dir=target_dir,
        ))
    mock_download.assert_called_once_with(repo_id="alice/dataset", token="hf_x", target_dir=target_dir)


def test_download_repo_copy_zenodo_reads_the_deposition_id_from_its_own_record_file(tmp_path):
    from services.publish_orchestrator import _download_repo_copy

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "zenodo_record.json").write_text(json.dumps({"deposition_id": 555}), encoding="utf-8")
    target_dir = tmp_path / "downloaded"

    with patch("services.publish_orchestrator.zenodo_service.download_files_from_zenodo") as mock_download:
        asyncio.run(_download_repo_copy(
            {"repo": "zenodo", "environment": "sandbox", "token": "zen_x"},
            session_dir=session_dir, build_dir=build_dir, target_dir=target_dir,
        ))
    mock_download.assert_called_once_with(environment="sandbox", deposition_id=555, token="zen_x", target_dir=target_dir)


def test_download_repo_copy_zenodo_falls_back_to_the_session_metadata_record_when_build_dir_lacks_one(tmp_path):
    """The whole point of _capture_repo_record/_read_repo_record: once
    build_dir no longer has zenodo_record.json (already folded into the
    session's own metadata.json earlier), the chain/checksums fallback
    still finds the same deposition_id there instead of failing."""
    from services.publish_orchestrator import _download_repo_copy

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(
        json.dumps({"title": "T", "repos": {"zenodo": {"deposition_id": 777}}}), encoding="utf-8",
    )
    build_dir = tmp_path / "build"
    build_dir.mkdir()  # no zenodo_record.json here — only the session's own copy has it
    target_dir = tmp_path / "downloaded"

    with patch("services.publish_orchestrator.zenodo_service.download_files_from_zenodo") as mock_download:
        asyncio.run(_download_repo_copy(
            {"repo": "zenodo", "environment": "sandbox", "token": "zen_x"},
            session_dir=session_dir, build_dir=build_dir, target_dir=target_dir,
        ))
    mock_download.assert_called_once_with(environment="sandbox", deposition_id=777, token="zen_x", target_dir=target_dir)


def test_download_repo_copy_b2share_uses_the_draft_aware_call_not_the_published_one(tmp_path):
    """Unlike Zenodo/HFH, a still-draft B2SHARE record 404s on the
    published-record endpoint — this must go through
    download_draft_files_from_b2share, never download_files_from_b2share
    (see _download_repo_copy's own docstring)."""
    from services.publish_orchestrator import _download_repo_copy

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "b2share_record.json").write_text(json.dumps({"record_id": "rec-1"}), encoding="utf-8")
    target_dir = tmp_path / "downloaded"

    with (
        patch("services.publish_orchestrator.b2share_service.download_draft_files_from_b2share") as mock_draft,
        patch("services.publish_orchestrator.b2share_service.download_files_from_b2share") as mock_published,
    ):
        asyncio.run(_download_repo_copy(
            {"repo": "b2share", "environment": "sandbox", "token": "b2_x"},
            session_dir=session_dir, build_dir=build_dir, target_dir=target_dir,
        ))
    mock_draft.assert_called_once_with(environment="sandbox", record_id="rec-1", token="b2_x", target_dir=target_dir)
    mock_published.assert_not_called()


def test_finalize_one_downloaded_b2share_uses_the_draft_aware_call(tmp_path):
    """_finalize_one now runs BEFORE phase 3's lock, so the B2SHARE record
    is still a draft — its "downloaded" output_mode must go through the
    same draft-aware _download_repo_copy the chain uses."""
    from services.publish_orchestrator import _finalize_one

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    build_dir = tmp_path / "build"
    _write_product_files(build_dir)
    (build_dir / "b2share_record.json").write_text(json.dumps({"record_id": "rec-1", "pid": None}), encoding="utf-8")
    output_dir = tmp_path / "b2share_out"

    with (
        patch("services.publish_orchestrator.b2share_service.download_draft_files_from_b2share") as mock_draft,
        patch("services.publish_orchestrator.b2share_service.download_files_from_b2share") as mock_published,
    ):
        result = asyncio.run(_finalize_one(
            {"repo": "b2share", "output_dir": str(output_dir), "output_mode": "downloaded",
             "environment": "sandbox", "token": "b2_x"},
            session_dir=session_dir, build_dir=build_dir, previous_output_dir="/prev", dry_run=False,
        ))
    download_dir = tmp_path / "b2share_out-downloaded"
    assert result == str(download_dir)
    mock_draft.assert_called_once_with(environment="sandbox", record_id="rec-1", token="b2_x", target_dir=download_dir)
    mock_published.assert_not_called()


# ── folding each repo's own record into the session's own metadata.json ──

def test_capture_repo_record_folds_the_record_into_session_metadata(tmp_path):
    from services.publish_orchestrator import _capture_repo_record

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "T"}), encoding="utf-8")
    build_dir = tmp_path / "zenodo-build"
    build_dir.mkdir()
    (build_dir / "zenodo_record.json").write_text(json.dumps({"deposition_id": 555, "doi": "10.5281/zenodo.1"}), encoding="utf-8")

    _capture_repo_record(session_dir, "zenodo", build_dir)

    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["title"] == "T"  # untouched
    assert meta["repos"]["zenodo"] == {"deposition_id": 555, "doi": "10.5281/zenodo.1"}


def test_capture_repo_record_also_folds_hfhs_own_record(tmp_path):
    """HFH's record is folded in too — _read_hfh_version reads its
    "version" back from there once build_dir is gone."""
    from services.publish_orchestrator import _capture_repo_record

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "T"}), encoding="utf-8")
    build_dir = tmp_path / "hfh-build"
    build_dir.mkdir()
    (build_dir / "hfh_record.json").write_text(json.dumps({"repo_id": "alice/dataset", "version": "9.9"}), encoding="utf-8")

    _capture_repo_record(session_dir, "hfh", build_dir)

    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["repos"]["hfh"] == {"repo_id": "alice/dataset", "version": "9.9"}


def test_capture_repo_record_is_a_no_op_for_gbif(tmp_path):
    """GBIF registers straight into its own output_dir, never build_dir."""
    from services.publish_orchestrator import _capture_repo_record

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "T"}), encoding="utf-8")
    build_dir = tmp_path / "gbif-build"
    build_dir.mkdir()

    _capture_repo_record(session_dir, "gbif", build_dir)  # must not raise

    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "repos" not in meta


def test_capture_session_metadata_keeps_the_captured_repo_records(tmp_path):
    """A later repo's own metadata.json never has "repos" — overwriting the
    session copy with it must not drop the records captured so far."""
    from services.publish_orchestrator import _capture_session_metadata

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(
        json.dumps({"title": "old", "repos": {"zenodo": {"deposition_id": 1}}}), encoding="utf-8",
    )
    build_dir = tmp_path / "b2share-build"
    build_dir.mkdir()
    (build_dir / "metadata.json").write_text(json.dumps({"title": "new"}), encoding="utf-8")

    _capture_session_metadata(session_dir, build_dir)

    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta == {"title": "new", "repos": {"zenodo": {"deposition_id": 1}}}


def test_read_repo_record_falls_back_to_session_metadata(tmp_path):
    from services.publish_orchestrator import _read_repo_record

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(
        json.dumps({"title": "T", "repos": {"b2share": {"record_id": "rec-9"}}}), encoding="utf-8",
    )
    build_dir = tmp_path / "build"
    build_dir.mkdir()  # no b2share_record.json here

    record = _read_repo_record(session_dir, "b2share", build_dir)

    assert record == {"record_id": "rec-9"}


def test_read_repo_record_raises_when_found_nowhere(tmp_path):
    from services.publish_orchestrator import _read_repo_record

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "metadata.json").write_text(json.dumps({"title": "T"}), encoding="utf-8")
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    with pytest.raises(RuntimeError):
        _read_repo_record(session_dir, "zenodo", build_dir)


def test_publish_all_passthrough_output_mode_forwards_the_original_input_to_gbif_unchanged(tmp_path):
    """output_mode="passthrough" on HFH means GBIF gets whatever input_dir
    the WHOLE TASK started with, untouched — not the metadata.json HFH's
    own upload just updated (e.g. via product.write_homepage), and no
    chain-after-hfh extraction happens at all."""
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
                    {
                        "repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset",
                        "token": "hf_x", "output_mode": "passthrough",
                    },
                    {
                        "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "username": "alice", "password": "s3cret", "environment": "sandbox",
                    },
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    # NOT HFH's real, just-updated homepage — passthrough never picked it up.
    assert mock_register.call_args.kwargs["homepage"] is None


def test_publish_all_downloaded_output_mode_round_trips_hfh_before_gbif_reads_it(tmp_path):
    """output_mode="downloaded" on HFH makes the chain hand GBIF a
    freshly-downloaded-back copy instead of trusting the local build_dir —
    proven here by the download containing a marker value build_dir itself
    never had."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    def fake_download(*, repo_id, token, target_dir):
        _write_product_files(target_dir)
        (target_dir / "metadata.json").unlink()  # a real download never has it
        return target_dir

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=fake_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch(
            "services.publish_orchestrator.hfh_service.download_from_repo", side_effect=fake_download,
        ) as mock_download,
        patch(
            "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
            return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/xyz", "doi": None},
        ),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [
                    {
                        "repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset",
                        "token": "hf_x", "output_mode": "downloaded",
                    },
                    {
                        "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "username": "alice", "password": "s3cret", "environment": "sandbox",
                    },
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    # "done" (not "error") already proves _extract_chain_input successfully
    # read metadata.json from build_dir despite the downloaded copy lacking
    # it entirely — an unhandled FileNotFoundError there would fail the task.
    assert body["status"] == "done", body
    # Called twice: once for the chain (_download_repo_copy, phase 1 — what
    # this test is about) and once more for HFH's own output_mode
    # "downloaded" user-facing copy (_finalize_one, after phase 2 — pre-existing,
    # unrelated behavior that just happens to share output_mode's value).
    assert mock_download.call_count == 2
    for call in mock_download.call_args_list:
        assert call.kwargs["repo_id"] == "alice/dataset"


def test_publish_all_downloaded_output_mode_skips_the_real_download_in_dry_run(tmp_path):
    """dry_run has nothing real uploaded to round-trip through — must fall
    back to the same "prepared" extraction as the default, not attempt a
    real network download."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_service.download_from_repo") as mock_download,
        patch(
            "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
            return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/xyz", "doi": None},
        ),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir), "dry_run": True,
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "output_mode": "downloaded"},
                    {
                        "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                        "archive_url": "https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip",
                        "publishing_organization_key": "org-1", "installation_key": "inst-1",
                        "environment": "sandbox",
                    },
                ],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    mock_download.assert_not_called()


def test_publish_all_passes_existing_deposition_id_through_to_zenodo(tmp_path):
    """RepoPublishConfig.existing_deposition_id (see ZenodoPublishForm.tsx's
    own search button) must reach zenodo_cli.upload_to_zenodo unchanged —
    it's what makes upload_to_zenodo create a proper linked Zenodo NEW
    VERSION instead of an unrelated fresh deposition (see
    services.zenodo.upload_to_zenodo's own docstring)."""
    captured = {}

    def fake_prepare_zenodo(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        captured["existing_deposition_id"] = kwargs.get("existing_deposition_id")
        (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")

    def fake_release_zenodo(output_dir, *, token):
        return {"doi": None, "record_url": "https://zenodo.org/records/1"}

    with (
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{
                    "repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x",
                    "environment": "sandbox", "existing_deposition_id": "999",
                }],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert captured["existing_deposition_id"] == "999"


def test_publish_all_passes_existing_record_id_through_to_b2share(tmp_path):
    """RepoPublishConfig.existing_record_id (see B2SharePublishForm.tsx's
    own search button) must reach b2share_cli.upload_to_b2share unchanged —
    it's what makes upload_to_b2share create a proper linked InvenioRDM NEW
    VERSION instead of an unrelated fresh draft (see
    services.b2share.upload_to_b2share's own docstring)."""
    captured = {}

    def fake_prepare_b2share(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_b2share(output_dir, **kwargs):
        captured["existing_record_id"] = kwargs.get("existing_record_id")
        (output_dir / "b2share_record.json").write_text(json.dumps({"pid": None}), encoding="utf-8")

    def fake_release_b2share(output_dir, *, token):
        return {"pid": None, "record_url": "https://b2share.eudat.eu/records/1"}

    with (
        patch("services.publish_orchestrator.b2share_cli.prepare_b2share_export", side_effect=fake_prepare_b2share),
        patch("services.publish_orchestrator.b2share_cli.upload_to_b2share", side_effect=fake_upload_b2share),
        patch("services.publish_orchestrator.b2share_cli.release_on_b2share", side_effect=fake_release_b2share),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": "/tmp/camtrapdp",
                "repos": [{
                    "repo": "b2share", "output_dir": str(_tmp(tmp_path, "b2share")), "token": "b2_x",
                    "environment": "sandbox", "community_id": "comm-1", "existing_record_id": "rec-old",
                }],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert captured["existing_record_id"] == "rec-old"


def test_publish_all_cross_references_dois_and_reuploads_changed_citation(tmp_path):
    upload_counts = {"zenodo": 0, "b2share": 0}

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        upload_counts["zenodo"] += 1
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})
            (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": "10.5281/zenodo.1"}), encoding="utf-8")
            _write_checksums(output_dir, "CITATION.cff")

    def fake_upload_b2share(output_dir, **kwargs):
        upload_counts["b2share"] += 1
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1", "url": "https://doi.org/10.1234/b2share.1"})
            (output_dir / "b2share_record.json").write_text(json.dumps({"pid": "10.1234/b2share.1", "pid_kind": "doi"}), encoding="utf-8")
            _write_checksums(output_dir, "CITATION.cff")

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
        _write_checksums(output_dir, "CITATION.cff")

    def fake_upload_hfh(output_dir, **kwargs):
        return "https://huggingface.co/datasets/alice/dataset"

    def fake_prepare_repo(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})
            (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": "10.5281/zenodo.1"}), encoding="utf-8")
            _write_checksums(output_dir, "CITATION.cff")

    def fake_upload_b2share(output_dir, **kwargs):
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.1234/b2share.1"})
            (output_dir / "b2share_record.json").write_text(json.dumps({"pid": "10.1234/b2share.1", "pid_kind": "doi"}), encoding="utf-8")
            _write_checksums(output_dir, "CITATION.cff")

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
        _write_checksums(output_dir, "CITATION.cff")

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


def test_publish_all_gbif_threads_an_explicit_dataset_key_through(tmp_path):
    """GBIFPublishForm's own dataset-picker (see search_organization_datasets)
    lets the user choose an existing dataset to update instead of relying on
    gbif_linked_dataset_record.json — that choice must reach
    register_gbif_dataset unchanged."""
    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with patch(
        "services.publish_orchestrator.gbif_cli.register_gbif_dataset",
        return_value={"dataset_page_url": "https://registry.gbif-test.org/dataset/existing-uuid"},
    ) as mock_register:
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [{
                    "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
                    "archive_url": "https://example.org/datapackage.json",
                    "publishing_organization_key": "org-1", "installation_key": "inst-1",
                    "username": "alice", "password": "s3cret", "environment": "sandbox",
                    "dataset_key": "existing-uuid",
                }],
            })
            assert start.status_code == 200, start.text
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "done", body
    assert mock_register.call_args.kwargs["dataset_key"] == "existing-uuid"


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
    """GBIF now registers early (phase 1, alongside HFH's own upload), so its
    DOI is already known by the time this sync runs — right after
    doi_populate.populate(), BEFORE HFH's own tag gets created. It patches
    HFH's own build_dir (still-untagged "main"), not the final,
    user-configured output_dir, so the tag about to be created captures a
    commit that already has GBIF's DOI cross-referenced into it (see
    publish_orchestrator's own docstring)."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})
        _write_checksums(output_dir, "CITATION.cff")

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
    mock_sync.assert_called_once()
    call_kwargs = mock_sync.call_args.kwargs
    assert call_kwargs["gbif_output_dir"] == gbif_output_dir
    assert call_kwargs["hfh_repo_id"] == "alice/dataset"
    assert call_kwargs["hfh_token"] == "hf_x"
    # A small, resolved populate_dir (see _resolve_populate_dir) — not
    # hfh_output_dir, the final, user-configured output_dir, which only
    # gets its files after phase 2's finalize, later than this sync
    # runs, and not HFH's raw build_dir either, since that might not have
    # CITATION.cff/README.md physically present anymore by the time this
    # runs (see publish_orchestrator's own docstring).
    assert call_kwargs["hfh_output_dir"] != hfh_output_dir
    assert call_kwargs["hfh_output_dir"].name == "hfh-populate"


def test_publish_all_hfh_zenodo_gbif_gbifs_doi_always_wins_hfhs_primary_slot(tmp_path):
    """The one behavior change this covers: whenever GBIF has a DOI, it's
    ALWAYS HFH's primary/top-level "doi" — any other repo's own DOI in the
    same run (here, Zenodo's) only ever lands as a secondary "identifiers"
    entry, never displacing it. Achieved by running the GBIF-DOI-into-HFH
    sync BEFORE doi_populate.populate() (see publish_orchestrator's own
    docstring) — no primary_doi_source is even given here, proving GBIF
    wins unconditionally, not just as a side effect of "only one candidate
    yet". Runs gbif_service.sync_doi_to_hfh for REAL (only its own
    huggingface_hub.upload_file network call is stubbed out), so the actual
    CITATION.cff-patching logic is what's under test, not just that some
    mock got called."""
    def fake_prepare_hfh(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})
        _write_checksums(output_dir, "CITATION.cff")

    def fake_prepare_zenodo(*, input_dir, output_dir, **kwargs):
        _write_product_files(output_dir)

    def fake_upload_zenodo(output_dir, **kwargs):
        if not (output_dir / "CITATION.cff").is_file():
            _write_citation(output_dir, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})
            (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": "10.5281/zenodo.1"}), encoding="utf-8")

    def fake_register_gbif(archive_url, output_dir, **kwargs):
        # Mirrors the real register_gbif_dataset's own side effect: writing
        # its local record file is what lets sync_doi_to_hfh (running for
        # real below) find GBIF's DOI at all.
        record = {
            "dataset_key": "xyz", "archive_url": archive_url,
            "dataset_page_url": "https://registry.gbif-test.org/dataset/xyz", "doi": "10.21373/eet8jz",
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "gbif_linked_dataset_record.json").write_text(json.dumps(record), encoding="utf-8")
        return record

    hfh_citations_seen = []

    def spying_upload_hfh(output_dir, **kwargs):
        # Captures CITATION.cff's content at each call — the build_dir
        # itself is deleted once the whole task finishes, so it can't be
        # read back afterwards.
        hfh_citations_seen.append(_read_citation(output_dir))
        return "https://huggingface.co/datasets/alice/dataset"

    input_dir = tmp_path / "input"
    _write_product_files(input_dir)

    with (
        patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=fake_prepare_hfh),
        patch("services.publish_orchestrator.hfh_cli.upload_to_huggingface", side_effect=spying_upload_hfh),
        patch("services.publish_orchestrator.hfh_cli.tag_release_on_huggingface", return_value=None),
        patch("services.publish_orchestrator.hfh_cli.release_on_huggingface", return_value=True),
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch(
            "services.publish_orchestrator.zenodo_cli.release_on_zenodo",
            return_value={"doi": "10.5281/zenodo.1", "record_url": "https://sandbox.zenodo.org/records/1"},
        ),
        patch("services.publish_orchestrator.gbif_cli.register_gbif_dataset", side_effect=fake_register_gbif),
        # The only real network call inside the real gbif_service.sync_doi_to_hfh.
        patch("services.gbif_service.upload_file", return_value=None),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(input_dir),
                "repos": [
                    {"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"},
                    {"repo": "zenodo", "output_dir": str(_tmp(tmp_path, "zenodo")), "token": "zen_x", "environment": "sandbox"},
                    {
                        "repo": "gbif", "output_dir": str(_tmp(tmp_path, "gbif")),
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
    # Populate's own cross-reference of Zenodo's DOI into HFH DID change
    # HFH's CITATION.cff (a new "identifiers" entry), so it re-uploaded once
    # more after the initial upload phase.
    assert len(hfh_citations_seen) == 2
    hfh_citation = hfh_citations_seen[-1]
    assert hfh_citation["doi"] == "10.21373/eet8jz"
    assert hfh_citation["identifiers"] == [
        {"type": "doi", "value": "https://doi.org/10.5281/zenodo.1", "description": "Zenodo DOI"},
    ]


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
    (never populated) build_dir. register_gbif_dataset itself is called
    TWICE — phase 1's early registration (against HFH's floating "main") and
    the post-lock repoint (against HFH's own tag, once created)."""
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
    assert body["repos"]["gbif"]["archive_repointed_to_tag"] is True
    assert mock_register.call_count == 2
    first_archive_url = mock_register.call_args_list[0].args[0]
    second_archive_url = mock_register.call_args_list[1].args[0]
    assert first_archive_url == "https://huggingface.co/datasets/alice/dataset/resolve/main/datapackage.json"
    assert second_archive_url == "https://huggingface.co/datasets/alice/dataset/resolve/1.0/datapackage.json"


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


def test_resume_after_a_failed_lock_neither_reuploads_nor_refinalizes(tmp_path):
    """A repo interrupted mid-release (stage "releasing") was already
    uploaded AND finalized — resume must only retry its lock."""
    calls: list[str] = []
    release_attempts = {"count": 0}

    def fake_prepare(*, input_dir, output_dir, **kwargs):
        calls.append("prepare")
        _write_product_files(output_dir)
        _write_citation(output_dir, {"cff-version": "1.2.0"})

    def fake_upload_zenodo(output_dir, **kwargs):
        calls.append("upload-zenodo")
        (output_dir / "zenodo_record.json").write_text(json.dumps({"doi": None}), encoding="utf-8")

    def fake_release_zenodo(output_dir, *, token):
        release_attempts["count"] += 1
        calls.append("release-zenodo")
        if release_attempts["count"] == 1:
            raise RuntimeError("network blip")
        return {"doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1"}

    zenodo_output_dir = _tmp(tmp_path, "zenodo")
    repos = [{"repo": "zenodo", "output_dir": str(zenodo_output_dir), "token": "zen_x", "environment": "sandbox"}]

    with (
        patch("services.publish_orchestrator.zenodo_cli.prepare_zenodo_export", side_effect=fake_prepare),
        patch("services.publish_orchestrator.zenodo_cli.upload_to_zenodo", side_effect=fake_upload_zenodo),
        patch("services.publish_orchestrator.zenodo_cli.release_on_zenodo", side_effect=fake_release_zenodo),
        patch(
            "services.publish_orchestrator.zenodo_service.copy_prepared_output_files",
            side_effect=lambda **k: calls.append("finalize-zenodo"),
        ),
    ):
        with _client() as client:
            start = client.post("/api/publish/start", json={"input_dir": "/tmp/camtrapdp", "repos": repos})
            task_id = start.json()["task_id"]
            body = _poll(client, task_id)
            assert body["status"] == "error", body
            assert body["repos"]["zenodo"]["stage"] == "releasing"
            assert body["repos"]["zenodo"]["output_dir"] == str(zenodo_output_dir)

            resume = client.post(f"/api/publish/sessions/{task_id}/resume", json={"repos": repos})
            assert resume.status_code == 200, resume.text
            resumed_body = _poll(client, task_id)

    assert resumed_body["status"] == "done", resumed_body
    assert resumed_body["repos"]["zenodo"]["doi"] == "10.5281/zenodo.1"
    assert calls == ["prepare", "upload-zenodo", "finalize-zenodo", "release-zenodo", "release-zenodo"]


def test_publish_all_reuses_a_prior_fetch_sessions_task_id(tmp_path):
    """A session_task_id from an earlier fetch/preprocess phase (see
    services.session_store) makes start_publish_all_task reuse that exact
    session_dir instead of minting a new one — the fetched source and
    preprocessing choices end up living alongside this publish's own build
    dirs, and a fully successful run deletes the whole thing together
    (confirmed with the user: including the fetched source itself)."""
    from services import session_store

    task_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="archive",
        fetch={
            "source_type": "archive", "params": {"url": "https://example.org/x.zip", "clear_cache": False},
            "output_dir": str(tmp_path / "source"), "input_dir": str(tmp_path / "source"),
        },
        status="done", error=None,
    )
    session_store.write_preprocessing_phase(
        task_id, status="done", error=None,
        choices={"anonymize_coordinates": False, "coordinate_decimals": 2, "randomize_media_ids": False, "media_id_domain": "localhost"},
    )

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
                "input_dir": str(tmp_path / "source"), "session_task_id": task_id,
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            assert start.status_code == 200, start.text
            returned_task_id = start.json()["task_id"]
            assert returned_task_id == task_id  # reused, not a fresh uuid4()
            body = _poll(client, returned_task_id)

    assert body["status"] == "done", body
    from wildintel_publisher.config import get_sessions_dir
    assert not (get_sessions_dir() / task_id).exists()  # the whole session, including the fetched source/, is gone


def test_publish_all_keeps_the_fetch_and_preprocessing_sections_when_publishing_fails(tmp_path):
    from services import session_store

    task_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="trapper",
        fetch={
            "source_type": "trapper",
            "params": {"url": "https://trapper.example", "project_id": 1, "deployment_id": "d1", "clear_cache": False, "include_events": True},
            "output_dir": str(tmp_path / "source"), "input_dir": str(tmp_path / "source"),
        },
        status="done", error=None,
    )

    def failing_prepare(*, input_dir, output_dir, **kwargs):
        raise RuntimeError("boom")

    with patch("services.publish_orchestrator.hfh_cli.prepare_hfh_export", side_effect=failing_prepare):
        with _client() as client:
            start = client.post("/api/publish/start", json={
                "input_dir": str(tmp_path / "source"), "session_task_id": task_id,
                "repos": [{"repo": "hfh", "output_dir": str(_tmp(tmp_path, "hfh")), "repo_id": "alice/dataset", "token": "hf_x"}],
            })
            body = _poll(client, start.json()["task_id"])

    assert body["status"] == "error"
    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "publishing"
    assert manifest["source_type"] == "trapper"
    assert manifest["fetch"]["params"]["project_id"] == 1  # the fetch phase's own section survives


def test_publish_all_rejects_starting_a_session_that_is_already_publishing():
    from services import session_store

    task_id = session_store.new_task_id()
    session_store.write_manifest(task_id, {"task_id": task_id, "phase": "publishing", "status": "running"})

    response = _client().post("/api/publish/start", json={
        "input_dir": "/tmp/camtrapdp", "session_task_id": task_id,
        "repos": [{"repo": "hfh", "output_dir": "/tmp/hfh", "repo_id": "alice/dataset", "token": "hf_x"}],
    })

    assert response.status_code == 409


# ── HFH's primary DOI when the caller didn't choose one ──

def _write_metadata(directory: Path, product_type: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(json.dumps({"product_type": product_type}), encoding="utf-8")
    return directory


@pytest.mark.parametrize("product_type", ["yolo", "software"])
def test_default_primary_doi_prefers_zenodo_then_b2share_outside_camtrapdp(tmp_path, product_type):
    from services.publish_orchestrator import _default_primary_doi_source

    input_dir = _write_metadata(tmp_path / "input", product_type)
    assert _default_primary_doi_source(input_dir, [{"repo": "hfh"}, {"repo": "b2share"}, {"repo": "zenodo"}]) == "zenodo"
    assert _default_primary_doi_source(input_dir, [{"repo": "hfh"}, {"repo": "b2share"}]) == "b2share"
    assert _default_primary_doi_source(input_dir, [{"repo": "hfh"}]) is None


def test_default_primary_doi_leaves_camtrapdp_to_the_wizard(tmp_path):
    from services.publish_orchestrator import _default_primary_doi_source

    input_dir = _write_metadata(tmp_path / "input", "camtrapdp")
    assert _default_primary_doi_source(input_dir, [{"repo": "hfh"}, {"repo": "zenodo"}, {"repo": "b2share"}]) is None


def test_default_primary_doi_is_none_without_metadata(tmp_path):
    from services.publish_orchestrator import _default_primary_doi_source

    assert _default_primary_doi_source(tmp_path / "missing", [{"repo": "zenodo"}]) is None
