"""Unit tests for services.camtrapdp_source.fetch_camtrap_dp_archive (a
public-URL Camtrap DP source — the same download/zip/validate steps as
services.gbif.validate_camtrap_dp_archive, but persisting the extracted
directory instead of discarding it) and resolve_local_camtrapdp_source (a
local-directory Camtrap DP source)."""
import csv
import hashlib
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from wildintel_publisher.core.services.camtrapdp_source import fetch_camtrap_dp_archive, resolve_local_camtrapdp_source


def _fake_stream_response(status_code: int, body: bytes) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.iter_bytes.return_value = [body]
    context_manager = MagicMock()
    context_manager.__enter__.return_value = response
    context_manager.__exit__.return_value = False
    return context_manager


def test_fetch_rejects_non_http_url(tmp_path):
    with pytest.raises(RuntimeError, match="http"):
        fetch_camtrap_dp_archive("ftp://example.org/archive.zip", tmp_path)


def test_fetch_rejects_a_failed_download(tmp_path):
    with patch("httpx.stream", return_value=_fake_stream_response(404, b"")):
        with pytest.raises(RuntimeError, match="Could not download"):
            fetch_camtrap_dp_archive("https://example.org/archive.zip", tmp_path)


def test_fetch_rejects_content_that_is_not_a_zip(tmp_path):
    not_a_zip = json.dumps({"name": "test"}).encode("utf-8")
    with patch("httpx.stream", return_value=_fake_stream_response(200, not_a_zip)):
        with pytest.raises(RuntimeError, match="not a valid zip archive"):
            fetch_camtrap_dp_archive("https://example.org/datapackage.json", tmp_path)


def test_fetch_extracts_and_persists_a_valid_camtrap_dp_zip(camtrapdp_dir, tmp_path):
    # common.validate_camtrap_dp itself is mocked to a no-op by the autouse
    # tests/conftest.py::_mock_camtrap_dp_validation fixture (real
    # frictionless validation needs network access).
    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    output_dir = tmp_path / "output"
    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        result = fetch_camtrap_dp_archive(
            "https://example.org/camtrapdp-remote.zip", output_dir,
        )

    assert result == output_dir / "camtrapdp-remote"
    assert (result / "datapackage.json").is_file()
    assert (result / "media.csv").is_file()


def test_fetch_extracts_a_zip_nested_inside_a_single_top_level_folder(camtrapdp_dir, tmp_path):
    """The real shape services.common.write_remote_zip produces (GBIF's own
    CAMTRAP_DP crawler requires exactly one root directory once it unpacks
    the archive — a flat zip with four loose files unpacks into four
    separate "roots" instead, which GBIF silently treats as an empty
    dataset). find_camtrap_dp_root must resolve into that nested folder."""
    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, f"camtrapdp-remote/{filename}")

    output_dir = tmp_path / "output"
    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        result = fetch_camtrap_dp_archive(
            "https://example.org/camtrapdp-remote.zip", output_dir,
        )

    assert result == output_dir / "camtrapdp-remote"
    assert (result / "datapackage.json").is_file()
    assert (result / "media.csv").is_file()
    # Not double-nested — the persisted directory holds the files directly.
    assert not (result / "camtrapdp-remote").exists()


def test_fetch_reuses_an_existing_extraction_without_re_downloading(tmp_path):
    destination = tmp_path / "output" / "camtrapdp-remote"
    destination.mkdir(parents=True)
    (destination / "datapackage.json").write_text("{}", encoding="utf-8")

    with patch("httpx.stream") as fake_stream:
        result = fetch_camtrap_dp_archive("https://example.org/camtrapdp-remote.zip", tmp_path / "output")

    fake_stream.assert_not_called()
    assert result == destination


def test_resolve_local_source_copies_only_the_four_core_files(camtrapdp_dir, tmp_path):
    source_dir = camtrapdp_dir()
    # A big media file living alongside the core files, as a real local
    # Camtrap DP would have — must NOT be copied.
    (source_dir / "images").mkdir()
    (source_dir / "images" / "m1.jpg").write_bytes(b"not-a-real-image")

    output_dir = tmp_path / "local-source"
    result = resolve_local_camtrapdp_source(source_dir, output_dir)

    assert result == output_dir / hashlib.sha1(str(source_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    assert sorted(p.name for p in result.iterdir()) == ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]


def test_resolve_local_source_decompresses_gzipped_tables(camtrapdp_dir, tmp_path):
    """Regression test: a Trapper export downloaded as a zip and extracted
    by hand (instead of through 'trapper download', which decompresses
    on the way in — see trapper.fetch_camtrapdp_package) keeps its tables
    gzip-compressed. copy_core_camtrapdp_files only looked for the plain
    .csv names and silently skipped the .gz ones, so the working copy ended
    up with just datapackage.json and validate_camtrap_dp then failed with
    an opaque "No such file or directory: .../deployments.csv.gz" — nothing
    actionable, since datapackage.json still referenced the never-copied
    table."""
    import gzip

    source_dir = camtrapdp_dir()
    original_media_csv = (source_dir / "media.csv").read_bytes()
    for filename in ("deployments.csv", "media.csv", "observations.csv"):
        original = source_dir / filename
        with gzip.open(source_dir / f"{filename}.gz", "wb") as f:
            f.write(original.read_bytes())
        original.unlink()

    output_dir = tmp_path / "local-source"
    result = resolve_local_camtrapdp_source(source_dir, output_dir)

    assert sorted(p.name for p in result.iterdir()) == ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]
    assert (result / "media.csv").read_bytes() == original_media_csv
    # the source directory itself is never touched — still gzip-compressed.
    assert (source_dir / "media.csv.gz").is_file()
    assert not (source_dir / "media.csv").exists()


