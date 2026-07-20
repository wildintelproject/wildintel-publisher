"""Unit tests for services.common.write_citation's CITATION.cff.j2
rendering — in particular the url/doi/identifiers/notes fields, which are
never populated by write_citation itself in the real pipeline (they get
patched into the already-written YAML afterwards — see hfh.py's
_patch_citation_with_repo_id, zenodo.py's _patch_citation_with_doi,
b2share.py's _patch_citation_with_pid) but are declared on the template/
function signature so what CITATION.cff can eventually contain is visible
without having to know about those patch functions."""
import yaml

from wildintel_publisher.config import REPO_ROOT
from wildintel_publisher.services import common

CITATION_TEMPLATE_FILE = REPO_ROOT / "templates" / "common" / "CITATION.cff.j2"


def _write(tmp_path, **extra):
    common.write_citation(
        CITATION_TEMPLATE_FILE, tmp_path,
        title="T", message="Cite me", authors=[{"name": "Alice", "affiliation": "Org"}],
        version="1.0", date_released="2026-01-01", license_id="CC-BY-4.0",
        repository_code="https://github.com/wildintelproject/wildintel-publisher",
        **extra,
    )
    return yaml.safe_load((tmp_path / "CITATION.cff").read_text(encoding="utf-8"))


def test_url_doi_identifiers_notes_are_absent_by_default(tmp_path):
    citation = _write(tmp_path)

    assert "url" not in citation
    assert "doi" not in citation
    assert "identifiers" not in citation
    assert "notes" not in citation
    assert "repository-artifact" not in citation


def test_url_and_doi_appear_when_given(tmp_path):
    citation = _write(tmp_path, url="https://huggingface.co/datasets/alice/dataset", doi="10.5281/zenodo.123")

    assert citation["url"] == "https://huggingface.co/datasets/alice/dataset"
    assert citation["doi"] == "10.5281/zenodo.123"
    assert "repository-artifact" not in citation


def test_identifiers_and_notes_appear_when_given(tmp_path):
    citation = _write(
        tmp_path,
        identifiers=[{"type": "doi", "value": "10.5281/zenodo.123", "description": "Zenodo Sandbox DOI"}],
        notes="This CITATION.cff contains a Zenodo Sandbox DOI for workflow testing only.",
    )

    assert citation["identifiers"] == [{"type": "doi", "value": "10.5281/zenodo.123", "description": "Zenodo Sandbox DOI"}]
    assert citation["notes"] == "This CITATION.cff contains a Zenodo Sandbox DOI for workflow testing only."
