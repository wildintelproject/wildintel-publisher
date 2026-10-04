"""Unit tests for services.camtrapdp_adapter.CamtrapDPAdapter's README
template hook and its anonymize_coordinates method — the rest of the
adapter is already exercised end to end by the CLI integration tests
(test_hfh_cli.py/test_zenodo_cli.py/test_b2share_cli.py), which assert on
the rendered README's own content."""
import csv
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

from wildintel_publisher.core.services import common
from wildintel_publisher.core.services.camtrapdp_adapter import CAMTRAPDP_DESCRIPTION_FOOTER, CamtrapDPAdapter


def test_readme_context_reports_hf_discovery_fields_sized_from_media_csv(tmp_path):
    with (tmp_path / common.MEDIA_CSV_FILENAME).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mediaID"])
        writer.writeheader()
        writer.writerows({"mediaID": f"m{i}"} for i in range(3))

    context = CamtrapDPAdapter().readme_context(tmp_path)

    assert context == {
        "task_categories": ["image-classification"],
        "tags": ["wildlife", "camera-trap", "camtrap-dp"],
        "size_category": "n<1K",
    }


def _write_minimal_datapackage(root: Path, *, description) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "datapackage.json").write_text(json.dumps({"title": "T", "description": description}), encoding="utf-8")
    return root


def test_extract_metadata_appends_wildintel_footer_to_a_real_description(tmp_path):
    _write_minimal_datapackage(tmp_path, description="A real description of the dataset.")

    metadata = CamtrapDPAdapter().extract_metadata(tmp_path)

    assert metadata["description"] == f"A real description of the dataset.\n\n{CAMTRAPDP_DESCRIPTION_FOOTER}"


def test_extract_metadata_uses_only_the_footer_when_there_is_no_description(tmp_path):
    _write_minimal_datapackage(tmp_path, description=None)

    metadata = CamtrapDPAdapter().extract_metadata(tmp_path)

    assert metadata["description"] == CAMTRAPDP_DESCRIPTION_FOOTER


def test_extract_metadata_does_not_duplicate_the_footer_if_already_present(tmp_path):
    # Re-running generate_metadata_json (e.g. "Back" then "Next" again in
    # the web wizard) always re-reads datapackage.json's own description
    # from scratch — this only guards against a description that somehow
    # already ends with the footer (e.g. datapackage.json edited by hand).
    _write_minimal_datapackage(tmp_path, description=f"Some text.\n\n{CAMTRAPDP_DESCRIPTION_FOOTER}")

    metadata = CamtrapDPAdapter().extract_metadata(tmp_path)

    assert metadata["description"] == f"Some text.\n\n{CAMTRAPDP_DESCRIPTION_FOOTER}"
    assert metadata["description"].count(CAMTRAPDP_DESCRIPTION_FOOTER) == 1


def test_extract_metadata_splits_contact_from_authors(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "datapackage.json").write_text(json.dumps({
        "title": "T",
        "contributors": [
            {"title": "Contact Person", "role": "contact"},
            {"title": "The PI", "role": "principalInvestigator"},
            {"title": "WildINTEL", "role": "publisher"},
        ],
    }), encoding="utf-8")

    metadata = CamtrapDPAdapter().extract_metadata(tmp_path)

    assert metadata["contact"] == [{"name": "Contact Person", "affiliation": ""}]
    assert metadata["authors"] == [{"name": "The PI", "affiliation": ""}]


