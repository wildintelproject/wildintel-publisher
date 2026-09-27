"""Unit tests for services.previous_version_service / POST
/api/publish/previous-version — every repository call is faked."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

HFH_REPO = "alice/wildlife"
ZENODO_SANDBOX = "https://sandbox.zenodo.org/api"
ZENODO_PRODUCTION = "https://zenodo.org/api"
B2SHARE_SANDBOX = "https://trng-b2share.eudat.eu/api"


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _citation(**fields) -> str:
    return yaml.safe_dump({"cff-version": "1.2.0", "title": "Wildlife", **fields})


def _response(url: str, status: int = 200, *, json=None, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", url)
    if json is not None:
        return httpx.Response(status, json=json, request=request)
    return httpx.Response(status, text=text, request=request)


def _fake_web(routes: dict):
    """httpx.get replacement: exact URL -> (status, json or text)."""
    def fake_get(url, **kwargs):
        if url not in routes:
            return _response(url, 404, json={"status": 404})
        status, body = routes[url]
        return _response(url, status, json=body) if isinstance(body, dict) else _response(url, status, text=body)
    return fake_get


def _zenodo_routes(api: str, *, latest_id: str, given_ids=(), citation: str, related=None) -> dict:
    latest = {
        "id": int(latest_id), "doi": f"10.5281/zenodo.{latest_id}",
        "links": {"html": f"{api.removesuffix('/api')}/records/{latest_id}"},
        "metadata": {"title": "Wildlife", "related_identifiers": related or []},
    }
    routes = {f"{api}/records/{rid}/versions/latest": (200, latest) for rid in (latest_id, *given_ids)}
    routes[f"{api}/records/{latest_id}/files/CITATION.cff/content"] = (200, citation)
    return routes


def _b2share_routes(*, latest_id: str, citation: str, related=None) -> dict:
    latest = {
        "id": latest_id, "pids": {"doi": {"identifier": f"10.80865/b2share.{latest_id}"}},
        "links": {"self_html": f"https://trng-b2share.eudat.eu/records/{latest_id}"},
        "metadata": {"title": "Wildlife", "related_identifiers": related or []},
    }
    return {
        f"{B2SHARE_SANDBOX}/records/{latest_id}/versions/latest": (200, latest),
        f"{B2SHARE_SANDBOX}/records/{latest_id}/files/CITATION.cff/content": (200, citation),
    }


@pytest.fixture
def fake_hfh(tmp_path):
    """Hugging Face Hub with HFH_REPO tagged 1.0/2.0 and a CITATION.cff the
    test sets through the returned dict."""
    state = {"citation": _citation(), "exists": True}
    api = MagicMock()

    def refs(repo_id, repo_type):
        if not state["exists"]:
            raise RuntimeError("Repository not found")
        return SimpleNamespace(tags=[SimpleNamespace(name="1.0"), SimpleNamespace(name="2.0")])

    api.list_repo_refs.side_effect = refs

    def download(repo_id, filename, repo_type, token=None):
        path = tmp_path / "CITATION.cff"
        path.write_text(state["citation"], encoding="utf-8")
        return str(path)

    with (
        patch("services.previous_version_service.HfApi", return_value=api),
        patch("services.previous_version_service.hf_hub_download", side_effect=download),
    ):
        yield state


@pytest.fixture(autouse=True)
def _sandbox_by_default(monkeypatch):
    from wildintel_publisher.config import Settings

    settings = Settings()
    settings.ZENODO.environment = "sandbox"
    settings.B2SHARE.environment = "sandbox"
    monkeypatch.setattr("services.previous_version_service.load_settings", lambda: settings)


def test_from_hfh_finds_zenodo_and_b2share_through_its_citation(fake_hfh):
    from services.previous_version_service import PreviousVersionRequest, lookup

    fake_hfh["citation"] = _citation(
        version="2.0", doi="10.5281/zenodo.200",
        identifiers=[{"type": "doi", "value": "10.80865/b2share.abcde-12345", "description": "B2SHARE"}],
    )
    routes = {
        **_zenodo_routes(ZENODO_SANDBOX, latest_id="200", citation=_citation(version="2.0")),
        **_b2share_routes(latest_id="abcde-12345", citation=_citation(version="2.0")),
    }
    with patch("httpx.get", side_effect=_fake_web(routes)):
        result = lookup(PreviousVersionRequest(repo="hfh", identifier=f"https://huggingface.co/datasets/{HFH_REPO}"))

    assert result.hfh.repo_id == HFH_REPO and result.hfh.version == "2.0"
    assert result.zenodo.record_id == "200" and result.zenodo.environment == "sandbox"
    assert result.b2share.record_id == "abcde-12345"
    assert result.version == "2.0" and result.title == "Wildlife"
    assert result.warnings == []


def test_from_an_old_zenodo_version_resolves_its_latest_and_follows_the_hfh_link(fake_hfh):
    from services.previous_version_service import PreviousVersionRequest, lookup

    fake_hfh["citation"] = _citation(version="2.0", doi="10.5281/zenodo.200")
    routes = _zenodo_routes(
        ZENODO_SANDBOX, latest_id="200", given_ids=("100",), citation=_citation(version="2.0"),
        related=[{"identifier": f"https://huggingface.co/datasets/{HFH_REPO}", "relation": "isSupplementTo"}],
    )
    with patch("httpx.get", side_effect=_fake_web(routes)):
        result = lookup(PreviousVersionRequest(repo="zenodo", identifier="https://sandbox.zenodo.org/records/100"))

    assert result.zenodo.record_id == "200"  # the LATEST version, not the one given
    assert result.hfh.repo_id == HFH_REPO


def test_a_linked_doi_is_found_in_the_other_environment_when_not_in_the_configured_one(fake_hfh):
    from services.previous_version_service import PreviousVersionRequest, lookup

    fake_hfh["citation"] = _citation(version="2.0", doi="10.5281/zenodo.200")
    routes = _zenodo_routes(ZENODO_PRODUCTION, latest_id="200", citation=_citation(version="2.0"))
    with patch("httpx.get", side_effect=_fake_web(routes)):
        result = lookup(PreviousVersionRequest(repo="hfh", identifier=HFH_REPO))

    assert result.zenodo.environment == "production"


def test_an_unreadable_linked_repository_is_only_a_warning(fake_hfh):
    from services.previous_version_service import PreviousVersionRequest, lookup

    fake_hfh["citation"] = _citation(version="2.0", doi="10.5281/zenodo.999")
    with patch("httpx.get", side_effect=_fake_web({})):
        result = lookup(PreviousVersionRequest(repo="hfh", identifier=HFH_REPO))

    assert result.hfh is not None and result.zenodo is None
    assert len(result.warnings) == 1 and "zenodo" in result.warnings[0]


def test_endpoint_rejects_an_unrecognizable_identifier():
    response = _client().post("/api/publish/previous-version", json={"repo": "zenodo", "identifier": "not-a-record"})
    assert response.status_code == 422
    assert "not a Zenodo record" in response.json()["detail"]


def test_endpoint_reports_404_when_the_starting_repository_cannot_be_read(fake_hfh):
    fake_hfh["exists"] = False
    response = _client().post("/api/publish/previous-version", json={"repo": "hfh", "identifier": HFH_REPO})
    assert response.status_code == 404
    assert HFH_REPO in response.json()["detail"]


@pytest.mark.parametrize(("repo", "identifier", "expected"), [
    ("zenodo", "609036", ("609036", None)),
    ("zenodo", "10.5281/zenodo.609036", ("609036", None)),
    ("zenodo", "https://doi.org/10.5281/zenodo.609036", ("609036", None)),
    ("zenodo", "https://zenodo.org/records/609036", ("609036", "production")),
    ("b2share", "https://trng-b2share.eudat.eu/records/6zdgk-6nw15", ("6zdgk-6nw15", "sandbox")),
    ("b2share", "10.80865/b2share.6zdgk-6nw15", ("6zdgk-6nw15", None)),
    ("hfh", "https://huggingface.co/datasets/alice/wildlife/tree/main", ("alice/wildlife", None)),
])
def test_identifier_normalization(repo, identifier, expected):
    from services.previous_version_service import _normalize

    assert _normalize(repo, identifier) == expected


GBIF_KEY = "2ba77cb1-5c3d-4a9f-a531-63c329de285b"
GBIF_SANDBOX = "https://api.gbif-test.org/v1"


def _gbif_routes(api: str = GBIF_SANDBOX, *, doi: str = "10.15468/abc123") -> dict:
    return {
        f"{api}/dataset/doi/{doi}": (200, {"results": [{"key": GBIF_KEY}]}),
        f"{api}/dataset/{GBIF_KEY}": (200, {"key": GBIF_KEY, "title": "Wildlife", "doi": doi}),
        f"{api}/dataset/{GBIF_KEY}/endpoint": (200, [
            {"type": "CAMTRAP_DP", "url": f"https://huggingface.co/datasets/{HFH_REPO}/resolve/2.0/camtrapdp-remote.zip"},
        ]),
    }


def _fake_web_with_lists(routes: dict):
    """_fake_web, plus list-shaped JSON bodies (GBIF's endpoint list)."""
    base = _fake_web({k: v for k, v in routes.items() if not isinstance(v[1], list)})

    def fake_get(url, **kwargs):
        if url in routes and isinstance(routes[url][1], list):
            return httpx.Response(routes[url][0], json=routes[url][1], request=httpx.Request("GET", url))
        return base(url, **kwargs)
    return fake_get


def test_from_hfh_finds_gbif_through_its_doi(fake_hfh):
    from services.previous_version_service import PreviousVersionRequest, lookup

    fake_hfh["citation"] = _citation(version="2.0", doi="10.15468/abc123")
    with patch("httpx.get", side_effect=_fake_web_with_lists(_gbif_routes())):
        result = lookup(PreviousVersionRequest(repo="hfh", identifier=HFH_REPO))

    assert result.gbif.dataset_key == GBIF_KEY and result.gbif.environment == "sandbox"


def test_from_gbif_follows_its_camtrap_dp_endpoint_to_hfh(fake_hfh):
    from services.previous_version_service import PreviousVersionRequest, lookup

    fake_hfh["citation"] = _citation(version="2.0", doi="10.15468/abc123")
    with patch("httpx.get", side_effect=_fake_web_with_lists(_gbif_routes())):
        result = lookup(PreviousVersionRequest(repo="gbif", identifier=f"https://registry.gbif-test.org/dataset/{GBIF_KEY}"))

    assert result.gbif.dataset_key == GBIF_KEY
    assert result.hfh.repo_id == HFH_REPO and result.version == "2.0"


def test_gbif_identifier_normalization():
    from services.previous_version_service import _normalize

    assert _normalize("gbif", f"https://www.gbif.org/dataset/{GBIF_KEY}") == (GBIF_KEY, "production")
    assert _normalize("gbif", GBIF_KEY.upper()) == (GBIF_KEY, None)
    assert _normalize("gbif", "10.15468/abc123") == ("10.15468/abc123", None)
