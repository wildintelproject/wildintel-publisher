"""FastAPI router — GBIF Registry registration.

No server-side session: every endpoint resolves credentials fresh per call,
falling back to settings.toml (see services.gbif_service). Unlike HFH/
Zenodo/B2SHARE there's no /publish endpoint here — GBIF never uploads
anything of its own, so registering a dataset only ever happens as part of
a multi-repo publish (see services.publish_orchestrator/api.routers.publish),
not standalone."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.requests import GBIFSyncDoiRequest, GBIFTestCredentialsRequest, GBIFValidateArchiveRequest
from services import gbif_service, hfh_service

router = APIRouter(prefix="/api/gbif", tags=["gbif"])
logger = logging.getLogger(__name__)


@router.get("/config")
def get_config() -> dict:
    """Current GBIF defaults from settings.toml (no credential values)."""
    return gbif_service.get_connection_defaults()


@router.post("/test-credentials")
def test_credentials(req: GBIFTestCredentialsRequest) -> dict:
    """Verify GBIF Registry API credentials, and save them (with
    environment, if given) to settings.toml once verified — so they don't
    need to be retyped."""
    try:
        username, password = gbif_service.resolve_credentials(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    environment = req.environment or gbif_service.get_connection_defaults()["environment"]
    try:
        result = gbif_service.test_credentials(username, password, environment)
    except ValueError as exc:
        logger.warning("GBIF test-credentials failed: %s", exc)
        raise HTTPException(401, str(exc)) from exc
    except Exception as exc:
        logger.warning("GBIF test-credentials failed with an unexpected error: %s", exc)
        raise HTTPException(502, f"Could not verify the GBIF credentials: {exc}") from exc

    gbif_service.save_config(req.environment, None, None, None, req.username, req.password)
    return result


@router.post("/validate-archive")
def validate_archive(req: GBIFValidateArchiveRequest) -> dict:
    """Downloads req.archive_url, checks it's a zip, and validates the
    extracted Camtrap DP against the official schema — catches upfront the
    exact failure GBIF's own CAMTRAP_DP crawler otherwise hits silently (a
    crawl that finishes with no records and no visible error) when the URL
    doesn't point to a real archive."""
    try:
        return gbif_service.validate_archive(req.archive_url)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sync-doi")
def sync_doi(req: GBIFSyncDoiRequest) -> dict:
    """Reflects the DOI GBIF assigned to the dataset (if any) in the HFH
    export's CITATION.cff, and re-uploads it (plus checksums-sha256.txt) to
    the given HuggingFace Hub repo."""
    try:
        hfh_token = hfh_service.resolve_token(req.hfh_token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        return gbif_service.sync_doi_to_hfh(
            gbif_output_dir=Path(req.gbif_output_dir),
            hfh_output_dir=Path(req.hfh_output_dir),
            hfh_repo_id=req.hfh_repo_id,
            hfh_token=hfh_token,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
