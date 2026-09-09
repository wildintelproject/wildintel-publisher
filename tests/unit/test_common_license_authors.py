"""Unit tests for services.common.resolve_license/resolve_authors/
resolve_contact/format_apa_*."""
import pytest

from wildintel_publisher.services.common import (
    format_apa_author,
    format_apa_citation,
    resolve_authors,
    resolve_contact,
    resolve_copyright_holders,
    resolve_license,
    resolve_publisher,
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


def test_resolve_authors_treats_a_missing_role_as_contributor():
    # Camtrap DP's own default for an unset role.
    assert resolve_authors([{"title": "No Role"}]) == [{"name": "No Role", "affiliation": ""}]


def test_resolve_authors_excludes_contact_publisher_and_rights_holder():
    contributors = [
        {"title": "Contact Person", "role": "contact"},
        {"title": "WildINTEL", "role": "publisher"},
        {"title": "Some University", "role": "rightsHolder"},
        {"title": "The PI", "role": "principalInvestigator"},
    ]
    assert resolve_authors(contributors) == [{"name": "The PI", "affiliation": ""}]


def test_resolve_authors_raises_when_only_contact_publisher_or_rights_holder():
    contributors = [
        {"title": "Contact Person", "role": "contact"},
        {"title": "WildINTEL", "role": "publisher"},
        {"title": "Some University", "role": "rightsHolder"},
    ]
    with pytest.raises(RuntimeError, match="no 'contributor' with a name"):
        resolve_authors(contributors)


def test_resolve_contact_returns_only_contact_role_contributors():
    contributors = [
        {"title": "Contact Person", "email": "contact@example.org", "role": "contact"},
        {"title": "The PI", "role": "principalInvestigator"},
        {"title": "WildINTEL", "role": "publisher"},
    ]
    assert resolve_contact(contributors) == [{"name": "Contact Person", "affiliation": ""}]


def test_resolve_contact_returns_empty_list_when_none_and_never_raises():
    assert resolve_contact([{"title": "The PI", "role": "principalInvestigator"}]) == []
    assert resolve_contact([]) == []


def test_resolve_publisher_returns_entity_with_website_and_email():
    contributors = [{"title": "WildINTEL", "email": "wildintelproject@gmail.com", "path": "https://wildintel.eu/", "role": "publisher"}]
    assert resolve_publisher(contributors) == {
        "name": "WildINTEL", "website": "https://wildintel.eu/", "email": "wildintelproject@gmail.com",
    }


def test_resolve_publisher_omits_website_and_email_when_absent():
    assert resolve_publisher([{"title": "WildINTEL", "role": "publisher"}]) == {"name": "WildINTEL"}


def test_resolve_publisher_returns_none_when_no_publisher_role():
    assert resolve_publisher([{"title": "The PI", "role": "principalInvestigator"}]) is None


def test_resolve_publisher_returns_none_when_empty():
    assert resolve_publisher([]) is None


def test_resolve_copyright_holders_returns_names_of_rights_holder_role_contributors():
    contributors = [
        {"title": "Institute of Nature Conservation PAS", "role": "rightsHolder"},
        {"title": "The PI", "role": "principalInvestigator"},
    ]
    assert resolve_copyright_holders(contributors) == ["Institute of Nature Conservation PAS"]


def test_resolve_copyright_holders_returns_empty_list_when_none():
    assert resolve_copyright_holders([{"title": "The PI", "role": "principalInvestigator"}]) == []
    assert resolve_copyright_holders([]) == []


def test_a_contributor_with_two_roles_shows_up_wherever_each_role_routes_it():
    """datapackage.json represents "several roles for one contributor" as
    two separate entries sharing the same title, one per role — e.g. the
    rightsHolder institution happens to also be listed as a
    principalInvestigator. Neither resolve_authors nor
    resolve_copyright_holders deduplicates by identity, so that
    organization ends up in BOTH results, exactly as it should."""
    contributors = [
        {"title": "University of Huelva", "role": "principalInvestigator"},
        {"title": "University of Huelva", "role": "rightsHolder"},
        {"title": "WildINTEL", "role": "publisher"},
    ]
    assert resolve_authors(contributors) == [{"name": "University of Huelva", "affiliation": ""}]
    assert resolve_copyright_holders(contributors) == ["University of Huelva"]
    assert resolve_publisher(contributors) == {"name": "WildINTEL"}


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
