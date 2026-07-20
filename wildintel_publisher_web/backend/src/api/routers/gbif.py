"""FastAPI router — GBIF Registry registration.

No server-side session: every endpoint resolves credentials fresh per call,
falling back to settings.toml (see services.gbif_service). Unlike HFH/
Zenodo/B2SHARE there's no /publish endpoint here — GBIF never uploads
anything of its own, so registering a dataset only ever happens as part of
a multi-repo publish (see services.publish_orchestrator/api.routers.publish),
not standalone."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from schemas.requests import GBIFTestCredentialsRequest
from services import gbif_service

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
