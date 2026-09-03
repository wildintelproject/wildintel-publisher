"""Integration tests for 'zenodo prepare/upload/release/sync-doi' — the
Zenodo REST API and image downloads are mocked out (no real network)."""
import csv
import json
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _init_software_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "CITATION.cff").write_text(yaml.safe_dump({
        "cff-version": "1.2.0", "title": "my-app", "version": "1.0.0", "license": "MIT",
        "authors": [{"given-names": "Jane", "family-names": "Doe"}],
        "repository-code": "https://github.com/example/my-app",
    }), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example/my-app.git"], cwd=root, check=True)
    return root


def _fake_httpx_get_image(self, url, *args, **kwargs):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = b"fake-image-bytes"
    return response


def _media_filepaths(output_dir):
    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        return [row["filePath"] for row in csv.DictReader(f)]


# ── prepare — the three filePath modes ───────────────────────────────────────

def test_zenodo_prepare_plain_mode_leaves_filepath_untouched(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=True)
    output_dir = tmp_path / "zenodo_out"

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--no-self-contained",
    ])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "images").exists()
    assert not (output_dir / "camtrapdp.zip").exists()
    assert _media_filepaths(output_dir) == ["https://trapper.example/m1.jpg?rt=tok1"]


def test_zenodo_prepare_defaults_to_self_contained_for_camtrapdp(camtrapdp_dir, tmp_path):
    # No --self-contained/--no-self-contained/--hfh-repo-id given at all —
    # Camtrap DP now defaults to mirror (self-contained), unlike Plain
    # above, which needs --no-self-contained to opt back into the old
    # behavior.
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"

    with patch("httpx.Client.get", _fake_httpx_get_image):
        result = runner.invoke(app, ["zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert (output_dir / "camtrapdp.zip").is_file()
    assert not (output_dir / "media.csv").exists()  # bundled into the zip, loose copy cleaned up


def test_zenodo_prepare_excludes_stale_raw_camtrapdp_zip(camtrapdp_dir, tmp_path):
    """Regression test: input_dir may carry Trapper's original camtrapdp.zip
    (kept alongside the extracted files) — it must NOT be copied verbatim,
    since it's stale as soon as private media gets filtered out below."""
    input_dir = camtrapdp_dir("trapper_out", include_private_media=True)
    (input_dir / "camtrapdp.zip").write_bytes(b"stale-zip-with-private-media-still-inside")
    output_dir = tmp_path / "zenodo_out"

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--no-self-contained",
    ])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "camtrapdp.zip").exists()


