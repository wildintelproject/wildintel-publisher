"""Unit tests for services.zenodo's pure-logic functions: metadata building,
DOI extraction/priority, publication-state detection, and CITATION.cff
DOI-patching (production vs sandbox)."""
import yaml

from wildintel_publisher.services.zenodo import (
    SANDBOX_DOI_DESCRIPTION,
    _patch_citation_with_doi,
    build_zenodo_metadata,
    extract_reserved_doi,
    is_already_published,
)


def test_build_zenodo_metadata_entity_author():
    metadata = build_zenodo_metadata(
        title="T", description="D", authors=[{"name": "Test Org", "affiliation": ""}],
        license_id="CC-BY-4.0", communities=None, related_identifier_url=None,
    )
    assert metadata["creators"] == [{"name": "Test Org"}]
    assert metadata["license"] == "cc-by-4.0"
    assert metadata["prereserve_doi"] is True
    assert "related_identifiers" not in metadata
    assert "communities" not in metadata


def test_build_zenodo_metadata_person_author_includes_affiliation():
    authors = [{"given_names": "Ada", "family_names": "Lovelace", "affiliation": "Test Uni"}]
    metadata = build_zenodo_metadata(title="T", description="D", authors=authors, license_id="MIT", communities=None, related_identifier_url=None)
    assert metadata["creators"] == [{"name": "Lovelace, Ada", "affiliation": "Test Uni"}]


def test_build_zenodo_metadata_includes_related_identifier_when_url_given():
    metadata = build_zenodo_metadata(
        title="T", description="D", authors=[{"name": "A"}], license_id="MIT",
        communities=None, related_identifier_url="https://huggingface.co/datasets/u/d",
    )
    assert metadata["related_identifiers"] == [
        {"identifier": "https://huggingface.co/datasets/u/d", "relation": "isSupplementTo", "resource_type": "dataset", "scheme": "url"}
    ]


def test_build_zenodo_metadata_parses_comma_separated_communities():
    metadata = build_zenodo_metadata(title="T", description="D", authors=[{"name": "A"}], license_id="MIT", communities="a, b ,c", related_identifier_url=None)
    assert metadata["communities"] == [{"identifier": "a"}, {"identifier": "b"}, {"identifier": "c"}]


def test_build_zenodo_metadata_blank_communities_omitted():
    metadata = build_zenodo_metadata(title="T", description="D", authors=[{"name": "A"}], license_id="MIT", communities="  ", related_identifier_url=None)
    assert "communities" not in metadata


def test_extract_reserved_doi_prefers_prereserve_doi():
    deposition = {"metadata": {"prereserve_doi": {"doi": "10.1/prereserved"}, "doi": "10.1/published"}, "doi": "10.1/top"}
    assert extract_reserved_doi(deposition) == "10.1/prereserved"


def test_extract_reserved_doi_falls_back_to_metadata_doi():
    deposition = {"metadata": {"doi": "10.1/published"}, "doi": "10.1/top"}
    assert extract_reserved_doi(deposition) == "10.1/published"


def test_extract_reserved_doi_falls_back_to_top_level_doi():
    deposition = {"metadata": {}, "doi": "10.1/top"}
    assert extract_reserved_doi(deposition) == "10.1/top"


def test_extract_reserved_doi_returns_none_when_absent():
    assert extract_reserved_doi({"metadata": {}}) is None


def test_is_already_published_true_when_submitted_flag_set():
    assert is_already_published({"submitted": True}) is True


def test_is_already_published_true_when_state_done():
    assert is_already_published({"state": "done"}) is True


def test_is_already_published_true_when_no_publish_link_but_has_record_id():
    assert is_already_published({"links": {}, "record_id": 123}) is True


def test_is_already_published_false_for_fresh_draft():
    assert is_already_published({"links": {"publish": "https://..."}, "state": "unsubmitted"}) is False


def test_patch_citation_with_doi_production_sets_top_level_fields(tmp_path):
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0", "title": "T"}), encoding="utf-8")

    _patch_citation_with_doi(citation_path, doi="10.5281/zenodo.123", record_url="https://zenodo.org/records/123", environment="production")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert data["doi"] == "10.5281/zenodo.123"
    assert data["url"] == "https://zenodo.org/records/123"
    assert "identifiers" not in data


def test_patch_citation_with_doi_sandbox_uses_identifiers_list_not_top_level(tmp_path):
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0", "title": "T"}), encoding="utf-8")

    _patch_citation_with_doi(citation_path, doi="10.5281/zenodo.999", record_url="https://sandbox.zenodo.org/records/999", environment="sandbox")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert "doi" not in data
    assert data["identifiers"] == [{"type": "doi", "value": "10.5281/zenodo.999", "description": SANDBOX_DOI_DESCRIPTION}]
    assert "Sandbox" in data["notes"]


def test_patch_citation_with_doi_sandbox_rerun_is_idempotent(tmp_path):
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0", "title": "T"}), encoding="utf-8")

    _patch_citation_with_doi(citation_path, doi="10.5281/zenodo.111", record_url="https://sandbox.zenodo.org/records/111", environment="sandbox")
    _patch_citation_with_doi(citation_path, doi="10.5281/zenodo.222", record_url="https://sandbox.zenodo.org/records/222", environment="sandbox")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert len(data["identifiers"]) == 1
    assert data["identifiers"][0]["value"] == "10.5281/zenodo.222"


def test_patch_citation_with_doi_no_op_when_file_missing(tmp_path):
    _patch_citation_with_doi(tmp_path / "CITATION.cff", doi="10.5281/x", record_url="https://x", environment="production")  # must not raise
    assert not (tmp_path / "CITATION.cff").exists()
