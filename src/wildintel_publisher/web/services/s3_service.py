"""Uploading a Camtrap DP package's own public images to a S3-compatible
bucket (AWS S3, MinIO, or any other provider speaking the same API) — the
web wizard's own optional "Upload images to a public repository?" question,
asked at the top of the metadata step (see S3ImageUploadPicker).

Unlike the other services here (hfh_service/zenodo_service/...), this isn't
a metadata repository of its own: it's a media-hosting preprocessing step
that runs once, directly against the product's own input_dir, as a
background task of its own (start_upload_task/get_upload_task_status) — the
wizard starts it right after the user's datapackage.json edits and
generate-metadata have been applied (its "Continue" button on the metadata
step), and waits for it before moving on. So by the time the user gets to
choose WHERE to publish, the images are already in the bucket and
media.csv's own filePath already points at their public URLs. Every repo
publish step downstream (HFH/Zenodo/B2SHARE mirror OR link mode) then treats
the package exactly like it would an already-published HuggingFace Hub
mirror (see wildintel_publisher.core.services.common.rewrite_media_filepaths_to_hfh),
with no S3-specific branch of its own needed anywhere else in the pipeline
(publish_orchestrator knows nothing about S3).

Object keys are content-addressable, git-loose-object style: each file's own
SHA-1 hex digest (of its BYTES, not its name — see common.sha1_file), sharded
into two 2-hex-char folder levels, the full 40-char digest as the object's
own name, no extension (see content_key). Two different mediaIDs that happen
to share the exact same bytes (a duplicate photo, common in camera-trap
datasets — the same trigger firing on multiple cameras, or across
deployments) are therefore uploaded and stored ONCE, not once per row of
media.csv — PutObject with the same key twice is a harmless, idempotent
no-op the second time.

run_s3_image_upload is a plain synchronous function (like every OTHER
service's own core logic here, e.g. hfh_service.publish) — _run_upload wraps
it in asyncio.to_thread and folds its `progress` callback into an in-memory
status dict polled by task_id (same pattern as trapper_service's own
download task)."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Callable

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from wildintel_publisher.core.config import S3Remote, load_settings
from wildintel_publisher.core.services import common

logger = logging.getLogger(__name__)

S3_ACCESS_KEY_ENV_VAR = "S3_ACCESS_KEY"
S3_SECRET_KEY_ENV_VAR = "S3_SECRET_KEY"

DEFAULT_TIMEOUT = common.DEFAULT_IMAGE_TIMEOUT

# Boto3/botocore exceptions worth retrying (see common.retrying) — a
# transient network/connectivity failure, never a permanent one (bad
# credentials, bucket policy denial, ...), which would only fail the exact
# same way on every retry.
_RETRYABLE_UPLOAD_EXCEPTIONS = (ClientError, EndpointConnectionError)

# Simple in-memory task store {task_id: status} — one process, no persistence
# across restarts, same trade-off trapper_service._download_tasks makes.
_upload_tasks: dict[str, dict[str, Any]] = {}


def list_remotes() -> list[dict]:
    """The saved remotes from settings.toml. access_key/secret_key
    themselves are never returned — only whether one is already saved."""
    return [
        {
            "id": remote.id, "name": remote.name, "endpoint_url": remote.endpoint_url, "region": remote.region,
            "bucket": remote.bucket, "prefix": remote.prefix, "public_base_url": remote.public_base_url,
            "verify_ssl": remote.verify_ssl,
            "has_access_key": bool(remote.access_key or os.environ.get(S3_ACCESS_KEY_ENV_VAR)),
            "has_secret_key": bool(remote.secret_key or os.environ.get(S3_SECRET_KEY_ENV_VAR)),
        }
        for remote in load_settings().S3.remotes
    ]


def get_remote(remote_id: str) -> S3Remote:
    """Raises:
        ValueError: if no saved remote has that id.
    """
    for remote in load_settings().S3.remotes:
        if remote.id == remote_id:
            return remote
    raise ValueError(f"There is no S3 remote {remote_id!r} — add it on the settings page first.")


def resolve_credentials(
    access_key: str | None, secret_key: str | None, remote: S3Remote | None = None,
) -> tuple[str, str]:
    """Explicit values first, then the remote's own saved ones, then the
    S3_ACCESS_KEY/S3_SECRET_KEY environment variables.

    Raises:
        ValueError: if either credential is unavailable from any source.
    """
    resolved_access = access_key or (remote.access_key if remote else None) or os.environ.get(S3_ACCESS_KEY_ENV_VAR)
    resolved_secret = secret_key or (remote.secret_key if remote else None) or os.environ.get(S3_SECRET_KEY_ENV_VAR)
    if not resolved_access or not resolved_secret:
        raise ValueError("Missing S3 access key/secret key — provide them, or save them in the remote's settings first.")
    return resolved_access, resolved_secret


def remote_upload_config(remote_id: str) -> dict[str, Any]:
    """Everything run_s3_image_upload needs to reach a saved remote —
    secrets included, so only ever passed server-side."""
    remote = get_remote(remote_id)
    access_key, secret_key = resolve_credentials(None, None, remote)
    return {
        "endpoint_url": remote.endpoint_url, "region": remote.region, "bucket": remote.bucket,
        "prefix": remote.prefix, "public_base_url": remote.public_base_url,
        "access_key": access_key, "secret_key": secret_key, "verify_ssl": remote.verify_ssl,
    }


def _build_client(*, endpoint_url: str | None, region: str | None, access_key: str, secret_key: str, verify_ssl: bool = True):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        # AWS SDK's SigV4 signing needs a non-empty region even against a
        # provider (MinIO, ...) that otherwise ignores it entirely.
        region_name=region or "us-east-1",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # False only for a trusted endpoint with a self-signed certificate.
        verify=verify_ssl,
    )


def test_connection(*, endpoint_url: str | None, region: str | None, bucket: str | None, access_key: str, secret_key: str,
    verify_ssl: bool = True,
) -> dict:
    """Verifies bucket/credentials with a single lightweight HeadBucket call
    — mirrors zenodo_service.test_token's own shape. Deliberately NOT
    retried (unlike download_public_images/upload_file below): a
    connectivity test is meant to fail fast and diagnostically, not mask a
    real config mistake behind a few seconds of silent retries.

    Returns:
        {"ok": True}

    Raises:
        ValueError: if the bucket doesn't exist, or access was denied — the
        router maps this to HTTP 400/401. Any other failure (unreachable
        endpoint, ...) raises RuntimeError instead.
    """
    if not bucket:
        raise ValueError("Missing S3 bucket name.")
    client = _build_client(
        endpoint_url=endpoint_url, region=region, access_key=access_key, secret_key=secret_key, verify_ssl=verify_ssl,
    )
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status in (401, 403):
            raise ValueError(f"Access denied to bucket {bucket!r} — check the access key/secret key.") from exc
        if status == 404:
            raise ValueError(f"Bucket {bucket!r} does not exist (or isn't reachable at this endpoint/region).") from exc
        raise RuntimeError(f"S3 returned an unexpected error: {exc}") from exc
    except (EndpointConnectionError, NoCredentialsError) as exc:
        raise RuntimeError(f"Could not reach the S3 endpoint: {exc}") from exc
    return {"ok": True}


def content_key(content_hash: str, prefix: str) -> str:
    """Git-loose-object-style key for a file whose content's SHA-1 hex
    digest is `content_hash` (see common.sha1_file): first 2 hex chars as
    the top folder, next 2 as a subfolder inside it, the full 40-char
    digest (no extension) as the object's own name. `prefix` (settings.
    S3.prefix, e.g. a dataset-specific folder shared with other objects in
    the same bucket) is prepended as its own path segment when non-blank."""
    return "/".join(part for part in (prefix.strip("/"), content_hash[:2], content_hash[2:4], content_hash) if part)


def _public_url_builder(
    *, bucket: str, prefix: str, endpoint_url: str | None, region: str | None, public_base_url: str | None,
) -> Callable[[str], str]:
    """Builds the url_for_file callable common.rewrite_media_filepaths_to_s3
    expects — public_base_url (a CDN/custom domain fronting the bucket)
    wins when given; absent that, path-style URLs off endpoint_url (needed
    by most self-hosted providers, e.g. MinIO, which don't support virtual-
    hosted-style by default); absent that too, AWS S3's own predictable
    virtual-hosted-style URL."""

    def url_for_file(content_hash: str) -> str:
        key = content_key(content_hash, prefix)
        if public_base_url:
            return f"{public_base_url.rstrip('/')}/{key}"
        if endpoint_url:
            return f"{endpoint_url.rstrip('/')}/{bucket}/{key}"
        return f"https://{bucket}.s3.{region or 'us-east-1'}.amazonaws.com/{key}"

    return url_for_file


def run_s3_image_upload(
    *, input_dir: Path, dry_run: bool = False, media_dir: Path | None = None,
    endpoint_url: str | None = None, region: str | None = None, bucket: str | None = None,
    prefix: str | None = None, public_base_url: str | None = None,
    access_key: str | None = None, secret_key: str | None = None, verify_ssl: bool | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Synchronous core of the S3 image upload step — run by _run_upload
    (via asyncio.to_thread) right after the wizard's metadata step has been
    applied, whenever "Upload images to a public repository?" was answered
    yes. Runs directly against `input_dir` — no separate build directory
    like the per-repo publish tasks use, since this step's own output
    (images/ downloaded locally, media.csv rewritten) is exactly what should
    stay in input_dir for every later repo to inherit.

    media_dir is where media.csv's locally-referenced (non-URL) filePath
    entries are resolved from, when different from input_dir — a local
    Camtrap DP source, where input_dir is only an app-owned working copy of
    the core files and the real images stayed at the user's original
    directory (same meaning as publish_orchestrator's own media_dir).
    Defaults to input_dir.

    Steps, in order:
      1. common.download_public_images (retried per-file — see
         S3Settings.retry_attempts/retry_wait_seconds, threaded through to
         it as its own retry_attempts/retry_wait_seconds).
      2. common.sha1_file on every downloaded file, to get each one's own
         content hash — collected into a {fileName: hash} mapping.
      3. Unless dry_run: client.upload_file to `{prefix}/{hash[:2]}/
         {hash[2:4]}/{hash}` (no extension — see content_key), retried on a
         transient ClientError/EndpointConnectionError. Skipped entirely in
         dry_run mode (nothing is actually uploaded/created — same
         "mocked network call, real local prep" contract every other repo's
         own dry_run branch follows — see the module docstring of
         publish_orchestrator), but the SAME deterministic key/URL is still
         computed and used to rewrite media.csv below, since it only
         depends on the file's own content, not on whether it was actually
         PUT to the bucket.
      4. common.rewrite_media_filepaths_to_s3, so downstream repos see the
         (would-be, in dry_run) public URL as media.csv's own filePath.

    The connection comes from a saved remote (see remote_upload_config);
    access_key/secret_key left as None fall back to the S3_ACCESS_KEY/
    S3_SECRET_KEY environment variables.

    progress, if given, is called with a partial dict (e.g. {"stage":
    "uploading"}, {"uploaded": 3}) after every stage transition and every
    individual file uploaded — meant to be merged into the caller's own
    status dict (see _run_upload, which passes status.update), not replace
    it wholesale.

    Returns:
        {"downloaded_images": int, "uploaded": int, "rewritten": int} — rewritten
        is how many media.csv rows actually got a new filePath (see
        common.rewrite_media_filepaths_to_s3).

    Raises:
        ValueError: if no bucket, or no access_key/secret_key, is available
        from any source (even in dry_run mode — the same config a real run
        would need is validated up front, so a dry run catches a missing
        bucket/credentials mistake too, without waiting for a real publish
        attempt to hit it).
    """
    def _report(**kwargs: Any) -> None:
        if progress is not None:
            progress(kwargs)

    settings = load_settings()
    resolved_bucket = bucket
    if not resolved_bucket:
        raise ValueError("Missing S3 bucket name.")
    resolved_access, resolved_secret = resolve_credentials(access_key, secret_key)
    resolved_endpoint = endpoint_url
    resolved_region = region
    resolved_prefix = prefix or ""
    resolved_public_base_url = public_base_url
    resolved_verify_ssl = True if verify_ssl is None else verify_ssl
    retry_attempts = settings.S3.retry_attempts
    retry_wait_seconds = settings.S3.retry_wait_seconds

    url_for_file = _public_url_builder(
        bucket=resolved_bucket, prefix=resolved_prefix, endpoint_url=resolved_endpoint,
        region=resolved_region, public_base_url=resolved_public_base_url,
    )

    _report(stage="downloading")
    images_dir = input_dir / common.IMAGES_DIRNAME
    # only_public: media.csv here is NOT filtered to filePublic=true yet (each
    # repo's own build does that later), and a non-public image must never
    # reach a public bucket.
    download = common.download_public_images(
        input_dir, input_dir=media_dir or input_dir,
        retry_attempts=retry_attempts, retry_wait_seconds=retry_wait_seconds, only_public=True,
        workers=settings.TRAPPER.download_workers,
    )
    failures = [{"file": name, "key": reason, "action": "failed"} for name, reason in download["failures"]]
    _report(log=list(failures))

    files = sorted(p for p in images_dir.rglob("*") if p.is_file())
    if not files:
        detail = f" First failure: {failures[0]['file']} — {failures[0]['key']}" if failures else " (no public row in media.csv)"
        raise ValueError(f"No public image could be fetched, so there's nothing to upload.{detail}")
    _report(stage="hashing", total=len(files))
    content_hashes: dict[str, str] = {file_path.name: common.sha1_file(file_path) for file_path in files}

    uploaded = 0
    # One entry per file, in order — {"file", "key", "action"} with action
    # "uploaded", "would-upload" (dry_run) or "duplicate" (same bytes as an
    # earlier file, so it shares that object). Reported cumulatively (a fresh
    # copy each time) so the polled status always carries the full list.
    log: list[dict[str, str]] = list(failures)
    # Duplicates (same bytes) share one object, so the number of PUTs to
    # expect — and what "uploaded" counts up to — is the unique-hash count.
    _report(stage="uploading", uploaded=0, total=len(set(content_hashes.values())), log=list(log))
    client = None
    if not dry_run:
        client = _build_client(
            endpoint_url=resolved_endpoint, region=resolved_region,
            access_key=resolved_access, secret_key=resolved_secret, verify_ssl=resolved_verify_ssl,
        )
    # A duplicate file (same content, e.g. a photo re-triggered across
    # deployments — see the module docstring) collapses to the SAME key
    # here, so it's only ever PUT once, not once per media.csv row.
    already_uploaded: set[str] = set()
    for file_path in files:
        content_hash = content_hashes[file_path.name]
        key = content_key(content_hash, resolved_prefix)
        if content_hash in already_uploaded:
            log.append({"file": file_path.name, "key": key, "action": "duplicate"})
            _report(log=list(log))
            continue
        if client is not None:
            # The key has no extension, so S3 can't infer the type from it:
            # pass the original file name's own, or browsers would download
            # the images instead of displaying them.
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            for attempt in common.retrying(retry_attempts, retry_wait_seconds, retry_on=_RETRYABLE_UPLOAD_EXCEPTIONS):
                with attempt:
                    client.upload_file(str(file_path), resolved_bucket, key, ExtraArgs={"ContentType": content_type})
            uploaded += 1
            logger.debug("Uploaded %s to s3://%s/%s (%s)", file_path.name, resolved_bucket, key, content_type)
        already_uploaded.add(content_hash)
        log.append({"file": file_path.name, "key": key, "action": "would-upload" if dry_run else "uploaded"})
        _report(uploaded=uploaded, log=list(log))

    _report(stage="rewriting")
    rewritten = common.rewrite_media_filepaths_to_s3(input_dir, content_hashes, url_for_file)

    return {"downloaded_images": len(files), "uploaded": uploaded, "rewritten": rewritten}


