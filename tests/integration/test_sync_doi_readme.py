"""Integration tests for zenodo.py/b2share.py/gbif.py's own sync_doi_to_hfh/
sync_pid_to_hfh also patching an already-prepared HFH export's README.md
'## Citation' section (see common.patch_readme_citation_url) — not just its
CITATION.cff, closing the gap services.doi_populate's own module docstring
used to call out ("HFH todavía no [tiene marcador], así que de momento su
README no refleja el DOI cruzado, solo su CITATION.cff")."""
import json

from wildintel_publisher.config import HFHSettings
from wildintel_publisher.services import b2share, gbif, hfh, zenodo


def _prepared_hfh_dir(camtrapdp_dir, tmp_path, name="hfh_out"):
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / name
    hfh.prepare_hfh_export(
        input_dir=input_dir, output_dir=output_dir, metadata=HFHSettings(), mirror_images=False,
    )
    return output_dir


def test_zenodo_sync_doi_to_hfh_patches_the_readme_in_production(camtrapdp_dir, tmp_path):
    hfh_dir = _prepared_hfh_dir(camtrapdp_dir, tmp_path)
    zenodo_dir = tmp_path / "zenodo_out"
    zenodo_dir.mkdir()
    (zenodo_dir / zenodo.RECORD_FILENAME).write_text(json.dumps({
        "doi": "10.5281/zenodo.1", "record_url": "https://zenodo.org/records/1",
        "environment": "production", "published": True,
    }), encoding="utf-8")

    doi = zenodo.sync_doi_to_hfh(zenodo_output_dir=zenodo_dir, hfh_output_dir=hfh_dir)

    assert doi == "10.5281/zenodo.1"
    readme = (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8")
    assert "https://zenodo.org/records/1" in readme


def test_zenodo_sync_doi_to_hfh_never_patches_the_readme_from_sandbox(camtrapdp_dir, tmp_path):
    hfh_dir = _prepared_hfh_dir(camtrapdp_dir, tmp_path)
    original_readme = (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8")
    zenodo_dir = tmp_path / "zenodo_out"
    zenodo_dir.mkdir()
    (zenodo_dir / zenodo.RECORD_FILENAME).write_text(json.dumps({
        "doi": "10.5072/zenodo.1", "record_url": "https://sandbox.zenodo.org/records/1",
        "environment": "sandbox", "published": True,
    }), encoding="utf-8")

    zenodo.sync_doi_to_hfh(zenodo_output_dir=zenodo_dir, hfh_output_dir=hfh_dir)

    assert (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8") == original_readme


def test_b2share_sync_pid_to_hfh_patches_the_readme(camtrapdp_dir, tmp_path):
    hfh_dir = _prepared_hfh_dir(camtrapdp_dir, tmp_path)
    b2share_dir = tmp_path / "b2share_out"
    b2share_dir.mkdir()
    (b2share_dir / b2share.RECORD_FILENAME).write_text(json.dumps({
        "pid": "10.1234/b2share.1", "pid_kind": "doi", "record_url": "https://b2share.eudat.eu/records/1",
        "environment": "production",
    }), encoding="utf-8")

    pid = b2share.sync_pid_to_hfh(b2share_output_dir=b2share_dir, hfh_output_dir=hfh_dir)

    assert pid == "10.1234/b2share.1"
    readme = (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8")
    assert "https://b2share.eudat.eu/records/1" in readme or "10.1234/b2share.1" in readme


def test_gbif_sync_doi_to_hfh_patches_the_readme(camtrapdp_dir, tmp_path):
    hfh_dir = _prepared_hfh_dir(camtrapdp_dir, tmp_path)
    gbif_dir = tmp_path / "gbif_out"
    gbif_dir.mkdir()
    (gbif_dir / gbif.RECORD_FILENAME).write_text(json.dumps({
        "doi": "10.21373/eet8jz", "dataset_page_url": "https://registry.gbif-test.org/dataset/abc-123",
    }), encoding="utf-8")

    doi = gbif.sync_doi_to_hfh(gbif_output_dir=gbif_dir, hfh_output_dir=hfh_dir)

    assert doi == "10.21373/eet8jz"
    readme = (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8")
    assert "https://registry.gbif-test.org/dataset/abc-123" in readme


def test_gbif_sync_doi_to_hfh_raises_when_no_doi_and_leaves_readme_untouched(camtrapdp_dir, tmp_path):
    hfh_dir = _prepared_hfh_dir(camtrapdp_dir, tmp_path)
    original_readme = (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8")
    gbif_dir = tmp_path / "gbif_out"
    gbif_dir.mkdir()
    (gbif_dir / gbif.RECORD_FILENAME).write_text(json.dumps({
        "dataset_page_url": "https://registry.gbif-test.org/dataset/abc-123",
    }), encoding="utf-8")

    try:
        gbif.sync_doi_to_hfh(gbif_output_dir=gbif_dir, hfh_output_dir=hfh_dir)
        raised = False
    except RuntimeError:
        raised = True

    assert raised
    assert (hfh_dir / hfh.README_FILENAME).read_text(encoding="utf-8") == original_readme
