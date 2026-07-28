"""Unit tests for services.common.download_public_images — media.csv's
filePath can be either an absolute http(s) URL (as delivered by Trapper, or
by an already-published Camtrap DP fetched via a public URL) or a path
relative to input_dir (an already-local, self-contained Camtrap DP package —
the same convention write_local_zip's own generated media.csv uses, e.g.
examples/camtrapdp)."""
import csv
from pathlib import Path
from unittest.mock import patch

from wildintel_publisher.services.common import download_public_images


def _write_media_csv(output_dir: Path, *, file_path: str, file_name: str = "m1.jpg") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "media.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mediaID", "filePath", "fileName"])
        writer.writeheader()
        writer.writerow({"mediaID": "m1", "filePath": file_path, "fileName": file_name})


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


def test_download_public_images_fetches_absolute_urls_over_http(tmp_path):
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    _write_media_csv(output_dir, file_path="https://trapper.example/m1.jpg?rt=tok1")

    with patch("httpx.Client.get", return_value=_FakeResponse(b"remote-bytes")) as mock_get:
        download_public_images(output_dir, input_dir=input_dir)

    mock_get.assert_called_once_with("https://trapper.example/m1.jpg?rt=tok1")
    assert (output_dir / "images" / "m1.jpg").read_bytes() == b"remote-bytes"


def test_download_public_images_copies_relative_filepath_from_input_dir(tmp_path):
    """A locally-sourced, already self-contained Camtrap DP package (see
    examples/camtrapdp) uses filePath values relative to its own directory
    instead of a downloadable URL — mirror mode must copy these, not try to
    fetch them over HTTP (which used to fail for every row, silently
    degrading to link-mode-like behavior)."""
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    (input_dir / "images").mkdir(parents=True)
    (input_dir / "images" / "m1.jpg").write_bytes(b"local-bytes")
    _write_media_csv(output_dir, file_path="images/m1.jpg")

    with patch("httpx.Client.get") as mock_get:
        download_public_images(output_dir, input_dir=input_dir)

    mock_get.assert_not_called()
    assert (output_dir / "images" / "m1.jpg").read_bytes() == b"local-bytes"


def test_download_public_images_reports_a_missing_local_file_as_failed(tmp_path):
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    _write_media_csv(output_dir, file_path="images/missing.jpg", file_name="missing.jpg")

    download_public_images(output_dir, input_dir=input_dir)  # must not raise

    assert not (output_dir / "images" / "missing.jpg").exists()


def test_download_public_images_skips_files_already_present_in_destination(tmp_path):
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    (output_dir / "images").mkdir(parents=True)
    (output_dir / "images" / "m1.jpg").write_bytes(b"already-there")
    _write_media_csv(output_dir, file_path="https://trapper.example/m1.jpg?rt=tok1")

    with patch("httpx.Client.get") as mock_get:
        download_public_images(output_dir, input_dir=input_dir)

    mock_get.assert_not_called()
    assert (output_dir / "images" / "m1.jpg").read_bytes() == b"already-there"
