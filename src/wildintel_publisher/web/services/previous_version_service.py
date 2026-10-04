"""Finds an already-published dataset's latest version on every repository,
from any ONE identifier the user knows — for the wizard's "new version of
an already published dataset" choice (see WizardPage's metadata step).

The repositories point at each other through what this tool itself
publishes: Hugging Face Hub's CITATION.cff carries Zenodo's DOI (and
B2SHARE's/GBIF's, as alternate identifiers — or GBIF's as the primary one);
Zenodo/B2SHARE's own CITATION.cff carry each other's; GBIF's CAMTRAP_DP
endpoint is the archive on the Hugging Face Hub dataset; and Zenodo/
B2SHARE records' related identifiers point at the Hugging Face Hub dataset (see publish_orchestrator's own
_related_hfh_repo_id — only for records published since that link was
added). lookup() follows those links, one hop at a time, until nothing new
turns up. Zenodo and B2SHARE always resolve to the LATEST version of the
record found, whichever version's id or DOI led there — a new version must
be created from it.

Everything here is read-only and uses public endpoints, except Hugging Face
Hub, where the saved token (if any) lets private datasets be found too."""
from __future__ import annotations

import re
from typing import Literal, Optional

import httpx
import yaml
from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel, Field

from wildintel_publisher.core.config import load_settings
from wildintel_publisher.core.services import b2share as b2share_cli
from wildintel_publisher.core.services import gbif as gbif_cli
from wildintel_publisher.core.services import zenodo as zenodo_cli

Repo = Literal["hfh", "zenodo", "b2share", "gbif"]
Environment = Literal["sandbox", "production"]

CITATION_FILENAME = "CITATION.cff"
TIMEOUT = 30

_HFH_URL = re.compile(r"huggingface\.co/datasets/([\w.-]+/[\w.-]+)")
_ZENODO_DOI = re.compile(r"^10\.\d{4,9}/zenodo\.(\d+)$", re.IGNORECASE)
_ZENODO_URL = re.compile(r"(sandbox\.)?zenodo\.org/(?:records?|deposit|uploads)/(\d+)")
_B2SHARE_DOI = re.compile(r"^10\.\d{4,9}/b2share\.([a-z0-9]{5}-[a-z0-9]{5})$", re.IGNORECASE)
_B2SHARE_URL = re.compile(r"(trng-)?b2share\.eudat\.eu/records/([a-z0-9]{5}-[a-z0-9]{5})")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_GBIF_URL = re.compile(rf"(gbif-test\.org|gbif\.org)/(?:v1/)?dataset/({_UUID})", re.IGNORECASE)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


class PreviousVersionRequest(BaseModel):
    repo: Repo
    # A repo_id ("owner/name") for Hugging Face Hub; a record id for
    # Zenodo/B2SHARE; a dataset key (UUID) for GBIF — or, for any of them,
    # its URL or DOI.
    identifier: str = Field(min_length=1)


class FoundHfh(BaseModel):
    repo_id: str
    url: str
    # Its highest version tag — the version last published there.
    version: Optional[str] = None


class FoundRecord(BaseModel):
    # Always the LATEST version's own record id (see the module docstring).
    record_id: str
    environment: Environment
    url: str
    doi: Optional[str] = None
    title: Optional[str] = None
    version: Optional[str] = None


class FoundGbif(BaseModel):
    """GBIF datasets have no versions of their own: a new version updates
    this same dataset (its endpoint and metadata) — see
    gbif.register_gbif_dataset's own dataset_key."""

    dataset_key: str
    environment: Environment
    url: str
    doi: Optional[str] = None
    title: Optional[str] = None


class PreviousVersion(BaseModel):
    title: Optional[str] = None
    # The version last published — see _highest_version.
    version: Optional[str] = None
    hfh: Optional[FoundHfh] = None
    zenodo: Optional[FoundRecord] = None
    b2share: Optional[FoundRecord] = None
    gbif: Optional[FoundGbif] = None
    warnings: list[str] = Field(default_factory=list)


class _Citation(BaseModel):
    """What lookup() needs out of a CITATION.cff this tool wrote."""

    title: Optional[str] = None
    version: Optional[str] = None
    dois: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> "_Citation":
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            return cls()
        dois = [str(data["doi"])] if data.get("doi") else []
        for ident in data.get("identifiers") or []:
            if isinstance(ident, dict) and ident.get("type") == "doi" and ident.get("value"):
                dois.append(str(ident["value"]))
        urls = [str(data[key]) for key in ("url", "repository") if data.get(key)]
        version = data.get("version")
        return cls(
            title=data.get("title"), version=str(version) if version is not None else None, dois=dois, urls=urls,
        )


def _version_key(version: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"[.\-]", version.lstrip("vV")))


def highest_version(versions: list[Optional[str]]) -> Optional[str]:
    known = [v for v in versions if v]
    if not known:
        return None
    try:
        return max(known, key=_version_key)
    except TypeError:  # mixed numeric/text parts — can't order them
        return known[0]


