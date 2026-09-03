"""Unit tests for services.common.fit_images_to_size — the uniform image
downscale step zenodo/b2share prepare run (Camtrap DP + --self-contained
only) before bundling images/ into camtrapdp.zip, to try to stay under
each repository's own per-file upload cap."""
import os
from pathlib import Path

from PIL import Image

from wildintel_publisher.services.common import fit_images_to_size


def _write_random_jpeg(path: Path, *, width: int, height: int, quality: int = 95) -> None:
    # Random noise compresses poorly (unlike a solid color), so file size
    # scales predictably with resolution — needed to force "over budget"
    # deterministically in these tests.
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    img.save(path, format="JPEG", quality=quality)


def test_fit_images_to_size_noop_when_already_under_budget(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_random_jpeg(images_dir / "m1.jpg", width=200, height=150)
    original_bytes = (images_dir / "m1.jpg").read_bytes()

    fit_images_to_size(images_dir, target_bytes=10 * 1024 * 1024)

    assert (images_dir / "m1.jpg").read_bytes() == original_bytes


def test_fit_images_to_size_resizes_uniformly_when_over_budget(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_random_jpeg(images_dir / "m1.jpg", width=800, height=600)
    _write_random_jpeg(images_dir / "m2.jpg", width=800, height=600)
    original_size = sum((images_dir / n).stat().st_size for n in ("m1.jpg", "m2.jpg"))

    fit_images_to_size(images_dir, target_bytes=original_size // 4, min_edge=100)

    with Image.open(images_dir / "m1.jpg") as img:
        assert img.size[0] < 800 and img.size[1] < 600
    with Image.open(images_dir / "m2.jpg") as img:
        assert img.size[0] < 800 and img.size[1] < 600
    new_size = sum((images_dir / n).stat().st_size for n in ("m1.jpg", "m2.jpg"))
    assert new_size < original_size


def test_fit_images_to_size_never_shrinks_below_min_edge(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_random_jpeg(images_dir / "m1.jpg", width=2000, height=1000)

    fit_images_to_size(images_dir, target_bytes=1, min_edge=300)  # absurdly tight budget

    with Image.open(images_dir / "m1.jpg") as img:
        assert max(img.size) == 300


def test_fit_images_to_size_never_upscales_an_already_small_image(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_random_jpeg(images_dir / "small.jpg", width=100, height=80)
    _write_random_jpeg(images_dir / "big.jpg", width=3000, height=2000)

    fit_images_to_size(images_dir, target_bytes=1, min_edge=640)

    with Image.open(images_dir / "small.jpg") as img:
        assert img.size == (100, 80)


def test_fit_images_to_size_leaves_non_image_files_untouched(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_random_jpeg(images_dir / "m1.jpg", width=2000, height=1500)
    video_bytes = os.urandom(1 * 1024 * 1024)
    (images_dir / "clip.mp4").write_bytes(video_bytes)

    fit_images_to_size(images_dir, target_bytes=1)

    assert (images_dir / "clip.mp4").read_bytes() == video_bytes


def test_fit_images_to_size_noop_for_missing_or_empty_dir(tmp_path):
    fit_images_to_size(tmp_path / "does-not-exist", target_bytes=100)

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    fit_images_to_size(empty_dir, target_bytes=100)