def _initial_upload_status() -> dict[str, Any]:
    """Status dict polled through get_upload_task_status — 'stage' is one of
    "downloading"/"hashing"/"uploading"/"rewriting" while running (see
    run_s3_image_upload's own `progress` callback), then "done"."""
    return {
        "status": "running", "stage": "", "error": None,
        "downloaded_images": 0, "uploaded": 0, "total": 0, "rewritten": None, "log": [], "dry_run": False,
    }


async def _run_upload(task_id: str, *, input_dir: Path, media_dir: Path | None, config: dict[str, Any]) -> None:
    status = _upload_tasks[task_id]
    status["dry_run"] = bool(config.get("dry_run"))
    try:
        result = await asyncio.to_thread(
            run_s3_image_upload, input_dir=input_dir, media_dir=media_dir, progress=status.update, **config,
        )
    except Exception as exc:
        logger.warning("S3 image upload failed: %s", exc, exc_info=logging.getLogger().isEnabledFor(logging.DEBUG))
        status["status"] = "error"
        status["error"] = str(exc)
        return
    status.update(result)
    status["status"] = "done"
    status["stage"] = "done"


def start_upload_task(*, input_dir: Path, media_dir: Path | None = None, config: dict[str, Any]) -> str:
    """Launches run_s3_image_upload as a background asyncio task and returns
    its task_id — poll get_upload_task_status for progress. `config` holds
    the connection (see remote_upload_config) and dry_run. A failure
    (including a missing bucket/credentials) shows up as status "error"
    rather than raising here.

    Safe to start again for the same input_dir after a failure or an
    interruption: already-downloaded images are skipped, and re-uploading an
    object with the same content-addressed key is a harmless overwrite."""
    task_id = uuid.uuid4().hex
    _upload_tasks[task_id] = _initial_upload_status()
    asyncio.create_task(_run_upload(task_id, input_dir=input_dir, media_dir=media_dir, config=config))
    return task_id


def get_upload_task_status(task_id: str) -> dict[str, Any] | None:
    return _upload_tasks.get(task_id)
