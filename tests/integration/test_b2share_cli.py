"""Integration tests for 'b2share prepare/upload/release/sync-pid' — the
B2SHARE REST API and image downloads are mocked out (no real network).

'b2share prepare' has the same three filePath modes as 'zenodo prepare':
plain (default, filePath untouched), --hfh-repo-id (rewrite to the
predictable HuggingFace Hub URL, no download), and --self-contained (now
identical to 'zenodo prepare' --self-contained — downloads images, bundles
them inside a single camtrapdp.zip with media.csv's filePath relative to
images/, and removes the loose files — B2SHARE's API caps each record at
100 files, so uploading one file per image the old way isn't viable)."""
import csv
import json
import zipfile
from unittest.mock import MagicMock, patch

import yaml
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _fake_httpx_get_image(self, url, *args, **kwargs):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.content = b"fake-image-bytes"
    return response


def _media_filepaths(output_dir):
    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        return [row["filePath"] for row in csv.DictReader(f)]


# ── prepare — the three filePath modes ───────────────────────────────────────

def test_b2share_prepare_plain_mode_leaves_filepath_untouched(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=True)
    output_dir = tmp_path / "b2share_out"

    result = runner.invoke(app, ["b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "images").exists()
    assert not (output_dir / "camtrapdp-local.zip").exists()
    assert _media_filepaths(output_dir) == ["https://trapper.example/m1.jpg?rt=tok1"]
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "metadata-only" in readme


def test_b2share_prepare_excludes_extra_files_from_hfh_output_dir(camtrapdp_dir, tmp_path):
    """input_dir doesn't have to be Trapper's raw output — if it's HFH's own
    processed export instead, it carries extra files (its own
    README/CITATION/LICENSE, images/, camtrapdp-local.zip) that must NOT be
    copied into B2SHARE's own record (only the whitelisted core files)."""
    input_dir = camtrapdp_dir("hfh_out", include_private_media=False)
    (input_dir / "README.md").write_text("# HFH's own README", encoding="utf-8")
    (input_dir / "camtrapdp-local.zip").write_bytes(b"hfh-local-zip")
    (input_dir / "images").mkdir()
    (input_dir / "images" / "m1.jpg").write_bytes(b"hfh-image")
    output_dir = tmp_path / "b2share_out"

    result = runner.invoke(app, ["b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert (output_dir / "README.md").read_text(encoding="utf-8") != "# HFH's own README"  # B2SHARE generated its own
    assert not (output_dir / "camtrapdp-local.zip").exists()
    assert not (output_dir / "images").exists()


def test_b2share_prepare_hfh_repo_id_mode_rewrites_to_predictable_hfh_url(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "b2share_out"

    result = runner.invoke(app, [
        "b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--hfh-repo-id", "someuser/somedataset",
    ])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "images").exists()
    assert _media_filepaths(output_dir) == ["https://huggingface.co/datasets/someuser/somedataset/resolve/main/images/m1.jpg"]
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "metadata-only" in readme
    assert "someuser/somedataset" in readme


def test_b2share_prepare_self_contained_downloads_and_bundles_zip(camtrapdp_dir, tmp_path):
    """--self-contained now behaves exactly like 'zenodo prepare'
    --self-contained: downloads images, bundles them (plus datapackage.json/
    CSVs) inside a single camtrapdp.zip with media.csv's filePath relative
    to images/, and removes the loose sources — B2SHARE's API caps each
    record at 100 files, so keeping (and later uploading) hundreds of loose
    image files isn't viable."""
    input_dir = camtrapdp_dir("trapper_out", include_private_media=True)
    output_dir = tmp_path / "b2share_out"

    with patch("httpx.Client.get", _fake_httpx_get_image):
        result = runner.invoke(app, [
            "b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
        ])

    assert result.exit_code == 0, result.output
    zip_path = output_dir / "camtrapdp.zip"
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "images/m1.jpg" in names
        assert zf.read("images/m1.jpg") == b"fake-image-bytes"
        with zf.open("media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "images/m1.jpg"  # 2nd (private) row filtered out beforehand

    # the loose datapackage.json/CSVs/images/ are removed once bundled into the zip
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "CITATION.cff", "LICENSE", "README.md", "camtrapdp.zip", "checksums-sha256.txt", "metadata.json",
    ]
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "B2SHARE" in readme
    assert "metadata-only" not in readme
    assert "camtrapdp.zip" in readme


def test_b2share_prepare_self_contained_takes_precedence_over_hfh_repo_id(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "b2share_out"

    with patch("httpx.Client.get", _fake_httpx_get_image):
        result = runner.invoke(app, [
            "b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
            "--self-contained", "--hfh-repo-id", "someuser/somedataset",
        ])

    assert result.exit_code == 0, result.output
    assert "Both --self-contained and --hfh-repo-id were given" in result.output
    assert (output_dir / "camtrapdp.zip").is_file()
    assert not (output_dir / "media.csv").exists()  # cleaned up, not rewritten to HFH either
    with zipfile.ZipFile(output_dir / "camtrapdp.zip") as zf:
        with zf.open("media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "images/m1.jpg"  # embedded + relative, not the HFH URL


def test_b2share_prepare_fails_when_input_dir_missing(tmp_path):
    result = runner.invoke(app, ["b2share", "prepare", "--input-dir", str(tmp_path / "missing"), "--output-dir", str(tmp_path / "out")])
    assert result.exit_code == 1


def test_b2share_prepare_refuses_non_empty_output_dir_without_overwrite(camtrapdp_dir, tmp_path, caplog):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "b2share_out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 1
    # reported via logging.error, not visible in CliRunner's result.output — check caplog instead.
    assert "already exists and is not empty" in caplog.text
    assert (output_dir / "leftover.txt").is_file()


def test_b2share_prepare_reuses_non_empty_output_dir_with_overwrite(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "b2share_out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--overwrite"])

    assert result.exit_code == 0, result.output
    assert (output_dir / "README.md").is_file()


# ── upload / release / sync-pid — mocked B2SHARE REST API ───────────────────

def _fake_response(status_code=200, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data if json_data is not None else {}
    return response


def _prepared_b2share_export(camtrapdp_dir, tmp_path, *, self_contained=False):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "b2share_out"
    args = ["b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)]
    if self_contained:
        args.append("--self-contained")
        with patch("httpx.Client.get", _fake_httpx_get_image):
            result = runner.invoke(app, args)
    else:
        result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return output_dir


def test_b2share_upload_then_release_then_sync_pid_with_epic_pid(camtrapdp_dir, tmp_path, monkeypatch):
    """Mocks the current InvenioRDM-based B2SHARE API (see b2share.py's own
    module docstring on the platform migration) — create draft, request
    community review, upload each file (init/content/commit), submit for
    review, then read back the PID once a moderator would have accepted it
    (here: as soon as submit-review is called, to keep the test simple)."""
    monkeypatch.setenv("B2SHARE_TOKEN", "faketoken")
    output_dir = _prepared_b2share_export(camtrapdp_dir, tmp_path, self_contained=False)

    state = {"reviewed": False}
    draft_record = {"id": "rec-1", "links": {}, "pids": {}}
    reviewed_record = {
        "id": "rec-1",
        "links": {"self_html": "https://trng-b2share.eudat.eu/records/rec-1"},
        "pids": {"epic": {"identifier": "http://hdl.handle.net/11304/deadbeef-1234", "provider": "epic"}},
    }

    def fake_post(url, **kwargs):
        if url.endswith("/records"):
            return _fake_response(201, draft_record)
        if url.endswith("/draft/pids/doi"):
            # this record only ever gets an ePIC PID at release time (via
            # the community), never a DOI — reserving one ahead of upload
            # isn't available here, and upload_to_b2share must treat that
            # as non-fatal and continue without one.
            return _fake_response(400, {"message": "DOI reservation not available"})
        if url.endswith("/draft/files"):
            return _fake_response(201, {})
        if url.endswith("/commit"):
            return _fake_response(200, {})
        if url.endswith("/draft/actions/submit-review"):
            state["reviewed"] = True
            return _fake_response(200, {})
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        return _fake_response(200, {})  # both .../draft/review and .../content

    def fake_get(url, **kwargs):
        return _fake_response(200, reviewed_record if state["reviewed"] else draft_record)

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get):
        upload_result = runner.invoke(app, ["b2share", "upload", "--output-dir", str(output_dir), "--community-id", "uuid-1"])
        assert upload_result.exit_code == 0, upload_result.output

        record = json.loads((output_dir / "b2share_record.json").read_text(encoding="utf-8"))
        assert record["record_id"] == "rec-1"
        assert record["published"] is False

        release_result = runner.invoke(app, ["b2share", "release", "--output-dir", str(output_dir)])
        assert release_result.exit_code == 0, release_result.output

    record = json.loads((output_dir / "b2share_record.json").read_text(encoding="utf-8"))
    assert record["published"] is True
    assert record["pid"] == "http://hdl.handle.net/11304/deadbeef-1234"  # already a full URL, per the real API
    assert record["pid_kind"] == "epic"

    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["identifiers"][0]["value"] == "http://hdl.handle.net/11304/deadbeef-1234"

    hfh_dir = tmp_path / "hfh_out2"
    hfh_dir.mkdir()
    (hfh_dir / "CITATION.cff").write_text(yaml.safe_dump({"cff-version": "1.2.0", "title": "T"}), encoding="utf-8")

    sync_result = runner.invoke(app, ["b2share", "sync-pid", "--b2share-output-dir", str(output_dir), "--hfh-output-dir", str(hfh_dir)])
    assert sync_result.exit_code == 0, sync_result.output

    hfh_citation = yaml.safe_load((hfh_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert hfh_citation["identifiers"][0]["value"] == "http://hdl.handle.net/11304/deadbeef-1234"


def test_b2share_upload_self_contained_uploads_only_the_zip_and_metadata_files(camtrapdp_dir, tmp_path, monkeypatch):
    """Since --self-contained now bundles every image inside camtrapdp.zip
    (see the 'prepare' tests above), 'b2share upload' never uploads images
    individually — it only ever sees the handful of files output_dir has
    left (the zip, README, CITATION.cff, LICENSE, checksums), regardless of
    how many images the dataset actually has. This is what keeps it under
    B2SHARE's 100-files-per-record cap."""
    monkeypatch.setenv("B2SHARE_TOKEN", "faketoken")
    output_dir = _prepared_b2share_export(camtrapdp_dir, tmp_path, self_contained=True)
    expected_filenames = {p.name for p in output_dir.iterdir()}
    assert "camtrapdp.zip" in expected_filenames

    draft_record = {"id": "rec-2", "links": {}, "pids": {}}

    def fake_post(url, **kwargs):
        if url.endswith("/records"):
            return _fake_response(201, draft_record)
        if url.endswith("/draft/pids/doi"):
            return _fake_response(201, {"pids": {"doi": {"identifier": "10.1234/b2share.rec2", "provider": "datacite"}}})
        if url.endswith("/draft/files") or url.endswith("/commit"):
            return _fake_response(201, {})
        raise AssertionError(f"unexpected POST {url}")

    uploaded_filenames = []

    def fake_put(url, **kwargs):
        if "/draft/files/" in url and url.endswith("/content"):
            key = url.split("/draft/files/", 1)[1].rsplit("/content", 1)[0]
            uploaded_filenames.append(key)
        return _fake_response(200, {})

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put):
        result = runner.invoke(app, ["b2share", "upload", "--output-dir", str(output_dir), "--community-id", "uuid-1"])

    assert result.exit_code == 0, result.output
    assert set(uploaded_filenames) == expected_filenames  # never per-image uploads
    assert "m1.jpg" not in uploaded_filenames

    # the DOI, reserved before any file was uploaded, is already baked into
    # the CITATION.cff/README.md that actually got uploaded above.
    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["doi"] == "10.1234/b2share.rec2"
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "https://doi.org/10.1234/b2share.rec2" in readme
    assert "DOI assigned by B2SHARE upon publication" not in readme

    record = json.loads((output_dir / "b2share_record.json").read_text(encoding="utf-8"))
    assert record["pid"] == "10.1234/b2share.rec2"
    assert record["pid_kind"] == "doi"


def test_b2share_upload_without_token_reports_error(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("B2SHARE_TOKEN", raising=False)
    output_dir = _prepared_b2share_export(camtrapdp_dir, tmp_path)

    result = runner.invoke(app, ["b2share", "upload", "--output-dir", str(output_dir), "--community-id", "uuid-1"])

    assert result.exit_code == 1
    assert "No B2SHARE token configured" in result.output


def test_b2share_upload_without_community_id_reports_error(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("B2SHARE_TOKEN", "faketoken")
    output_dir = _prepared_b2share_export(camtrapdp_dir, tmp_path)

    result = runner.invoke(app, ["b2share", "upload", "--output-dir", str(output_dir)])

    assert result.exit_code == 1
    assert "Missing the EUDAT B2SHARE community UUID" in result.output


def test_b2share_sync_pid_reports_pending_when_no_pid_yet(camtrapdp_dir, tmp_path):
    output_dir = _prepared_b2share_export(camtrapdp_dir, tmp_path)
    (output_dir / "b2share_record.json").write_text(json.dumps({
        "record_id": "rec-1", "environment": "sandbox", "self_contained": False,
        "pid": None, "pid_kind": None, "record_url": "https://x", "published": True,
    }), encoding="utf-8")

    result = runner.invoke(app, ["b2share", "sync-pid", "--b2share-output-dir", str(output_dir), "--hfh-output-dir", str(tmp_path / "hfh_out")])

    assert result.exit_code == 0
    assert "pending approval" in result.output
