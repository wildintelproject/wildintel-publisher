"""Unit tests for services.b2share's pure-logic functions: PID extraction
(DOI vs ePIC Handle, from InvenioRDM's record["pids"] shape), metadata
building (InvenioRDM record body), and CITATION.cff PID-patching."""
import yaml

from wildintel_publisher.services.b2share import (
    B2SHARE_PID_DESCRIPTION,
    _patch_citation_with_pid,
    build_b2share_metadata,
    build_pid_url,
    build_record_url,
    extract_pid,
)


def test_extract_pid_prefers_doi_and_tags_kind_doi():
    record = {"pids": {"doi": {"identifier": "10.1234/abcd"}, "epic": {"identifier": "11304/x"}}}
    assert extract_pid(record) == ("10.1234/abcd", "doi")


def test_extract_pid_falls_back_to_epic_pid():
    record = {"pids": {"epic": {"identifier": "11304/deadbeef"}}}
    assert extract_pid(record) == ("11304/deadbeef", "epic")


def test_extract_pid_returns_none_when_neither_present():
    assert extract_pid({"pids": {}}) == (None, None)
    assert extract_pid({}) == (None, None)


def test_build_pid_url_doi_uses_doi_org_resolver():
    assert build_pid_url("10.1234/abcd", "doi") == "https://doi.org/10.1234/abcd"


def test_build_pid_url_epic_uses_hdl_handle_net_resolver():
    """The bug fix: an ePIC Handle PID must NOT be resolved via doi.org."""
    assert build_pid_url("11304/deadbeef", "epic") == "http://hdl.handle.net/11304/deadbeef"


def test_build_pid_url_passes_through_when_already_a_url():
    """InvenioRDM's own epic.identifier is already a full URL — build_pid_url
    must not re-wrap it."""
    assert build_pid_url("http://hdl.handle.net/11304/deadbeef", "epic") == "http://hdl.handle.net/11304/deadbeef"
    assert build_pid_url("https://doi.org/10.1234/x", "doi") == "https://doi.org/10.1234/x"


def test_build_pid_url_returns_none_when_no_pid():
    assert build_pid_url(None, "doi") is None


def test_build_record_url_prefers_self_html_link():
    record = {"links": {"self_html": "https://b2share.eudat.eu/records/abc"}, "id": "abc"}
    assert build_record_url("https://b2share.eudat.eu", record) == "https://b2share.eudat.eu/records/abc"


def test_build_record_url_falls_back_to_constructed_url():
    record = {"links": {}, "id": "abc"}
    assert build_record_url("https://b2share.eudat.eu", record) == "https://b2share.eudat.eu/records/abc"


def test_build_b2share_metadata_top_level_shape():
    body = build_b2share_metadata(
        title="T", description="D", authors=[{"name": "Test Org"}], license_id="CC-BY-4.0",
        related_identifier_url="https://huggingface.co/datasets/u/d",
    )
    assert body["access"] == {"record": "public", "files": "public"}
    assert body["files"] == {"enabled": True}
    metadata = body["metadata"]
    assert metadata["title"] == "T"
    assert metadata["description"] == "D"
    assert metadata["resource_types"] == [{"id": "dataset"}]
    assert metadata["rights"] == [{"id": "cc-by-4.0"}]  # SPDX lowercase id
    assert metadata["creators"] == [{"person_or_org": {"type": "organizational", "name": "Test Org"}}]
    assert metadata["related_identifiers"] == [{
        "identifier": "https://huggingface.co/datasets/u/d",
        "scheme": "url",
        "relation_type": {"id": "isidenticalto"},
    }]


def test_build_b2share_metadata_person_author_format():
    authors = [{"given_names": "Ada", "family_names": "Lovelace"}]
    body = build_b2share_metadata(title="T", description="D", authors=authors, license_id="MIT", related_identifier_url=None)
    metadata = body["metadata"]
    assert metadata["creators"] == [{
        "person_or_org": {"type": "personal", "given_name": "Ada", "family_name": "Lovelace", "name": "Lovelace, Ada"}
    }]
    assert "related_identifiers" not in metadata


def test_build_b2share_metadata_includes_affiliation_when_given():
    authors = [{"name": "Ada", "affiliation": "Some Org"}]
    body = build_b2share_metadata(title="T", description="D", authors=authors, license_id="MIT", related_identifier_url=None)
    assert body["metadata"]["creators"][0]["affiliations"] == [{"name": "Some Org"}]


def test_patch_citation_with_pid_doi_sets_top_level_when_no_existing_doi(tmp_path):
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0"}), encoding="utf-8")

    _patch_citation_with_pid(citation_path, pid="10.1234/abcd", pid_kind="doi", record_url="https://b2share.eudat.eu/records/1")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert data["doi"] == "10.1234/abcd"
    assert data["url"] == "https://doi.org/10.1234/abcd"


def test_patch_citation_with_pid_epic_always_goes_to_identifiers(tmp_path):
    """An ePIC Handle is not a DOI, so even with no pre-existing doi field it
    must go into identifiers, not overwrite the top-level doi field."""
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0"}), encoding="utf-8")

    _patch_citation_with_pid(citation_path, pid="11304/deadbeef", pid_kind="epic", record_url="https://b2share.eudat.eu/records/1")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert "doi" not in data
    assert data["identifiers"] == [{"type": "other", "value": "http://hdl.handle.net/11304/deadbeef", "description": B2SHARE_PID_DESCRIPTION}]


def test_patch_citation_with_pid_does_not_overwrite_existing_doi(tmp_path):
    """If Zenodo already set the main doi field, B2SHARE's PID must be added
    to identifiers instead of clobbering it — different platforms, different scope."""
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"}), encoding="utf-8")

    _patch_citation_with_pid(citation_path, pid="10.1234/abcd", pid_kind="doi", record_url="https://b2share.eudat.eu/records/1")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert data["doi"] == "10.5281/zenodo.1"  # untouched
    assert data["identifiers"][0]["value"] == "https://doi.org/10.1234/abcd"


def test_patch_citation_with_pid_is_a_no_op_when_the_same_doi_is_already_the_top_level_one(tmp_path):
    """Covers the DOI-reserved-ahead-of-upload flow: upload_to_b2share
    already patches CITATION.cff's top-level doi as soon as it reserves it,
    so release_on_b2share's own later call with that same DOI must not
    duplicate it into identifiers too."""
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(
        yaml.safe_dump({"cff-version": "1.2.0", "doi": "10.1234/abcd", "url": "https://doi.org/10.1234/abcd"}),
        encoding="utf-8",
    )

    _patch_citation_with_pid(citation_path, pid="10.1234/abcd", pid_kind="doi", record_url="https://b2share.eudat.eu/records/1")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert data["doi"] == "10.1234/abcd"
    assert "identifiers" not in data


def test_patch_citation_with_pid_rerun_is_idempotent(tmp_path):
    citation_path = tmp_path / "CITATION.cff"
    citation_path.write_text(yaml.safe_dump({"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"}), encoding="utf-8")

    _patch_citation_with_pid(citation_path, pid="11304/aaaa", pid_kind="epic", record_url="https://x/1")
    _patch_citation_with_pid(citation_path, pid="11304/bbbb", pid_kind="epic", record_url="https://x/2")

    data = yaml.safe_load(citation_path.read_text(encoding="utf-8"))
    assert len(data["identifiers"]) == 1
    assert data["identifiers"][0]["value"] == "http://hdl.handle.net/11304/bbbb"