def test_zenodo_prepare_hfh_repo_id_mode_rewrites_to_predictable_hfh_url(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--hfh-repo-id", "someuser/somedataset",
    ])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "images").exists()
    assert _media_filepaths(output_dir) == ["https://huggingface.co/datasets/someuser/somedataset/resolve/main/images/m1.jpg"]
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "metadata-only" in readme
    assert "someuser/somedataset" in readme

    # Link mode also gets a camtrapdp-remote.zip (same shape as HFH's own —
    # see common.write_remote_zip): no images embedded (media.csv already
    # points at real HFH URLs), single root folder, ready as GBIF's own
    # --archive-url without needing Hugging Face Hub published in this run.
    zip_path = output_dir / "camtrapdp-remote.zip"
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert names == [
            "camtrapdp-remote/datapackage.json", "camtrapdp-remote/deployments.csv",
            "camtrapdp-remote/media.csv", "camtrapdp-remote/observations.csv",
        ]
        with zf.open("camtrapdp-remote/media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "https://huggingface.co/datasets/someuser/somedataset/resolve/main/images/m1.jpg"
    # the loose tables (with the same rewritten URL) still stay alongside it too
    assert (output_dir / "media.csv").is_file()


def test_zenodo_prepare_self_contained_mode_downloads_images_and_bundles_zip(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"

    with patch("httpx.Client.get", _fake_httpx_get_image):
        result = runner.invoke(app, [
            "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
        ])

    assert result.exit_code == 0, result.output
    zip_path = output_dir / "camtrapdp.zip"
    assert zip_path.is_file()
    # nested under a single root folder (the zip's own stem) so this same
    # archive also works as GBIF's --archive-url — see write_local_zip.
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "camtrapdp/images/m1.jpg" in names
        assert zf.read("camtrapdp/images/m1.jpg") == b"fake-image-bytes"
        with zf.open("camtrapdp/media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "images/m1.jpg"

    # the loose datapackage.json/CSVs/images/ are removed once bundled into the zip —
    # output_dir ends up with just camtrapdp.zip, README.md, CITATION.cff, LICENSE,
    # checksums and metadata.json (the generated wrapper files, kept as-is).
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "CITATION.cff", "LICENSE", "README.md", "camtrapdp.zip", "checksums-sha256.txt", "metadata.json",
    ]

    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "self-contained" in readme
    assert "camtrapdp.zip" in readme


def test_zenodo_prepare_self_contained_takes_precedence_over_hfh_repo_id(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"

    with patch("httpx.Client.get", _fake_httpx_get_image):
        result = runner.invoke(app, [
            "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
            "--self-contained", "--hfh-repo-id", "someuser/somedataset",
        ])

    assert result.exit_code == 0, result.output
    assert "Both --self-contained and --hfh-repo-id were given" in result.output
    assert (output_dir / "camtrapdp.zip").is_file()
    assert not (output_dir / "media.csv").exists()  # cleaned up, not rewritten to HFH either
    with zipfile.ZipFile(output_dir / "camtrapdp.zip") as zf:
        with zf.open("camtrapdp/media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "images/m1.jpg"  # embedded + relative, not the HFH URL


def test_zenodo_prepare_fails_when_input_dir_missing(tmp_path):
    result = runner.invoke(app, ["zenodo", "prepare", "--input-dir", str(tmp_path / "missing"), "--output-dir", str(tmp_path / "out")])
    assert result.exit_code == 1


def test_zenodo_prepare_refuses_non_empty_output_dir_without_overwrite(camtrapdp_dir, tmp_path, caplog):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 1
    # reported via logging.error, not visible in CliRunner's result.output — check caplog instead.
    assert "already exists and is not empty" in caplog.text
    assert (output_dir / "leftover.txt").is_file()


def test_zenodo_prepare_reuses_non_empty_output_dir_with_overwrite(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--overwrite", "--no-self-contained",
    ])

    assert result.exit_code == 0, result.output
    assert (output_dir / "README.md").is_file()


# ── upload / release / sync-doi — mocked Zenodo REST API ────────────────────

def _fake_response(status_code=200, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data if json_data is not None else {}
    return response


def _prepared_zenodo_export(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"
    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--no-self-contained",
    ])
    assert result.exit_code == 0, result.output
    return output_dir


def test_zenodo_upload_never_uploads_metadata_json(camtrapdp_dir, tmp_path, monkeypatch):
    """metadata.json is internal pipeline bookkeeping (product_type,
    publish_history...) — kept in output_dir for chaining/re-reading, but
    must never reach Zenodo itself."""
    monkeypatch.setenv("ZENODO_TOKEN", "faketoken")
    output_dir = _prepared_zenodo_export(camtrapdp_dir, tmp_path)
    assert (output_dir / "metadata.json").is_file()

    draft_deposition = {"id": 555, "links": {"bucket": "https://sandbox.zenodo.org/api/files/bucket-abc"}, "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.555"}}}
    uploaded_filenames = []

    def fake_post(url, **kwargs):
        if url.endswith("/deposit/depositions"):
            return _fake_response(201, draft_deposition)
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        if url.endswith("/deposit/depositions/555"):
            return _fake_response(200, draft_deposition)
        uploaded_filenames.append(url.rsplit("/", 1)[-1])
        return _fake_response(201, {})  # file upload to bucket

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put):
        result = runner.invoke(app, ["zenodo", "upload", "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert "metadata.json" not in uploaded_filenames
    assert "README.md" in uploaded_filenames


def test_zenodo_upload_then_release_then_sync_doi(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("ZENODO_TOKEN", "faketoken")
    output_dir = _prepared_zenodo_export(camtrapdp_dir, tmp_path)

    state = {"published": False}
    draft_deposition = {"id": 555, "links": {"bucket": "https://sandbox.zenodo.org/api/files/bucket-abc"}, "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.555"}}}
    published_deposition = {
        "id": 555,
        "links": {"bucket": "https://sandbox.zenodo.org/api/files/bucket-abc", "record_html": "https://sandbox.zenodo.org/records/555"},
        "metadata": {"doi": "10.5281/zenodo.555"},
        "doi": "10.5281/zenodo.555",
    }

    def fake_post(url, **kwargs):
        if url.endswith("/deposit/depositions"):
            return _fake_response(201, draft_deposition)
        if url.endswith("/actions/publish"):
            state["published"] = True
            return _fake_response(202, published_deposition)
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        if url.endswith("/deposit/depositions/555"):
            return _fake_response(200, draft_deposition)
        return _fake_response(201, {})  # file upload to bucket

    def fake_get(url, **kwargs):
        return _fake_response(200, published_deposition if state["published"] else draft_deposition)

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), patch("httpx.get", side_effect=fake_get):
        upload_result = runner.invoke(app, ["zenodo", "upload", "--output-dir", str(output_dir)])
        assert upload_result.exit_code == 0, upload_result.output

        record = json.loads((output_dir / "zenodo_record.json").read_text(encoding="utf-8"))
        assert record["deposition_id"] == 555
        assert record["published"] is False

        release_result = runner.invoke(app, ["zenodo", "release", "--output-dir", str(output_dir)])
        assert release_result.exit_code == 0, release_result.output

    record = json.loads((output_dir / "zenodo_record.json").read_text(encoding="utf-8"))
    assert record["published"] is True
    assert record["doi"] == "10.5281/zenodo.555"

    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["identifiers"][0]["value"] == "10.5281/zenodo.555"  # sandbox -> identifiers, not top-level doi

    # sync-doi reflects the same DOI into an (unrelated, here reused) hfh export dir
    hfh_dir = tmp_path / "hfh_out"
    hfh_dir.mkdir()
    (hfh_dir / "CITATION.cff").write_text(yaml.safe_dump({"cff-version": "1.2.0", "title": "T"}), encoding="utf-8")

    sync_result = runner.invoke(app, ["zenodo", "sync-doi", "--zenodo-output-dir", str(output_dir), "--hfh-output-dir", str(hfh_dir)])
    assert sync_result.exit_code == 0, sync_result.output

    hfh_citation = yaml.safe_load((hfh_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert hfh_citation["identifiers"][0]["value"] == "10.5281/zenodo.555"


def test_zenodo_upload_production_mode_reserves_doi_and_patches_citation_and_readme_before_uploading(camtrapdp_dir, tmp_path, monkeypatch):
    """In production, the DOI Zenodo prereserves in update_deposition_metadata's
    own response is already usable — upload_to_zenodo must patch
    CITATION.cff's top-level doi/url AND README.md's placeholder with it
    BEFORE uploading any file, so what actually lands on Zenodo already has
    the DOI baked in (unlike before this behavior existed, where README.md
    only ever got it via a separate, manual re-upload)."""
    monkeypatch.setenv("ZENODO_TOKEN", "faketoken")
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"
    prepare_result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
    ])
    assert prepare_result.exit_code == 0, prepare_result.output
    assert "(DOI assigned by Zenodo upon publication)" in (output_dir / "README.md").read_text(encoding="utf-8")

    draft_deposition = {
        "id": 777, "links": {"bucket": "https://zenodo.org/api/files/bucket-xyz"},
        "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.777"}},
    }

    def fake_post(url, **kwargs):
        if url.endswith("/deposit/depositions"):
            return _fake_response(201, draft_deposition)
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        if url.endswith("/deposit/depositions/777"):
            return _fake_response(200, draft_deposition)
        return _fake_response(201, {})  # file upload to bucket

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put):
        result = runner.invoke(app, [
            "zenodo", "upload", "--output-dir", str(output_dir), "--environment", "production",
        ])

    assert result.exit_code == 0, result.output
    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["doi"] == "10.5281/zenodo.777"
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "https://doi.org/10.5281/zenodo.777" in readme
    assert "(DOI assigned by Zenodo upon publication)" not in readme

    record = json.loads((output_dir / "zenodo_record.json").read_text(encoding="utf-8"))
    assert record["doi"] == "10.5281/zenodo.777"