def test_resolve_local_source_patches_trappers_private_license_placeholder(camtrapdp_dir, tmp_path, monkeypatch):
    """Regression test: a Trapper export that never got a real license
    configured server-side keeps Trapper's own "private" placeholder in
    both scopes — 'trapper download' patches that automatically (see
    trapper.fetch_camtrapdp_package), but Local Directory never did, so
    extract_metadata's own resolve_license found no real license at all and
    the wizard had to ask for one by hand, even though downloading the very
    same package with 'trapper download' directly would never have hit
    that."""
    from wildintel_publisher.core.services import camtrapdp_source

    monkeypatch.setattr(camtrapdp_source.settings.CAMTRAPDP, "license_id", "MIT")
    monkeypatch.setattr(camtrapdp_source.settings.CAMTRAPDP, "license_name", "MIT License")
    monkeypatch.setattr(camtrapdp_source.settings.CAMTRAPDP, "license_url", "https://opensource.org/license/mit")

    source_dir = camtrapdp_dir()
    datapackage_path = source_dir / "datapackage.json"
    data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    data["licenses"] = [{"name": "private", "scope": "data"}, {"name": "private", "scope": "media"}]
    datapackage_path.write_text(json.dumps(data), encoding="utf-8")

    output_dir = tmp_path / "local-source"
    result = resolve_local_camtrapdp_source(source_dir, output_dir)

    patched = json.loads((result / "datapackage.json").read_text(encoding="utf-8"))
    scopes = {lic["scope"]: lic["name"] for lic in patched["licenses"]}
    assert scopes == {"data": "MIT", "media": "MIT"}
    # the source directory itself is never touched.
    assert json.loads(datapackage_path.read_text(encoding="utf-8"))["licenses"][0]["name"] == "private"


def test_resolve_local_source_rejects_a_missing_directory(tmp_path):
    with pytest.raises(RuntimeError, match="does not exist"):
        resolve_local_camtrapdp_source(tmp_path / "nope", tmp_path / "output")


def test_resolve_local_source_always_recopies_ignoring_any_stale_destination(camtrapdp_dir, tmp_path):
    source_dir = camtrapdp_dir()
    output_dir = tmp_path / "local-source"
    destination = output_dir / hashlib.sha1(str(source_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    destination.mkdir(parents=True)
    (destination / "stale.txt").write_text("old", encoding="utf-8")

    result = resolve_local_camtrapdp_source(source_dir, output_dir)

    assert result == destination
    assert not (destination / "stale.txt").exists()
    assert (destination / "datapackage.json").is_file()


def test_resolve_local_source_use_hash_subdir_false_writes_straight_into_output_dir(camtrapdp_dir, tmp_path):
    """use_hash_subdir=False is for a caller whose own output_dir is
    already unique per source (the web backend's own session_dir/source —
    see services.camtrapdp_source_service.resolve_local_source) — the hash
    subfolder only exists to dedupe several distinct local sources sharing
    ONE output_dir, which a per-session directory never does."""
    source_dir = camtrapdp_dir()
    output_dir = tmp_path / "session-1" / "source"

    result = resolve_local_camtrapdp_source(source_dir, output_dir, use_hash_subdir=False)

    assert result == output_dir
    assert sorted(p.name for p in result.iterdir()) == ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]


def test_resolve_local_source_never_mutates_the_original_directory(tmp_path):
    """The whole point of this function: generate_metadata_json's
    validate/anonymize/randomize steps, run against the returned working
    copy, must never touch source_dir — regression test for the bug this
    refactor fixes (a local Camtrap DP source used to be mutated in place)."""
    from wildintel_publisher.core.services import product

    source_dir = tmp_path / "original"
    source_dir.mkdir()
    (source_dir / "datapackage.json").write_text("{}", encoding="utf-8")
    with (source_dir / "deployments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["deploymentID", "latitude", "longitude"])
        writer.writeheader()
        writer.writerow({"deploymentID": "d1", "latitude": "41.123456", "longitude": "-3.987654"})
    with (source_dir / "media.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mediaID", "fileName", "filePublic"])
        writer.writeheader()
        writer.writerow({"mediaID": "img001", "fileName": "img001.jpg", "filePublic": "true"})

    original_deployments_bytes = (source_dir / "deployments.csv").read_bytes()
    original_media_bytes = (source_dir / "media.csv").read_bytes()
    original_entries = sorted(p.name for p in source_dir.iterdir())

    output_dir = tmp_path / "local-source"
    working_dir = resolve_local_camtrapdp_source(source_dir, output_dir)
    product.generate_metadata_json(
        product.CAMTRAPDP, working_dir,
        anonymize_coordinates=True, coordinate_decimals=1, randomize_media_ids=True,
    )

    # The working copy DID get mutated (anonymize/randomize actually ran) ...
    with (working_dir / "deployments.csv").open(newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f))[0]["latitude"] == "41.1"
    with (working_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f))[0]["mediaID"] != "img001"

    # ... but the original source_dir is byte-for-byte untouched, and never
    # gained a metadata.json of its own.
    assert (source_dir / "deployments.csv").read_bytes() == original_deployments_bytes
    assert (source_dir / "media.csv").read_bytes() == original_media_bytes
    assert sorted(p.name for p in source_dir.iterdir()) == original_entries


def test_fetch_clear_cache_forces_a_fresh_download(camtrapdp_dir, tmp_path):
    destination = tmp_path / "output" / "camtrapdp-remote"
    destination.mkdir(parents=True)
    (destination / "stale.txt").write_text("old", encoding="utf-8")

    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        result = fetch_camtrap_dp_archive(
            "https://example.org/camtrapdp-remote.zip", tmp_path / "output", clear_cache=True,
        )

    assert not (result / "stale.txt").exists()
    assert (result / "datapackage.json").is_file()
