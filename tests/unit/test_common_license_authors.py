"""Unit tests for services.common.resolve_license/resolve_authors/format_apa_*."""
import pytest

from wildintel_publisher.services.common import (
    format_apa_author,
    format_apa_citation,
    resolve_authors,
    resolve_license,
)


def test_resolve_license_finds_first_real_license():
    licenses = [
        {"name": "private", "scope": "data"},
        {"name": "CC-BY-4.0", "title": "Creative Commons Attribution 4.0", "path": "https://creativecommons.org/licenses/by/4.0/", "scope": "media"},
    ]
    result = resolve_license(licenses)
    assert result == {"id": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}


def test_resolve_license_falls_back_to_name_when_no_title():
    result = resolve_license([{"name": "CC0-1.0", "path": "https://creativecommons.org/publicdomain/zero/1.0/"}])
    assert result["name"] == "CC0-1.0"


def test_resolve_license_raises_when_only_private_placeholders():
    with pytest.raises(RuntimeError, match="no real license"):
        resolve_license([{"name": "private", "scope": "data"}, {"name": "private", "scope": "media"}])


def test_resolve_license_raises_when_empty():
    with pytest.raises(RuntimeError):
        resolve_license([])


def test_resolve_license_ignores_non_dict_entries():
    with pytest.raises(RuntimeError):
        resolve_license(["not-a-dict", None])


def test_resolve_authors_converts_contributors_to_entity_authors():
    contributors = [{"title": "Jane Doe", "organization": "Test Org", "role": "principalInvestigator"}]
    assert resolve_authors(contributors) == [{"name": "Jane Doe", "affiliation": "Test Org"}]


def test_resolve_authors_skips_contributors_without_title():
    contributors = [{"organization": "No Name Org"}, {"title": "Real Person", "organization": ""}]
    assert resolve_authors(contributors) == [{"name": "Real Person", "affiliation": ""}]


def test_resolve_authors_raises_when_no_named_contributor():
    with pytest.raises(RuntimeError, match="no 'contributor' with a name"):
        resolve_authors([{"organization": "Org Only"}])


def test_resolve_authors_raises_when_empty():
    with pytest.raises(RuntimeError):
        resolve_authors([])


def test_format_apa_author_entity_uses_name_as_is():
    assert format_apa_author({"name": "Jane Doe"}) == "Jane Doe"


def test_format_apa_author_person_formats_as_family_comma_initials():
    author = {"given_names": "Ada Marie", "family_names": "Lovelace"}
    assert format_apa_author(author) == "Lovelace, A. M."


def test_format_apa_citation_single_author():
    citation = format_apa_citation(
        authors=[{"name": "Jane Doe"}], title="Test Dataset", version="1.0",
        date_released="2026-07-16", publisher="Zenodo", url="https://example.org/record/1",
    )
    assert citation == "Jane Doe (2026). *Test Dataset* (Version 1.0) [Data set]. Zenodo. https://example.org/record/1"


def test_format_apa_citation_two_authors_joined_with_ampersand():
    authors = [{"name": "Author One"}, {"name": "Author Two"}]
    citation = format_apa_citation(authors=authors, title="T", version="1.0", date_released="2026-01-01", publisher="P", url="U")
    assert citation.startswith("Author One & Author Two (2026)")


def test_format_apa_citation_three_or_more_authors_oxford_comma_ampersand():
    authors = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    citation = format_apa_citation(authors=authors, title="T", version="1.0", date_released="2026-01-01", publisher="P", url="U")
    assert citation.startswith("A, B, & C (2026)")


def test_format_apa_citation_missing_date_uses_nd():
    citation = format_apa_citation(authors=[{"name": "A"}], title="T", version="1.0", date_released="", publisher="P", url="U")
    assert "(n.d.)" in citation
