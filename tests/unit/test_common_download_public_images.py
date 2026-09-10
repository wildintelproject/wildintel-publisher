"""Unit tests for services.common.download_public_images — media.csv's
filePath can be either an absolute http(s) URL (as delivered by Trapper, or
by an already-published Camtrap DP fetched via a public URL) or a path
relative to input_dir (an already-local, self-contained Camtrap DP package —
the same convention write_local_zip's own generated media.csv uses, e.g.
examples/camtrapdp)."""
import csv
from pathlib import Path
from unittest.mock import patch

from wildintel_publisher.services.common import _image_bucket, download_public_images


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
    assert (output_dir / "images" / _image_bucket("m1.jpg") / "m1.jpg").read_bytes() == b"remote-bytes"


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
    assert (output_dir / "images" / _image_bucket("m1.jpg") / "m1.jpg").read_bytes() == b"local-bytes"


def test_download_public_images_reports_a_missing_local_file_as_failed(tmp_path):
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    _write_media_csv(output_dir, file_path="images/missing.jpg", file_name="missing.jpg")

    download_public_images(output_dir, input_dir=input_dir)  # must not raise

    assert not (output_dir / "images" / _image_bucket("missing.jpg") / "missing.jpg").exists()


def test_download_public_images_skips_files_already_present_in_destination(tmp_path):
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    bucket_dir = output_dir / "images" / _image_bucket("m1.jpg")
    bucket_dir.mkdir(parents=True)
    (bucket_dir / "m1.jpg").write_bytes(b"already-there")
    _write_media_csv(output_dir, file_path="https://trapper.example/m1.jpg?rt=tok1")

    with patch("httpx.Client.get") as mock_get:
        download_public_images(output_dir, input_dir=input_dir)

    mock_get.assert_not_called()
    assert (bucket_dir / "m1.jpg").read_bytes() == b"already-there"


def test_download_public_images_populates_and_uses_the_cache_dir_on_a_miss(tmp_path):
    """cache_dir absent from disk: fetches for real (once) and leaves a copy
    in BOTH the cache and the repo's own destination — see
    services.publish_orchestrator, the only real caller: this is what lets
    a second repo in the same publish reuse it without a second fetch."""
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    cache_dir = tmp_path / "media-cache"
    _write_media_csv(output_dir, file_path="https://trapper.example/m1.jpg?rt=tok1")

    with patch("httpx.Client.get", return_value=_FakeResponse(b"remote-bytes")) as mock_get:
        download_public_images(output_dir, input_dir=input_dir, cache_dir=cache_dir)

    mock_get.assert_called_once()
    bucket = _image_bucket("m1.jpg")
    assert (output_dir / "images" / bucket / "m1.jpg").read_bytes() == b"remote-bytes"
    assert (cache_dir / bucket / "m1.jpg").read_bytes() == b"remote-bytes"


def test_download_public_images_reuses_a_cache_hit_without_touching_the_network(tmp_path):
    """The scenario a shared session-wide cache exists for: repo #2 in a
    multi-repo publish finds repo #1's own already-fetched file in the
    shared cache and just copies it — no second network round-trip."""
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    cache_dir = tmp_path / "media-cache"
    bucket = _image_bucket("m1.jpg")
    (cache_dir / bucket).mkdir(parents=True)
    (cache_dir / bucket / "m1.jpg").write_bytes(b"cached-bytes")
    _write_media_csv(output_dir, file_path="https://trapper.example/m1.jpg?rt=tok1")

    with patch("httpx.Client.get") as mock_get:
        download_public_images(output_dir, input_dir=input_dir, cache_dir=cache_dir)

    mock_get.assert_not_called()
    assert (output_dir / "images" / bucket / "m1.jpg").read_bytes() == b"cached-bytes"


def test_download_public_images_cache_copy_is_independent_not_a_hardlink(tmp_path):
    """Regression guard: a later per-repo resize (fit_images_to_size, run
    in-place on each repo's own output_dir/images/ after this) must never
    reach back into the shared cache — only possible if every copy out of
    (and into) the cache is a REAL, independent copy."""
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    cache_dir = tmp_path / "media-cache"
    bucket = _image_bucket("m1.jpg")
    (cache_dir / bucket).mkdir(parents=True)
    (cache_dir / bucket / "m1.jpg").write_bytes(b"cached-bytes")
    _write_media_csv(output_dir, file_path="https://trapper.example/m1.jpg?rt=tok1")

    with patch("httpx.Client.get"):
        download_public_images(output_dir, input_dir=input_dir, cache_dir=cache_dir)

    destination = output_dir / "images" / bucket / "m1.jpg"
    destination.write_bytes(b"resized-bytes")  # simulates fit_images_to_size mutating it in place
    assert (cache_dir / bucket / "m1.jpg").read_bytes() == b"cached-bytes"  # untouched


def test_download_public_images_copies_relative_filepath_into_cache_too(tmp_path):
    """The local-copy branch (filePath relative to input_dir) also feeds the
    cache, not just the http(s) branch."""
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    cache_dir = tmp_path / "media-cache"
    (input_dir / "images").mkdir(parents=True)
    (input_dir / "images" / "m1.jpg").write_bytes(b"local-bytes")
    _write_media_csv(output_dir, file_path="images/m1.jpg")

    download_public_images(output_dir, input_dir=input_dir, cache_dir=cache_dir)

    bucket = _image_bucket("m1.jpg")
    assert (cache_dir / bucket / "m1.jpg").read_bytes() == b"local-bytes"
    assert (output_dir / "images" / bucket / "m1.jpg").read_bytes() == b"local-bytes"
