"""FastAPI router — configuring/testing the S3-compatible bucket, and running
the image download+upload step against a package (see
services.s3_service.run_s3_image_upload) — which the wizard starts right
after the metadata step is applied, before the user picks where to publish.

Every endpoint resolves credentials fresh per call, falling back to
settings.toml (see services.s3_service)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.requests import S3TestConnectionRequest, S3UploadRequest
from services import s3_service

router = APIRouter(prefix="/api/s3", tags=["s3"])
logger = logging.getLogger(__name__)


@router.get("/config")
def get_config() -> dict:
    """Current S3 defaults from settings.toml (no access/secret key value)."""
    return s3_service.get_connection_defaults()


@router.post("/test-connection")
def test_connection(req: S3TestConnectionRequest) -> dict:
    """Verify a S3 bucket/credentials combination, and save it to
    settings.toml once verified — so it doesn't need to be retyped."""
    try:
        access_key, secret_key = s3_service.resolve_credentials(req.access_key, req.secret_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    defaults = s3_service.get_connection_defaults()
    bucket = req.bucket or defaults["bucket"]
    endpoint_url = req.endpoint_url if req.endpoint_url is not None else defaults["endpoint_url"]
    region = req.region if req.region is not None else defaults["region"]
    verify_ssl = req.verify_ssl if req.verify_ssl is not None else defaults["verify_ssl"]

    try:
        result = s3_service.test_connection(
            endpoint_url=endpoint_url, region=region, bucket=bucket, access_key=access_key, secret_key=secret_key,
            verify_ssl=verify_ssl,
        )
    except ValueError as exc:
        logger.warning("S3 test-connection failed: %s", exc)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.warning("S3 test-connection failed with an unexpected error: %s", exc)
        raise HTTPException(502, f"Could not verify the S3 connection: {exc}") from exc

    s3_service.save_config(
        endpoint_url=req.endpoint_url, region=req.region, bucket=req.bucket, prefix=None, public_base_url=None,
        access_key=req.access_key, secret_key=req.secret_key, verify_ssl=req.verify_ssl,
    )
    return result


@router.post("/upload")
async def start_upload(req: S3UploadRequest) -> dict:
    """Starts downloading every public image of the package in input_dir and
    uploading it to the bucket, rewriting media.csv's filePath to the public
    URLs. Returns a task_id; poll GET /api/s3/upload/{task_id}. A missing
    bucket/credentials shows up there as an error status, not here."""
    input_dir = Path(req.input_dir)
    if not (input_dir / "media.csv").is_file():
        raise HTTPException(400, f"{input_dir} has no media.csv — nothing to upload.")
    media_dir = Path(req.media_dir) if req.media_dir else None
    task_id = s3_service.start_upload_task(
        input_dir=input_dir, media_dir=media_dir,
        config=req.model_dump(exclude={"input_dir", "media_dir"}),
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
