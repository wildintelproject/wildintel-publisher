"""FastAPI router — configuring/testing the S3-compatible bucket, and running
the image download+upload step against a package (see
services.s3_service.run_s3_image_upload) — which the wizard starts right
after the metadata step is applied, before the user picks where to publish.

Every endpoint resolves the saved remote's credentials fresh per call (see
services.s3_service)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from wildintel_publisher.web.schemas.requests import S3TestConnectionRequest, S3UploadRequest
from wildintel_publisher.web.services import s3_service

router = APIRouter(prefix="/api/s3", tags=["s3"])
logger = logging.getLogger(__name__)


@router.get("/config")
def get_config() -> dict:
    """The saved remotes from settings.toml (no access/secret key values)."""
    return {"remotes": s3_service.list_remotes()}


@router.post("/test-connection")
def test_connection(req: S3TestConnectionRequest) -> dict:
    """Verify a S3 bucket/credentials combination. Nothing is saved — the
    settings page saves the remote itself."""
    try:
        remote = s3_service.get_remote(req.remote_id) if req.remote_id else None
    except ValueError:
        remote = None  # a remote still being created on the settings page
    try:
        access_key, secret_key = s3_service.resolve_credentials(req.access_key, req.secret_key, remote)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    bucket = req.bucket or (remote.bucket if remote else None)
    endpoint_url = req.endpoint_url if req.endpoint_url is not None else (remote.endpoint_url if remote else None)
    region = req.region if req.region is not None else (remote.region if remote else None)
    verify_ssl = req.verify_ssl if req.verify_ssl is not None else (remote.verify_ssl if remote else True)

    try:
        return s3_service.test_connection(
            endpoint_url=endpoint_url, region=region, bucket=bucket, access_key=access_key, secret_key=secret_key,
            verify_ssl=verify_ssl,
        )
    except ValueError as exc:
        logger.warning("S3 test-connection failed: %s", exc)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.warning("S3 test-connection failed with an unexpected error: %s", exc)
        raise HTTPException(502, f"Could not verify the S3 connection: {exc}") from exc


@router.post("/upload")
async def start_upload(req: S3UploadRequest) -> dict:
    """Starts downloading every public image of the package in input_dir and
    uploading it to the saved remote remote_id, rewriting media.csv's
    filePath to the public URLs. Returns a task_id; poll
    GET /api/s3/upload/{task_id}. A missing bucket/credentials shows up
    there as an error status, not here."""
    input_dir = Path(req.input_dir)
    if not (input_dir / "media.csv").is_file():
        raise HTTPException(400, f"{input_dir} has no media.csv — nothing to upload.")
    try:
        connection = s3_service.remote_upload_config(req.remote_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    media_dir = Path(req.media_dir) if req.media_dir else None
    task_id = s3_service.start_upload_task(
        input_dir=input_dir, media_dir=media_dir, config={**connection, "dry_run": req.dry_run},
    )
    return {"task_id": task_id}


@router.get("/upload/{task_id}")
def upload_status(task_id: str) -> dict:
    """Poll a S3 upload task — {"status": "running"|"done"|"error", "stage",
    "error", "downloaded_images", "uploaded", "total", "rewritten"}."""
    result = s3_service.get_upload_task_status(task_id)
    if result is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return result