# ── one repository at a time ──

class _Visit(BaseModel):
    """One repository's own findings, plus the other repositories it points
    at (repo -> identifier, environment when known)."""

    title: Optional[str] = None
    links: list[tuple[Repo, str, Optional[Environment]]] = Field(default_factory=list)


def _links_from(citation: _Citation, related_urls: list[str]) -> list[tuple[Repo, str, Optional[Environment]]]:
    links: list[tuple[Repo, str, Optional[Environment]]] = []
    for doi in citation.dois:
        if match := _ZENODO_DOI.match(doi):
            links.append(("zenodo", match.group(1), None))
        elif match := _B2SHARE_DOI.match(doi):
            links.append(("b2share", match.group(1), None))
        else:
            # Any other DOI this tool cross-references is GBIF's own (see
            # gbif.sync_doi_to_hfh) — _visit_gbif resolves it to its key.
            links.append(("gbif", doi, None))
    for url in [*citation.urls, *related_urls]:
        if match := _HFH_URL.search(url):
            links.append(("hfh", match.group(1), None))
    return links


def _visit_hfh(repo_id: str, result: PreviousVersion) -> _Visit:
    token = load_settings().HFH.token or None
    api = HfApi(token=token)
    tags = [tag.name for tag in api.list_repo_refs(repo_id, repo_type="dataset").tags]
    result.hfh = FoundHfh(
        repo_id=repo_id, url=f"https://huggingface.co/datasets/{repo_id}", version=highest_version(tags),
    )
    path = hf_hub_download(repo_id, CITATION_FILENAME, repo_type="dataset", token=token)
    with open(path, encoding="utf-8") as fh:
        citation = _Citation.parse(fh.read())
    return _Visit(title=citation.title, links=_links_from(citation, []))


def _get_json(url: str) -> dict:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    if response.status_code == 404:
        raise RuntimeError(f"{url} not found.")
    response.raise_for_status()
    return response.json()


def _get_citation(url: str) -> _Citation:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    return _Citation.parse(response.text) if response.status_code == 200 else _Citation()


def _visit_zenodo(record_id: str, environment: Environment, result: PreviousVersion) -> _Visit:
    api = zenodo_cli._api_base_url(environment)
    latest = _get_json(f"{api}/records/{record_id}/versions/latest")
    latest_id = str(latest["id"])
    metadata = latest.get("metadata") or {}
    citation = _get_citation(f"{api}/records/{latest_id}/files/{CITATION_FILENAME}/content")
    result.zenodo = FoundRecord(
        record_id=latest_id, environment=environment,
        url=(latest.get("links") or {}).get("html") or f"{zenodo_cli._base_url(environment)}/records/{latest_id}",
        doi=latest.get("doi") or metadata.get("doi"), title=metadata.get("title"),
        version=metadata.get("version") or citation.version,
    )
    related = [str(r.get("identifier", "")) for r in metadata.get("related_identifiers") or [] if isinstance(r, dict)]
    return _Visit(title=metadata.get("title"), links=_links_from(citation, related))


def _visit_b2share(record_id: str, environment: Environment, result: PreviousVersion) -> _Visit:
    api = b2share_cli._api_base_url(environment)
    latest = _get_json(f"{api}/records/{record_id}/versions/latest")
    latest_id = str(latest["id"])
    metadata = latest.get("metadata") or {}
    citation = _get_citation(f"{api}/records/{latest_id}/files/{CITATION_FILENAME}/content")
    pid, _ = b2share_cli.extract_pid(latest)
    result.b2share = FoundRecord(
        record_id=latest_id, environment=environment,
        url=b2share_cli.build_record_url(b2share_cli._base_url(environment), latest) or "",
        doi=pid, title=metadata.get("title"), version=metadata.get("version") or citation.version,
    )
    related = [str(r.get("identifier", "")) for r in metadata.get("related_identifiers") or [] if isinstance(r, dict)]
    return _Visit(title=metadata.get("title"), links=_links_from(citation, related))


def _visit_gbif(identifier: str, environment: Environment, result: PreviousVersion) -> _Visit:
    api = f"{gbif_cli.GBIF_REGISTRY_BASE_URLS[environment]}/v1"
    if _DOI.match(identifier):
        matches = _get_json(f"{api}/dataset/doi/{identifier}").get("results") or []
        if not matches:
            raise RuntimeError(f"no GBIF dataset with DOI {identifier}.")
        identifier = matches[0]["key"]
    dataset = _get_json(f"{api}/dataset/{identifier}")
    endpoints = _get_json_list(f"{api}/dataset/{identifier}/endpoint")
    result.gbif = FoundGbif(
        dataset_key=identifier, environment=environment,
        url=gbif_cli.GBIF_DATASET_PAGE_URL_TEMPLATES[environment].format(key=identifier),
        doi=dataset.get("doi"), title=dataset.get("title"),
    )
    # Its CAMTRAP_DP endpoint is the archive this tool registered — on the
    # Hugging Face Hub dataset, when it was published there.
    archive_urls = [str(e.get("url", "")) for e in endpoints if e.get("type") == gbif_cli.GBIF_ENDPOINT_TYPE]
    return _Visit(title=dataset.get("title"), links=_links_from(_Citation(), archive_urls))


