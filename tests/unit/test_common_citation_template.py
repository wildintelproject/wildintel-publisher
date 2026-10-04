"""Unit tests for services.common.write_citation's CITATION.cff.j2
rendering — in particular the url/doi/identifiers/notes fields, which are
never populated by write_citation itself in the real pipeline (they get
patched into the already-written YAML afterwards — see hfh.py's
_patch_citation_with_repo_id, zenodo.py's _patch_citation_with_doi,
b2share.py's _patch_citation_with_pid) but are declared on the template/
function signature so what CITATION.cff can eventually contain is visible
without having to know about those patch functions."""
import yaml

from wildintel_publisher.core.config import REPO_ROOT
from wildintel_publisher.core.services import common

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
    assert "contact" not in citation
    assert "preferred-citation" not in citation
    # Never valid CFF fields at the document root (only inside a
    # "reference" object, e.g. preferred-citation) — see resolve_publisher/
    # resolve_copyright_holders's own docstrings.
    assert "publisher" not in citation
    assert "copyright" not in citation


def test_contact_appears_as_its_own_field_when_given(tmp_path):
    citation = _write(tmp_path, contact=[{"name": "Contact Person", "affiliation": "Test Org"}])

    assert citation["contact"] == [{"name": "Contact Person", "affiliation": "Test Org"}]
    # Never folded into authors — CITATION.cff has its own field for this.
    assert citation["authors"] == [{"name": "Alice", "affiliation": "Org"}]


def test_contact_person_style_uses_given_and_family_names(tmp_path):
    citation = _write(tmp_path, contact=[{"given_names": "Jane", "family_names": "Doe", "affiliation": "Org"}])

    assert citation["contact"] == [{"given-names": "Jane", "family-names": "Doe", "affiliation": "Org"}]


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


def test_publisher_and_copyright_render_inside_preferred_citation_not_at_root(tmp_path):
    """CITATION.cff has no top-level "publisher"/"copyright" field (verified
    against the real CFF JSON schema: both only exist inside a "reference"
    object) — write_citation must never write them at the root, only nested
    under preferred-citation, which itself must satisfy CFF's own
    requirements for a reference (authors/title/type)."""
    citation = _write(
        tmp_path,
        publisher={"name": "WildINTEL", "website": "https://wildintel.eu/", "email": "wildintelproject@gmail.com"},
        copyright_holders=["Institute of Nature Conservation PAS"],
    )

    assert "publisher" not in citation
    assert "copyright" not in citation
    pref = citation["preferred-citation"]
    assert pref["type"] == "dataset"
    assert pref["title"] == "T"
    assert pref["authors"] == [{"name": "Alice", "affiliation": "Org"}]
    assert pref["version"] == "1.0"
    assert pref["date-released"] == "2026-01-01"
    assert pref["publisher"] == {"name": "WildINTEL", "website": "https://wildintel.eu/", "email": "wildintelproject@gmail.com"}
    assert pref["copyright"] == "© 2026 Institute of Nature Conservation PAS"


def test_preferred_citation_omitted_when_neither_publisher_nor_copyright_holders_given(tmp_path):
    citation = _write(tmp_path, publisher=None, copyright_holders=[])

    assert "preferred-citation" not in citation


def test_copyright_joins_multiple_rights_holders_under_one_year(tmp_path):
    citation = _write(tmp_path, copyright_holders=["University of Huelva", "Institute of Nature Conservation PAS"])

    assert citation["preferred-citation"]["copyright"] == "© 2026 University of Huelva, Institute of Nature Conservation PAS"
    assert "publisher" not in citation["preferred-citation"]


def test_preferred_citation_publisher_omits_website_and_email_when_absent(tmp_path):
    citation = _write(tmp_path, publisher={"name": "WildINTEL"})

    assert citation["preferred-citation"]["publisher"] == {"name": "WildINTEL"}
