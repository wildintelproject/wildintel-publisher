"""Unit tests for common.patch_citation_with_identifier — the generic
DOI/PID patcher shared by zenodo.py/b2share.py's own patchers and by
services.doi_populate (cross-referencing one repo's DOI into another's
CITATION.cff)."""
import yaml

from wildintel_publisher.services.common import patch_citation_with_identifier


def _write(tmp_path, data):
    path = tmp_path / "CITATION.cff"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_doi_becomes_primary_when_none_set_yet(tmp_path):
    path = _write(tmp_path, {"cff-version": "1.2.0"})

    changed = patch_citation_with_identifier(
        path, value="10.5281/zenodo.1", kind="doi", url="https://doi.org/10.5281/zenodo.1", description="Zenodo DOI",
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert changed is True
    assert data["doi"] == "10.5281/zenodo.1"
    assert data["url"] == "https://doi.org/10.5281/zenodo.1"
    assert "identifiers" not in data


def test_doi_goes_to_identifiers_when_primary_already_set(tmp_path):
    path = _write(tmp_path, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})

    patch_citation_with_identifier(
        path, value="10.1234/b2share.1", kind="doi", url="https://doi.org/10.1234/b2share.1", description="B2SHARE DOI",
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["doi"] == "10.5281/zenodo.1"  # untouched
    assert data["identifiers"] == [{"type": "doi", "value": "https://doi.org/10.1234/b2share.1", "description": "B2SHARE DOI"}]


def test_allow_as_primary_false_always_goes_to_identifiers(tmp_path):
    path = _write(tmp_path, {"cff-version": "1.2.0"})

    patch_citation_with_identifier(
        path, value="10.5281/zenodo.999", kind="doi", url=None, description="Sandbox", allow_as_primary=False,
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "doi" not in data
    assert data["identifiers"] == [{"type": "doi", "value": "10.5281/zenodo.999", "description": "Sandbox"}]


def test_non_doi_kind_always_goes_to_identifiers_as_other(tmp_path):
    path = _write(tmp_path, {"cff-version": "1.2.0"})

    patch_citation_with_identifier(
        path, value="11304/deadbeef", kind="epic", url="http://hdl.handle.net/11304/deadbeef", description="B2SHARE PID",
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "doi" not in data
    assert data["identifiers"] == [{"type": "other", "value": "http://hdl.handle.net/11304/deadbeef", "description": "B2SHARE PID"}]


def test_is_a_no_op_when_the_same_doi_is_already_the_top_level_one(tmp_path):
    path = _write(tmp_path, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://doi.org/10.5281/zenodo.1"})

    changed = patch_citation_with_identifier(
        path, value="10.5281/zenodo.1", kind="doi", url="https://doi.org/10.5281/zenodo.1", description="Zenodo DOI",
    )

    assert changed is False


def test_updates_the_url_when_the_same_doi_is_reconfirmed_with_a_different_url(tmp_path):
    """Covers the draft-url -> final-record-url upgrade: zenodo.py patches
    CITATION.cff once at upload time (draft deposit URL) and again at
    release time (final record URL) with the SAME already-reserved DOI —
    the second call must still update the url, not silently no-op just
    because the doi itself didn't change."""
    path = _write(tmp_path, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1", "url": "https://zenodo.org/deposit/1"})

    changed = patch_citation_with_identifier(
        path, value="10.5281/zenodo.1", kind="doi", url="https://zenodo.org/records/1", description="Zenodo DOI",
    )

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert changed is True
    assert data["url"] == "https://zenodo.org/records/1"
    assert "identifiers" not in data


def test_rerun_with_same_description_replaces_rather_than_duplicates(tmp_path):
    path = _write(tmp_path, {"cff-version": "1.2.0", "doi": "10.5281/zenodo.1"})

    patch_citation_with_identifier(path, value="11304/aaaa", kind="epic", url="http://x/1", description="B2SHARE PID")
    patch_citation_with_identifier(path, value="11304/bbbb", kind="epic", url="http://x/2", description="B2SHARE PID")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(data["identifiers"]) == 1
    assert data["identifiers"][0]["value"] == "http://x/2"


def test_returns_false_and_does_not_touch_a_missing_file(tmp_path):
    missing = tmp_path / "CITATION.cff"
    changed = patch_citation_with_identifier(missing, value="10.5281/zenodo.1", kind="doi", url=None, description="Zenodo DOI")
    assert changed is False
    assert not missing.exists()
