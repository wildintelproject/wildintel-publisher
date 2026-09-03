"""Unit tests for services.camtrapdp_adapter.CamtrapDPAdapter's README
template hook and its anonymize_coordinates method — the rest of the
adapter is already exercised end to end by the CLI integration tests
(test_hfh_cli.py/test_zenodo_cli.py/test_b2share_cli.py), which assert on
the rendered README's own content."""
import csv
import zipfile
from pathlib import Path

from wildintel_publisher.services.camtrapdp_adapter import CamtrapDPAdapter


def test_readme_context_has_nothing_extra(tmp_path):
    # Camtrap DP's README fragments (templates/*/_readme-format-camtrapdp.md.j2)
    # need nothing beyond the generic context every product type gets.
    assert CamtrapDPAdapter().readme_context(tmp_path) == {}


def test_checkout_release_noops(tmp_path):
    # Camtrap DP's raw source isn't a git checkout — never raises, never
    # touches the directory.
    result = CamtrapDPAdapter().checkout_release(tmp_path, version="1.0")
    assert result is None
    assert list(tmp_path.iterdir()) == []


def _write_deployments_csv(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "deployments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["deploymentID", "latitude", "longitude"])
        writer.writeheader()
        writer.writerow({"deploymentID": "d1", "latitude": "41.123456", "longitude": "-3.987654"})
    return root


def test_anonymize_coordinates_rounds_deployments_csv_in_place(tmp_path):
    input_dir = _write_deployments_csv(tmp_path)

    CamtrapDPAdapter().anonymize_coordinates(input_dir, decimals=2)

    with (input_dir / "deployments.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["latitude"] == "41.12"
    assert rows[0]["longitude"] == "-3.99"


def _write_media_csv(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "media.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mediaID", "fileName"])
        writer.writeheader()
        writer.writerow({"mediaID": "img001", "fileName": "img001.jpg"})
    return root


def test_randomize_media_ids_replaces_media_csv_ids_in_place(tmp_path):
    input_dir = _write_media_csv(tmp_path)

    CamtrapDPAdapter().randomize_media_ids(input_dir)

    with (input_dir / "media.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["mediaID"] != "img001"


def test_extract_core_files_strips_the_self_contained_zips_root_folder(tmp_path):
    # write_local_zip(embed_images=True) nests every entry under a single
    # root folder (the zip's own stem) so it also works as GBIF's
    # --archive-url — extract_core_files must undo that nesting so
    # target_dir stays flat, same as the "loose files" branch above it.
    output_dir = tmp_path / "build"
    output_dir.mkdir()
    zip_path = output_dir / "camtrapdp.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("camtrapdp/datapackage.json", "{}")
        zf.writestr("camtrapdp/media.csv", "mediaID\nm1\n")
        zf.writestr("camtrapdp/images/m1.jpg", b"fake-bytes")

    target_dir = tmp_path / "chain"
    CamtrapDPAdapter().extract_core_files(output_dir, target_dir)

    assert (target_dir / "datapackage.json").is_file()
    assert (target_dir / "media.csv").is_file()
    assert (target_dir / "images" / "m1.jpg").read_bytes() == b"fake-bytes"
    assert not (target_dir / "camtrapdp").exists()
