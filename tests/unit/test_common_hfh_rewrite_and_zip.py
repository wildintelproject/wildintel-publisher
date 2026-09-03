"""Unit tests for services.common.rewrite_media_filepaths_to_hfh/write_local_zip/checksums."""
import csv
import json
import zipfile
from pathlib import Path

from wildintel_publisher.services.common import (
    rewrite_media_filepaths_to_hfh,
    sha256_file,
    write_checksums,
    write_local_zip,
)


def test_rewrite_media_filepaths_to_hfh_unconditional_when_no_local_images_dir(camtrapdp_dir):
    """'zenodo prepare --hfh-repo-id' (no download) mode: no images/ dir exists
    locally, so every row must be rewritten unconditionally, trusting HFH
    already has (or will have) the file."""
    output_dir = camtrapdp_dir("pkg", include_private_media=False)

    rewritten = rewrite_media_filepaths_to_hfh(output_dir, "someuser/somedataset")

    assert rewritten == 1
    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["filePath"] == "https://huggingface.co/datasets/someuser/somedataset/resolve/main/images/m1.jpg"


def test_rewrite_media_filepaths_to_hfh_skips_rows_missing_local_file(camtrapdp_dir):
    """hfh upload mode: images/ dir exists locally, so only rows whose file
    was actually downloaded there get rewritten."""
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    images_dir = output_dir / "images"
    images_dir.mkdir()
    # m1.jpg intentionally NOT created -> row must be skipped, not rewritten.

    rewritten = rewrite_media_filepaths_to_hfh(output_dir, "someuser/somedataset")

    assert rewritten == 0
    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["filePath"] == "https://trapper.example/m1.jpg?rt=tok1"


def test_rewrite_media_filepaths_to_hfh_rewrites_when_local_file_present(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    images_dir = output_dir / "images"
    images_dir.mkdir()
    (images_dir / "m1.jpg").write_bytes(b"fake")

    rewritten = rewrite_media_filepaths_to_hfh(output_dir, "someuser/somedataset")

    assert rewritten == 1


def test_rewrite_media_filepaths_to_hfh_returns_zero_when_columns_missing(tmp_path: Path):
    media_csv = tmp_path / "media.csv"
    media_csv.write_text("mediaID\nm1\n", encoding="utf-8")
    assert rewrite_media_filepaths_to_hfh(tmp_path, "u/d") == 0


def test_write_local_zip_without_embed_images_leaves_relative_path_for_downloaded_files(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    (output_dir / "images").mkdir()
    (output_dir / "images" / "m1.jpg").write_bytes(b"fake-bytes")

    zip_path = write_local_zip(output_dir, zip_filename="camtrapdp-local.zip")

    assert zip_path.name == "camtrapdp-local.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "images/m1.jpg" not in names  # NOT embedded by default
        with zf.open("media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "images/m1.jpg"
    # the media.csv on disk (outside the zip) keeps its original remote filePath
    with (output_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        disk_rows = list(csv.DictReader(f))
    assert disk_rows[0]["filePath"] == "https://trapper.example/m1.jpg?rt=tok1"


def test_write_local_zip_with_embed_images_bundles_the_image_bytes(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    (output_dir / "images").mkdir()
    (output_dir / "images" / "m1.jpg").write_bytes(b"fake-bytes")

    zip_path = write_local_zip(output_dir, zip_filename="camtrapdp.zip", embed_images=True)

    # embed_images=True nests everything under one root folder (the zip's
    # own stem) so the same archive also works as GBIF's --archive-url — see
    # write_remote_zip's own "single root directory" requirement.
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "camtrapdp/images/m1.jpg" in names
        assert zf.read("camtrapdp/images/m1.jpg") == b"fake-bytes"
        with zf.open("camtrapdp/media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "images/m1.jpg"


def test_write_local_zip_with_embed_images_injects_gbif_ingestion_field(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    (output_dir / "images").mkdir()
    (output_dir / "images" / "m1.jpg").write_bytes(b"fake-bytes")
    with (output_dir / "observations.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["observationID", "mediaID", "observationLevel"])
        writer.writeheader()
        writer.writerow({"observationID": "o1", "mediaID": "m1", "observationLevel": "media"})

    zip_path = write_local_zip(output_dir, zip_filename="camtrapdp.zip", embed_images=True)

    with zipfile.ZipFile(zip_path) as zf:
        datapackage = json.loads(zf.read("camtrapdp/datapackage.json"))
    assert datapackage["gbifIngestion"]["observationLevel"] == "media"


def test_write_local_zip_without_embed_images_stays_flat_at_zip_root(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    (output_dir / "images").mkdir()
    (output_dir / "images" / "m1.jpg").write_bytes(b"fake-bytes")

    zip_path = write_local_zip(output_dir, zip_filename="camtrapdp-local.zip")

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "media.csv" in names
    assert "camtrapdp-local/media.csv" not in names


def test_write_local_zip_keeps_remote_filepath_when_file_never_downloaded(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    # no images/ dir at all

    zip_path = write_local_zip(output_dir)

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("media.csv") as mf:
            rows = list(csv.DictReader(line.decode() for line in mf))
    assert rows[0]["filePath"] == "https://trapper.example/m1.jpg?rt=tok1"


def test_sha256_file_matches_hashlib_reference(tmp_path: Path):
    import hashlib
    path = tmp_path / "f.txt"
    path.write_bytes(b"hello world")
    assert sha256_file(path) == hashlib.sha256(b"hello world").hexdigest()


def test_write_checksums_lists_every_file_except_itself(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    checksum_path = write_checksums(tmp_path)

    content = checksum_path.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) == 2
    assert any(line.endswith("  a.txt") for line in lines)
    assert any(line.endswith("  b.txt") for line in lines)
    assert checksum_path.name not in content


def test_write_checksums_includes_nested_files_with_posix_relative_path(tmp_path: Path):
    nested = tmp_path / "images"
    nested.mkdir()
    (nested / "m1.jpg").write_bytes(b"x")

    checksum_path = write_checksums(tmp_path)

    assert "images/m1.jpg" in checksum_path.read_text(encoding="utf-8")