def test_zenodo_upload_sandbox_mode_never_patches_readme_with_the_test_doi(camtrapdp_dir, tmp_path, monkeypatch):
    """Sandbox DOIs aren't citable — CITATION.cff may record it (in
    identifiers, never the top-level doi/url — see _patch_citation_with_doi),
    but README.md's placeholder must never be replaced with one."""
    monkeypatch.setenv("ZENODO_TOKEN", "faketoken")
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "zenodo_out"
    prepare_result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
    ])
    assert prepare_result.exit_code == 0, prepare_result.output

    draft_deposition = {
        "id": 888, "links": {"bucket": "https://sandbox.zenodo.org/api/files/bucket-abc"},
        "metadata": {"prereserve_doi": {"doi": "10.5072/zenodo.888"}},
    }

    def fake_post(url, **kwargs):
        if url.endswith("/deposit/depositions"):
            return _fake_response(201, draft_deposition)
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        if url.endswith("/deposit/depositions/888"):
            return _fake_response(200, draft_deposition)
        return _fake_response(201, {})

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put):
        result = runner.invoke(app, ["zenodo", "upload", "--output-dir", str(output_dir)])  # default: sandbox

    assert result.exit_code == 0, result.output
    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert "doi" not in citation
    assert citation["identifiers"][0]["value"] == "10.5072/zenodo.888"
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "(DOI assigned by Zenodo upon publication)" in readme
    assert "10.5072/zenodo.888" not in readme