def _get_json_list(url: str) -> list:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, list) else []


# ── identifier normalization ──

def _normalize(repo: Repo, identifier: str) -> tuple[str, Optional[Environment]]:
    """A bare id/repo_id, a URL or a DOI -> (id, environment if the URL
    says which one)."""
    value = identifier.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if repo == "hfh":
        if match := _HFH_URL.search(value):
            return match.group(1), None
        if re.fullmatch(r"[\w.-]+/[\w.-]+", value):
            return value, None
        raise ValueError(f"{identifier!r} is not a Hugging Face Hub dataset (expected owner/name or its URL).")
    if repo == "zenodo":
        if match := _ZENODO_URL.search(value):
            return match.group(2), "sandbox" if match.group(1) else "production"
        if match := _ZENODO_DOI.match(value):
            return match.group(1), None
        if value.isdigit():
            return value, None
        raise ValueError(f"{identifier!r} is not a Zenodo record (expected its numeric id, URL or DOI).")
    if repo == "gbif":
        if match := _GBIF_URL.search(value):
            return match.group(2).lower(), "sandbox" if "gbif-test" in match.group(1).lower() else "production"
        if re.fullmatch(_UUID, value, re.IGNORECASE):
            return value.lower(), None
        if _DOI.match(value):
            return value, None
        raise ValueError(f"{identifier!r} is not a GBIF dataset (expected its key, URL or DOI).")
    if match := _B2SHARE_URL.search(value):
        return match.group(2), "sandbox" if match.group(1) else "production"
    if match := _B2SHARE_DOI.match(value):
        return match.group(1), None
    if re.fullmatch(r"[a-z0-9]{5}-[a-z0-9]{5}", value, re.IGNORECASE):
        return value.lower(), None
    raise ValueError(f"{identifier!r} is not a B2SHARE record (expected its id, URL or DOI).")


def _other(environment: Optional[Environment]) -> Optional[Environment]:
    return {"sandbox": "production", "production": "sandbox"}.get(environment or "")


def _visit_first(
    repo: Repo, identifier: str, environments: list[Optional[Environment]], result: PreviousVersion,
) -> tuple[_Visit, Optional[Environment]]:
    if repo == "hfh":
        return _visit_hfh(identifier, result), None
    visit_record = {"zenodo": _visit_zenodo, "b2share": _visit_b2share, "gbif": _visit_gbif}[repo]
    error: Exception | None = None
    for environment in environments:
        try:
            return visit_record(identifier, environment, result), environment
        except Exception as exc:  # e.g. not found in this environment
            error = error or exc
    raise error


# ── entry point ──

def lookup(request: PreviousVersionRequest) -> PreviousVersion:
    """Raises:
        ValueError: if request.identifier isn't recognizable for request.repo.
        RuntimeError: if that starting repository can't be read at all —
        any OTHER repository failing along the way only adds a warning.
    """
    settings = load_settings()
    default_env: dict[Repo, Optional[Environment]] = {
        "hfh": None, "zenodo": settings.ZENODO.environment, "b2share": settings.B2SHARE.environment,
        "gbif": settings.GBIF.environment or "sandbox",
    }
    start_id, start_env = _normalize(request.repo, request.identifier)
    result = PreviousVersion()
    pending: list[tuple[Repo, str, Optional[Environment]]] = [(request.repo, start_id, start_env)]
    seen: set[Repo] = set()
    titles: dict[Repo, Optional[str]] = {}

    while pending:
        repo, identifier, environment = pending.pop(0)
        if repo in seen:
            continue
        seen.add(repo)
        # With no environment known (a bare id, or a DOI — sandbox and
        # production DOIs look alike), try the configured one first, then
        # the other.
        candidates = [environment] if environment else [default_env[repo], _other(default_env[repo])]
        try:
            visit, _ = _visit_first(repo, identifier, candidates, result)
        except Exception as exc:
            if repo == request.repo:
                raise RuntimeError(f"Could not read {identifier!r}: {exc}") from exc
            result.warnings.append(f"Found a link to {repo} ({identifier}), but couldn't read it: {exc}")
            continue
        titles[repo] = visit.title
        # No environment is inherited along a link — each repository's is
        # independent — so _visit_first tries both for it.
        pending.extend(link for link in visit.links if link[0] not in seen)

    result.title = titles.get(request.repo) or next((t for t in titles.values() if t), None)
    result.version = highest_version([
        result.hfh.version if result.hfh else None,
        result.zenodo.version if result.zenodo else None,
        result.b2share.version if result.b2share else None,
    ])
    return result
