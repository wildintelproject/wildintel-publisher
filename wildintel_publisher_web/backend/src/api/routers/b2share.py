"""FastAPI router — B2SHARE (EUDAT) publishing.

No server-side session: every endpoint resolves the token fresh per call,
falling back to settings.toml (see services.b2share_service)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.requests import B2SharePublishRequest, B2ShareSyncPidRequest, B2ShareTestTokenRequest
from services import b2share_service, hfh_service

router = APIRouter(prefix="/api/b2share", tags=["b2share"])
logger = logging.getLogger(__name__)


@router.get("/config")
def get_config() -> dict:
    """Current B2SHARE defaults from settings.toml (no token value)."""
    return b2share_service.get_connection_defaults()


@router.post("/test-token")
def test_token(req: B2ShareTestTokenRequest) -> dict:
    """Verify a B2SHARE token, and save it (with environment, if given) to
    settings.toml once verified — so it doesn't need to be retyped."""
    try:
        token = b2share_service.resolve_token(req.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    environment = req.environment or b2share_service.get_connection_defaults()["environment"]
    try:
        result = b2share_service.test_token(token, environment)
    except ValueError as exc:
        logger.warning("B2SHARE test-token failed: %s", exc)
        raise HTTPException(401, str(exc)) from exc
    except Exception as exc:
        logger.warning("B2SHARE test-token failed with an unexpected error: %s", exc)
        raise HTTPException(502, f"Could not verify the B2SHARE token: {exc}") from exc

    b2share_service.save_config(req.environment, None, req.token)
    return result


@router.post("/publish")
async def publish(req: B2SharePublishRequest) -> dict:
    """Start prepare -> upload -> release as a background task.
    Returns a task_id; poll GET /api/b2share/publish/{task_id} for status."""
    try:
        token = b2share_service.resolve_token(req.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not req.mirror_images and not req.hfh_repo_id:
        raise HTTPException(400, "Link mode needs a HuggingFace Hub repository to link media.csv to.")

    defaults = b2share_service.get_connection_defaults()
    environment = req.environment or defaults["environment"]
    community_id = req.community_id or defaults["community_id"]
    if not community_id:
        raise HTTPException(400, "Missing the EUDAT B2SHARE community UUID.")

    b2share_service.save_config(req.environment, req.community_id, req.token)

    output_dir = Path(req.output_dir) if req.output_dir else b2share_service.get_b2share_output_dir()
    task_id = b2share_service.start_publish_task(
        input_dir=Path(req.input_dir),
        output_dir=output_dir,
        version=req.version or b2share_service.DEFAULT_VERSION,
        timeout=req.timeout or b2share_service.DEFAULT_TIMEOUT,
        mirror_images=req.mirror_images,
        hfh_repo_id=req.hfh_repo_id,
        environment=environment,
        community_id=community_id,
        token=token,
        output_mode=req.output_mode,
    )
    return {"task_id": task_id}


@router.get("/publish/{task_id}")
def publish_status(task_id: str) -> dict:
    """Poll the status of a B2SHARE publish task."""
    status = b2share_service.get_publish_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status


@router.post("/sync-pid")
def sync_pid(req: B2ShareSyncPidRequest) -> dict:
    """Reflects the already-available B2SHARE PID/DOI in the HFH export's
    CITATION.cff, and re-uploads it (plus checksums-sha256.txt) to the
    given HuggingFace Hub repo."""
    try:
        hfh_token = hfh_service.resolve_token(req.hfh_token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        return b2share_service.sync_pid_to_hfh(
            b2share_output_dir=Path(req.b2share_output_dir),
            hfh_output_dir=Path(req.hfh_output_dir),
            hfh_repo_id=req.hfh_repo_id,
            hfh_token=hfh_token,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
