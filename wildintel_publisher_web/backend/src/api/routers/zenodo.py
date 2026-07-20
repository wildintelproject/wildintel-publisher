"""FastAPI router — Zenodo publishing.

No server-side session: every endpoint resolves the token fresh per call,
falling back to settings.toml (see services.zenodo_service)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.requests import ZenodoPublishRequest, ZenodoSyncDoiRequest, ZenodoTestTokenRequest
from services import hfh_service, zenodo_service

router = APIRouter(prefix="/api/zenodo", tags=["zenodo"])
logger = logging.getLogger(__name__)


@router.get("/config")
def get_config() -> dict:
    """Current ZENODO defaults from settings.toml (no token value)."""
    return zenodo_service.get_connection_defaults()


@router.post("/test-token")
def test_token(req: ZenodoTestTokenRequest) -> dict:
    """Verify a Zenodo token, and save it (with environment, if given) to
    settings.toml once verified — so it doesn't need to be retyped."""
    try:
        token = zenodo_service.resolve_token(req.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    environment = req.environment or zenodo_service.get_connection_defaults()["environment"]
    try:
        result = zenodo_service.test_token(token, environment)
    except ValueError as exc:
        logger.warning("Zenodo test-token failed: %s", exc)
        raise HTTPException(401, str(exc)) from exc
    except Exception as exc:
        logger.warning("Zenodo test-token failed with an unexpected error: %s", exc)
        raise HTTPException(502, f"Could not verify the Zenodo token: {exc}") from exc

    zenodo_service.save_config(req.environment, None, req.token)
    return result


@router.post("/publish")
async def publish(req: ZenodoPublishRequest) -> dict:
    """Start prepare -> upload -> release as a background task.
    Returns a task_id; poll GET /api/zenodo/publish/{task_id} for status."""
    try:
        token = zenodo_service.resolve_token(req.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not req.mirror_images and not req.hfh_repo_id:
        raise HTTPException(400, "Link mode needs a HuggingFace Hub repository to link media.csv to.")

    defaults = zenodo_service.get_connection_defaults()
    environment = req.environment or defaults["environment"]
    communities = req.communities if req.communities is not None else defaults["communities"]

    zenodo_service.save_config(req.environment, req.communities, req.token)

    output_dir = Path(req.output_dir) if req.output_dir else zenodo_service.get_zenodo_output_dir()
    task_id = zenodo_service.start_publish_task(
        input_dir=Path(req.input_dir),
        output_dir=output_dir,
        version=req.version or zenodo_service.DEFAULT_VERSION,
        timeout=req.timeout or zenodo_service.DEFAULT_TIMEOUT,
        mirror_images=req.mirror_images,
        hfh_repo_id=req.hfh_repo_id,
        environment=environment,
        communities=communities,
        token=token,
        output_mode=req.output_mode,
    )
    return {"task_id": task_id}


@router.get("/publish/{task_id}")
def publish_status(task_id: str) -> dict:
    """Poll the status of a Zenodo publish task."""
    status = zenodo_service.get_publish_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status


@router.post("/sync-doi")
def sync_doi(req: ZenodoSyncDoiRequest) -> dict:
    """Reflects the already-published Zenodo DOI in the HFH export's
    CITATION.cff, and re-uploads it (plus checksums-sha256.txt) to the
    given HuggingFace Hub repo."""
    try:
        hfh_token = hfh_service.resolve_token(req.hfh_token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        return zenodo_service.sync_doi_to_hfh(
            zenodo_output_dir=Path(req.zenodo_output_dir),
            hfh_output_dir=Path(req.hfh_output_dir),
            hfh_repo_id=req.hfh_repo_id,
            hfh_token=hfh_token,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
