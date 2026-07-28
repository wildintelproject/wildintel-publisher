"""GBIF Registry registration for the web backend — thin wrapper around
wildintel_publisher.services.gbif.

No server-side session is kept: every call reads settings.toml fresh, and
the actual username/password are never returned to the frontend (same
principle as services.trapper_service/services.zenodo_service — only
whether credentials are already saved).

Unlike HFH/Zenodo/B2SHARE, GBIF never uploads or hosts anything of its own —
there's no prepare/upload/release pipeline and so no background publish task
here: services.publish_orchestrator calls
wildintel_publisher.services.gbif.register_gbif_dataset directly, during its
own 'lock' phase, reusing the CLI's own function unchanged (see that
module's docstring)."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from dynaconf import loaders
from huggingface_hub import upload_file
from wildintel_publisher.config import DEFAULT_CONFIG_FILE, get_gbif_output_dir, load_settings
from wildintel_publisher.services import gbif as gbif_cli
from wildintel_publisher.services.gbif import validate_camtrap_dp_archive

GBIF_USERNAME_ENV_VAR = "GBIF_USERNAME"
GBIF_PASSWORD_ENV_VAR = "GBIF_PASSWORD"

GBIF_REGISTRY_BASE_URLS = {
    "sandbox": "https://api.gbif-test.org",
    "production": "https://api.gbif.org",
}


def get_connection_defaults() -> dict:
    """Current GBIF defaults from settings.toml. The credentials themselves
    are never returned — only whether they're already saved."""
    settings = load_settings()
    return {
        "environment": settings.GBIF.environment,
        "publishing_organization_key": settings.GBIF.publishing_organization_key,
        "installation_key": settings.GBIF.installation_key,
        "registry_language": settings.GBIF.registry_language,
        "output_dir": str(get_gbif_output_dir()),
        "has_credentials": bool(
            (os.environ.get(GBIF_USERNAME_ENV_VAR) or settings.GBIF.username)
            and (os.environ.get(GBIF_PASSWORD_ENV_VAR) or settings.GBIF.password)
        ),
    }


def resolve_credentials(username: str | None, password: str | None) -> tuple[str, str]:
    """Mirrors commands/gbif.py's own _require_credentials: the
    GBIF_USERNAME/GBIF_PASSWORD environment variables take priority, then
    whatever's saved in settings.toml.

    Raises:
        ValueError: if either half is missing from every source.
    """
    settings = load_settings()
    resolved_username = username or os.environ.get(GBIF_USERNAME_ENV_VAR) or settings.GBIF.username
    resolved_password = password or os.environ.get(GBIF_PASSWORD_ENV_VAR) or settings.GBIF.password
    if not resolved_username or not resolved_password:
        raise ValueError(
            "Missing GBIF Registry API credentials — provide a username/password, or save them "
            "in the configuration first."
        )
    return resolved_username, resolved_password


def save_config(
    environment: str | None,
    publishing_organization_key: str | None,
    installation_key: str | None,
    registry_language: str | None,
    username: str | None,
    password: str | None,
) -> None:
    """Persists whichever GBIF fields are given into the shared
    settings.toml — called once credentials have been verified (see the
    /test-credentials route) and again, with the final submitted values,
    right before a publish (see routers.publish._resolve_repo_config).
    Rewrites the FULL Settings object, same footgun guard as
    zenodo_service.save_config."""
    settings = load_settings()
    if environment:
        settings.GBIF.environment = environment
    if publishing_organization_key:
        settings.GBIF.publishing_organization_key = publishing_organization_key
    if installation_key:
        settings.GBIF.installation_key = installation_key
    if registry_language:
        settings.GBIF.registry_language = registry_language
    if username:
        settings.GBIF.username = username
    if password:
        settings.GBIF.password = password
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)


def test_credentials(username: str, password: str, environment: str) -> dict:
    """Verifies GBIF Registry API credentials with a single call to
    /v1/user/login — the same Basic-Auth "am I who I say I am" endpoint
    IPT/registry tooling uses to validate a gbif.org (or gbif-test.org)
    account, since the Registry API has no dedicated token to check like
    Zenodo/B2SHARE's own test_token.

    Returns:
        {"ok": True}

    Raises:
        ValueError: if GBIF rejected the credentials themselves (401/403) —
        the router maps this to HTTP 401. Any other non-200 response (GBIF
        outage, rate limiting, etc.) raises RuntimeError instead, so the
        router can tell genuinely bad credentials apart from an unrelated
        upstream error.
    """
    base_url = GBIF_REGISTRY_BASE_URLS.get(environment, GBIF_REGISTRY_BASE_URLS["sandbox"])
    response = httpx.get(f"{base_url}/v1/user/login", auth=(username, password), timeout=15)
    if response.status_code in (401, 403):
        raise ValueError(f"Incorrect GBIF username/password (HTTP {response.status_code}).")
    if response.status_code != 200:
        raise RuntimeError(f"GBIF returned an unexpected error (HTTP {response.status_code}).")
    return {"ok": True}


def validate_archive(archive_url: str) -> dict:
    """Thin wrapper around wildintel_publisher.services.gbif.
    validate_camtrap_dp_archive — downloads archive_url, checks it's a real
    zip, and validates the extracted Camtrap DP against the official
    schema. Blocking (network + local file I/O), same as every other
    function in this module — the router runs it in FastAPI's own
    threadpool (plain `def` route, not `async def`), matching how
    test_credentials/get_config already do.

    Returns:
        {"ok": True}

    Raises:
        RuntimeError: if the URL can't be downloaded, isn't a real zip
        archive, or the extracted content fails Camtrap DP validation.
    """
    validate_camtrap_dp_archive(archive_url)
    return {"ok": True}


def sync_doi_to_hfh(
    *, gbif_output_dir: Path, hfh_output_dir: Path, hfh_repo_id: str, hfh_token: str,
) -> dict:
    """Reflects the DOI GBIF assigned to the dataset (if any — see
    gbif.register_gbif_dataset) in the HFH export's CITATION.cff/README.md/
    checksums (reusing wildintel_publisher.services.gbif.sync_doi_to_hfh —
    which also patches README.md's own "## Citation" section, see
    common.patch_readme_citation_url), and re-uploads just those changed
    files to the given HuggingFace Hub repo — the CLI's own 'gbif sync-doi'
    stops at the local edit and tells the user to re-run 'hfh upload'
    themselves; a web UI has no such "now go run this yourself" affordance,
    same as zenodo_service/b2share_service's own sync_doi_to_hfh/
    sync_pid_to_hfh.

    Returns:
        {"doi": "...", "repo_url": "https://huggingface.co/datasets/..."}

    Raises:
        RuntimeError: if the GBIF dataset has no DOI, or the HFH export
        hasn't been prepared (see gbif.sync_doi_to_hfh), or if the
        HuggingFace Hub upload fails.
    """
    doi = gbif_cli.sync_doi_to_hfh(gbif_output_dir=gbif_output_dir, hfh_output_dir=hfh_output_dir)

    for filename in ("CITATION.cff", "README.md", "checksums-sha256.txt"):
        file_path = hfh_output_dir / filename
        if not file_path.is_file():
            continue
        upload_file(
            path_or_fileobj=str(file_path),
            path_in_repo=filename,
            repo_id=hfh_repo_id,
            repo_type="dataset",
            token=hfh_token,
            commit_message=f"Sync GBIF DOI ({doi}) via wildintel-publisher",
        )

    return {"doi": doi, "repo_url": f"https://huggingface.co/datasets/{hfh_repo_id}"}
