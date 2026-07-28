"""Unit tests for services.common.write_remote_zip/find_camtrap_dp_root —
GBIF's own CAMTRAP_DP crawler requires exactly one root directory once it
unpacks the archive (org.gbif.utils.file.CompressionUtil errors with "More
than one root directory" for a flat zip with four loose files at its own
root, silently treating the whole dataset as empty — no records, no error
visible anywhere in this project), and its own Camtrap DP -> Darwin Core
conversion (inbo/camtrapdp's write_dwc.R) silently keeps only observations
whose observationLevel matches datapackage.json's gbifIngestion.
observationLevel field, DEFAULTING TO "event" when that field is absent —
zeroing out every occurrence for a media-level package like Trapper's own,
again with no error visible anywhere."""
import csv
import json
import zipfile

import pytest

from wildintel_publisher.services.common import find_camtrap_dp_root, write_remote_zip


def _set_observation_level(output_dir, level):
    """Rewrites observations.csv (camtrapdp_dir's own fixture doesn't set
    this column at all) so every row has the given observationLevel — or a
    per-row alternating mix, when `level` is a list."""
    path = output_dir / "observations.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) + ["observationLevel"]
    levels = level if isinstance(level, list) else [level] * len(rows)
    for row, lvl in zip(rows, levels):
        row["observationLevel"] = lvl
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_write_remote_zip_nests_the_four_files_in_a_single_top_level_folder(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)

    zip_path = write_remote_zip(output_dir)

    assert zip_path.name == "camtrapdp-remote.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert names == {
        "camtrapdp-remote/datapackage.json", "camtrapdp-remote/deployments.csv",
        "camtrapdp-remote/media.csv", "camtrapdp-remote/observations.csv",
    }


def test_write_remote_zip_uses_the_given_filename_as_the_folder_name(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)

    zip_path = write_remote_zip(output_dir, zip_filename="custom-name.zip")

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "custom-name/datapackage.json" in names


def test_write_remote_zip_injects_gbif_ingestion_observation_level_when_media_based(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    _set_observation_level(output_dir, "media")

    zip_path = write_remote_zip(output_dir)

    with zipfile.ZipFile(zip_path) as zf:
        datapackage = json.loads(zf.read("camtrapdp-remote/datapackage.json"))
    assert datapackage["gbifIngestion"] == {"observationLevel": "media"}
    # The on-disk datapackage.json every other repo also copies as-is is
    # left untouched — this is a GBIF-only vendor extension.
    on_disk = json.loads((output_dir / "datapackage.json").read_text(encoding="utf-8"))
    assert "gbifIngestion" not in on_disk


def test_write_remote_zip_injects_gbif_ingestion_observation_level_when_event_based(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)
    _set_observation_level(output_dir, "event")

    zip_path = write_remote_zip(output_dir)

    with zipfile.ZipFile(zip_path) as zf:
        datapackage = json.loads(zf.read("camtrapdp-remote/datapackage.json"))
    assert datapackage["gbifIngestion"] == {"observationLevel": "event"}


def test_write_remote_zip_leaves_gbif_ingestion_unset_when_observation_level_column_is_missing(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=False)  # fixture never sets this column

    zip_path = write_remote_zip(output_dir)

    with zipfile.ZipFile(zip_path) as zf:
        datapackage = json.loads(zf.read("camtrapdp-remote/datapackage.json"))
    assert "gbifIngestion" not in datapackage


def test_write_remote_zip_leaves_gbif_ingestion_unset_when_observation_levels_are_mixed(camtrapdp_dir):
    output_dir = camtrapdp_dir("pkg", include_private_media=True)  # 2 observation rows
    _set_observation_level(output_dir, ["media", "event"])

    zip_path = write_remote_zip(output_dir)

    with zipfile.ZipFile(zip_path) as zf:
        datapackage = json.loads(zf.read("camtrapdp-remote/datapackage.json"))
    assert "gbifIngestion" not in datapackage


def test_find_camtrap_dp_root_returns_extract_dir_when_flat(tmp_path):
    (tmp_path / "datapackage.json").write_text("{}", encoding="utf-8")

    assert find_camtrap_dp_root(tmp_path) == tmp_path


def test_find_camtrap_dp_root_descends_into_a_single_nested_folder(tmp_path):
    nested = tmp_path / "camtrapdp-remote"
    nested.mkdir()
    (nested / "datapackage.json").write_text("{}", encoding="utf-8")

    assert find_camtrap_dp_root(tmp_path) == nested


def test_find_camtrap_dp_root_raises_when_datapackage_json_is_nowhere_to_be_found(tmp_path):
    (tmp_path / "some-other-file.txt").write_text("x", encoding="utf-8")

    with pytest.raises(RuntimeError, match="datapackage.json"):
        find_camtrap_dp_root(tmp_path)


def test_find_camtrap_dp_root_raises_when_more_than_one_subdirectory_exists(tmp_path):
    (tmp_path / "folder-a").mkdir()
    (tmp_path / "folder-b").mkdir()
    (tmp_path / "folder-b" / "datapackage.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="datapackage.json"):
        find_camtrap_dp_root(tmp_path)