def test_extract_metadata_extracts_publisher_and_copyright_holders_from_contributors(tmp_path):
    """publisher/copyright_holders (see common.resolve_publisher/
    resolve_copyright_holders) end up in metadata.json alongside authors/
    contact — a contributor with two roles (here: the same institution as
    both principalInvestigator and rightsHolder) shows up wherever each of
    its own role's entry routes it, with no identity deduplication."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "datapackage.json").write_text(json.dumps({
        "title": "T",
        "contributors": [
            {"title": "University of Huelva", "role": "principalInvestigator"},
            {"title": "University of Huelva", "role": "rightsHolder"},
            {"title": "WildINTEL", "email": "wildintelproject@gmail.com", "path": "https://wildintel.eu/", "role": "publisher"},
        ],
    }), encoding="utf-8")

    metadata = CamtrapDPAdapter().extract_metadata(tmp_path)

    assert metadata["authors"] == [{"name": "University of Huelva", "affiliation": ""}]
    assert metadata["copyright_holders"] == ["University of Huelva"]
    assert metadata["publisher"] == {
        "name": "WildINTEL", "website": "https://wildintel.eu/", "email": "wildintelproject@gmail.com",
    }


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


def _write_minimal_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "datapackage.json").write_text("{}", encoding="utf-8")
    with (root / "media.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mediaID", "filePath", "fileName", "filePublic"])
        writer.writeheader()
        writer.writerow({"mediaID": "m1", "filePath": "images/m1.jpg", "fileName": "m1.jpg", "filePublic": "true"})
    return root


def test_prepare_appends_the_footer_to_the_published_datapackage_json(tmp_path):
    """copy_core_camtrapdp_files copies datapackage.json byte-for-byte, so
    without this the PUBLISHED datapackage.json (the one that actually
    ships to HFH/Zenodo/B2SHARE/GBIF) would never get the same WildINTEL
    attribution paragraph metadata.json's own description already gets (see
    extract_metadata) — regression test for exactly that gap."""
    input_dir = _write_minimal_package(tmp_path / "working")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch("wildintel_publisher.core.services.camtrapdp_adapter.common.validate_camtrap_dp"), \
         patch("wildintel_publisher.core.services.camtrapdp_adapter.common.download_public_images"):
        CamtrapDPAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    output_data = json.loads((output_dir / "datapackage.json").read_text(encoding="utf-8"))
    assert output_data["description"] == CAMTRAPDP_DESCRIPTION_FOOTER
    # input_dir's own datapackage.json is never touched.
    assert (input_dir / "datapackage.json").read_text(encoding="utf-8") == "{}"


def test_prepare_mirrors_from_media_dir_when_given(tmp_path):
    """When input_dir is itself just a working copy of the core files (the
    local-source case — see services.camtrapdp_source.
    resolve_local_camtrapdp_source), media_dir is where the ACTUAL images
    referenced by a relative filePath live — the mirror step must read from
    there, not from input_dir."""
    input_dir = _write_minimal_package(tmp_path / "working")
    media_dir = tmp_path / "original"  # never gets core files copied into it
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch("wildintel_publisher.core.services.camtrapdp_adapter.common.validate_camtrap_dp"), \
         patch("wildintel_publisher.core.services.camtrapdp_adapter.common.download_public_images") as mock_download:
        CamtrapDPAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60, media_dir=media_dir)

    mock_download.assert_called_once_with(output_dir, input_dir=media_dir, timeout=60, cache_dir=None)


def test_prepare_mirrors_from_input_dir_when_media_dir_not_given(tmp_path):
    """Unchanged default behavior (URL/Trapper/CLI sources) — no media_dir
    means input_dir IS where the media actually lives."""
    input_dir = _write_minimal_package(tmp_path / "working")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch("wildintel_publisher.core.services.camtrapdp_adapter.common.validate_camtrap_dp"), \
         patch("wildintel_publisher.core.services.camtrapdp_adapter.common.download_public_images") as mock_download:
        CamtrapDPAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    mock_download.assert_called_once_with(output_dir, input_dir=input_dir, timeout=60, cache_dir=None)


def test_prepare_passes_media_cache_dir_through_to_download_public_images(tmp_path):
    """A multi-repo publish (see services.publish_orchestrator) passes the
    same media_cache_dir for every repo so download_public_images can reuse
    an earlier repo's own already-fetched images — see its own docstring."""
    input_dir = _write_minimal_package(tmp_path / "working")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    cache_dir = tmp_path / "media-cache"

    with patch("wildintel_publisher.core.services.camtrapdp_adapter.common.validate_camtrap_dp"), \
         patch("wildintel_publisher.core.services.camtrapdp_adapter.common.download_public_images") as mock_download:
        CamtrapDPAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60, media_cache_dir=cache_dir)

    mock_download.assert_called_once_with(output_dir, input_dir=input_dir, timeout=60, cache_dir=cache_dir)


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
