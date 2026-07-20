"""FastAPI router — HuggingFace Hub publishing.

No server-side session: every endpoint resolves the token fresh per call,
falling back to settings.toml (see services.hfh_service)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from huggingface_hub.errors import HfHubHTTPError

from schemas.requests import HFHPublishRequest, HFHTestTokenRequest
from services import hfh_service

router = APIRouter(prefix="/api/hfh", tags=["hfh"])
logger = logging.getLogger(__name__)


@router.get("/config")
def get_config() -> dict:
    """Current HFH defaults from settings.toml (no token value)."""
    return hfh_service.get_connection_defaults()


@router.post("/test-token")
def test_token(req: HFHTestTokenRequest) -> dict:
    """Verify a HuggingFace Hub token, and save it (with repo_id, if given)
    to settings.toml once verified — so it doesn't need to be retyped."""
    try:
        token = hfh_service.resolve_token(req.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        result = hfh_service.test_token(token, req.repo_id, req.version)
    except HfHubHTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (401, 403):
            logger.warning("HFH test-token failed: %s", exc)
            raise HTTPException(401, "Incorrect or expired HuggingFace Hub token.") from exc
        logger.warning("HFH test-token failed with an unexpected Hugging Face Hub error: %s", exc)
        raise HTTPException(502, f"Hugging Face Hub returned an unexpected error: {exc}") from exc
    except Exception as exc:
        logger.warning("HFH test-token failed: %s", exc)
        raise HTTPException(502, f"Could not reach Hugging Face Hub: {exc}") from exc

    hfh_service.save_config(req.repo_id, req.token)
    return result


@router.post("/publish")
async def publish(req: HFHPublishRequest) -> dict:
    """Start prepare -> upload -> release as a background task.
    Returns a task_id; poll GET /api/hfh/publish/{task_id} for status."""
    try:
        token = hfh_service.resolve_token(req.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not req.repo_id:
        raise HTTPException(400, "Missing the HuggingFace Hub repository (user_or_org/dataset).")

    hfh_service.save_config(req.repo_id, req.token)

    output_dir = Path(req.output_dir) if req.output_dir else hfh_service.get_hfh_output_dir()
    task_id = hfh_service.start_publish_task(
        input_dir=Path(req.input_dir),
        output_dir=output_dir,
        version=req.version or hfh_service.DEFAULT_VERSION,
        timeout=req.timeout or hfh_service.DEFAULT_TIMEOUT,
        repo_id=req.repo_id,
        private=req.private,
        token=token,
        mirror_images=req.mirror_images,
        output_mode=req.output_mode,
    )
    return {"task_id": task_id}


@router.get("/publish/{task_id}")
def publish_status(task_id: str) -> dict:
    """Poll the status of a HuggingFace Hub publish task."""
    status = hfh_service.get_publish_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status
