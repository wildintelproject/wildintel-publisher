"""Unit tests for services.camtrapdp_source.fetch_camtrap_dp_archive — the
same download/zip/validate steps as services.gbif.validate_camtrap_dp_archive,
but persisting the extracted directory instead of discarding it."""
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from wildintel_publisher.services.camtrapdp_source import fetch_camtrap_dp_archive


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