def test_zenodo_upload_without_token_reports_error(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)
    output_dir = _prepared_zenodo_export(camtrapdp_dir, tmp_path)

    result = runner.invoke(app, ["zenodo", "upload", "--output-dir", str(output_dir)])

    assert result.exit_code == 1
    assert "No Zenodo token configured" in result.output


def test_zenodo_sync_doi_fails_when_not_yet_published(camtrapdp_dir, tmp_path):
    output_dir = _prepared_zenodo_export(camtrapdp_dir, tmp_path)
    (output_dir / "zenodo_record.json").write_text(json.dumps({
        "deposition_id": 1, "environment": "sandbox", "doi": None, "record_url": "https://x", "published": False,
    }), encoding="utf-8")

    result = runner.invoke(app, ["zenodo", "sync-doi", "--zenodo-output-dir", str(output_dir), "--hfh-output-dir", str(tmp_path / "hfh_out")])

    assert result.exit_code == 1


# ── software application: reference-only ("link") mode ──────────────────────

def test_zenodo_prepare_software_reference_mode_copies_no_source_and_cites_the_repo(tmp_path):
    """Software has no HFH target — "link" mode (self_contained=False, no
    --hfh-repo-id) must cite the repository itself, not a Hugging Face Hub
    placeholder, and must not copy any source files (see
    SoftwareAdapter.prepare's own mirror=False branch)."""
    input_dir = _init_software_repo(tmp_path / "repo")
    generate = runner.invoke(app, [
        "product", "generate-metadata", "--input-dir", str(input_dir), "--product-type", "software",
    ])
    assert generate.exit_code == 0, generate.output

    output_dir = tmp_path / "zenodo_out"
    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--hfh-repo-id", "",
    ])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "main.py").exists()
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "https://github.com/example/my-app" in readme
    assert "REPLACE_WITH_HF_USER/dataset" not in readme


def test_zenodo_prepare_software_self_contained_mode_zips_the_original_repo_files(tmp_path):
    """Self-contained ("Mirror") mode bundles the whole repo into a zip — its
    contents come straight from the clone itself (input_dir), so the repo's
    own README.md/CITATION.cff keep their real names inside the zip, instead
    of a SOURCE_-renamed copy sitting alongside a newly-generated one under
    the same original name (see SoftwareAdapter.bundle_local_zip)."""
    input_dir = _init_software_repo(tmp_path / "repo")
    (input_dir / "README.md").write_text("# my-app\n", encoding="utf-8")
    generate = runner.invoke(app, [
        "product", "generate-metadata", "--input-dir", str(input_dir), "--product-type", "software",
    ])
    assert generate.exit_code == 0, generate.output

    output_dir = tmp_path / "zenodo_out"
    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
    ])

    assert result.exit_code == 0, result.output
    # Only the generated citation files + the zip survive loose in output_dir
    # — everything else (the repo's own files) is only inside the zip.
    assert not (output_dir / "main.py").exists()
    assert (output_dir / "README.md").is_file()
    assert (output_dir / "CITATION.cff").is_file()

    with zipfile.ZipFile(output_dir / "software.zip") as zf:
        names = set(zf.namelist())
    assert "main.py" in names
    assert "README.md" in names  # the repo's own, real name — not SOURCE_README.md
    assert "CITATION.cff" in names
    assert not any(name.startswith(".git/") for name in names)
    assert "metadata.json" not in names
