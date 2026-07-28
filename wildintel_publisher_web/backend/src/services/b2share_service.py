"""B2SHARE (EUDAT) publishing for the web backend — thin wrapper around
wildintel_publisher.services.b2share.

No server-side session is kept: every call reads settings.toml fresh, and
the actual token is never returned to the frontend (same principle as
services.trapper_service/services.hfh_service/services.zenodo_service).

Per the user's request this mirrors HFH's own simple two-mode web UX
(mirror/link) rather than Zenodo's three-way CLI surface. B2SHARE's
--self-contained mode behaves EXACTLY like Zenodo's own --self-contained
(downloads images, bundles everything into a single camtrapdp.zip, drops
the loose files) — B2SHARE's API caps each record at 100 files, so
uploading one file per image the way the pre-InvenioRDM design used to
isn't viable for any real dataset. mirror_images=True here maps to
self_contained=True.

The publish pipeline itself (prepare -> upload -> release) reuses
wildintel_publisher.services.b2share directly (the same functions
'b2share prepare'/'upload'/'release' call in the CLI) — each step is
synchronous and the whole thing can take a while (image downloads/uploads
in mirror mode), so it runs as a background asyncio task polled by
task_id, same pattern as hfh_service.start_publish_task/zenodo_service.

Syncing the B2SHARE PID/DOI into an already-published HuggingFace Hub
export mirrors zenodo_service.sync_doi_to_hfh — a genuinely new capability
the CLI never needed as a single step (its own 'b2share sync-pid' only
edits the local CITATION.cff/checksums and tells the user to re-run
'hfh upload' themselves).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from dynaconf import loaders
from huggingface_hub import upload_file
from wildintel_publisher.config import DEFAULT_CONFIG_FILE, get_b2share_output_dir, load_settings
from wildintel_publisher.services import b2share as b2share_service
from wildintel_publisher.services import product

B2SHARE_TOKEN_ENV_VAR = "B2SHARE_TOKEN"

DEFAULT_VERSION = b2share_service.DEFAULT_VERSION
DEFAULT_TIMEOUT = b2share_service.DEFAULT_IMAGE_TIMEOUT

# Simple in-memory task store {task_id: {status, stage, pid, record_url,
# output_dir, error}} — same one-process, no-persistence trade-off as
# hfh_service/zenodo_service's own task stores. output_dir reflects
# output_mode (see start_publish_task) and is what the frontend chains as
# the next repo's inputDir.
_publish_tasks: dict[str, dict[str, Any]] = {}


def get_connection_defaults() -> dict:
    """Current B2SHARE defaults from settings.toml. The token itself is
    never returned — only whether one is already saved."""
    settings = load_settings()
    return {
        "environment": settings.B2SHARE.environment,
        "community_id": settings.B2SHARE.community_id,
        "output_dir": str(get_b2share_output_dir()),
        "version": DEFAULT_VERSION,
        "timeout": DEFAULT_TIMEOUT,
        "has_token": bool(os.environ.get(B2SHARE_TOKEN_ENV_VAR) or settings.B2SHARE.token),
    }


def resolve_token(token: str | None) -> str:
    """Mirrors commands/b2share.py's own _require_token: the B2SHARE_TOKEN
    environment variable takes priority, then whatever's saved in settings.toml.

    Raises:
        ValueError: if no token is available from any source.
    """
    settings = load_settings()
    resolved = token or os.environ.get(B2SHARE_TOKEN_ENV_VAR) or settings.B2SHARE.token
    if not resolved:
        raise ValueError("Missing B2SHARE token — provide one, or save it in the configuration first.")
    return resolved


def save_config(environment: str | None, community_id: str | None, token: str | None) -> None:
    """Persists environment/community_id/token into the shared settings.toml —
    called once a token has been verified (see the /test-token route).
    Rewrites the FULL Settings object, same footgun guard as
    trapper_service.save_credentials/hfh_service/zenodo_service."""
    settings = load_settings()
    if environment:
        settings.B2SHARE.environment = environment
    if community_id:
        settings.B2SHARE.community_id = community_id
    if token:
        settings.B2SHARE.token = token
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)


def test_token(token: str, environment: str) -> dict:
    """Verifies a B2SHARE token with a single lightweight, authenticated API
    call (listing records, page size 1) — B2SHARE has no dedicated 'whoami'
    endpoint.

    Returns:
        {"ok": True}

    Raises:
        ValueError: if B2SHARE rejected the token itself (401/403) — the
        router maps this to HTTP 401. Any other non-200 response (B2SHARE
        outage, rate limiting, etc.) raises RuntimeError instead, so the
        router can tell a genuinely bad token apart from an unrelated
        upstream error.
    """
    base_url = "https://trng-b2share.eudat.eu" if environment == "sandbox" else "https://b2share.eudat.eu"
    response = httpx.get(
        f"{base_url}/api/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"size": 1},
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise ValueError(f"Incorrect or expired B2SHARE token (HTTP {response.status_code}).")
    if response.status_code != 200:
        raise RuntimeError(f"B2SHARE returned an unexpected error (HTTP {response.status_code}).")
    return {"ok": True}


def _b2share_base_url(environment: str) -> str:
    return "https://trng-b2share.eudat.eu" if environment == "sandbox" else "https://b2share.eudat.eu"


def download_files_from_b2share(*, environment: str, record_id: str, token: str, target_dir: Path) -> Path:
    """Downloads the record's current files (the ones that were just
    uploaded/published) into `target_dir` — used by output_mode='downloaded'
    to hand the next repo in the publish order a verified, actually-
    round-tripped copy instead of the local staging directory."""
    api_base_url = f"{_b2share_base_url(environment)}/api"
    record = b2share_service.get_record(api_base_url, token, record_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    for file_info in record.get("files", []):
        filename = file_info.get("key")
        links = file_info.get("links") or {}
        download_url = links.get("self")
        if not filename or not download_url:
            continue
        response = httpx.get(download_url, headers={"Authorization": f"Bearer {token}"}, timeout=300)
        response.raise_for_status()
        (target_dir / filename).write_bytes(response.content)
    return target_dir


# Copied into the user's configured output_dir in addition to the product's
# own core files: b2share_record.json isn't part of any product's own
# format, but sync_pid_to_hfh (the "Sync PID/DOI to Hugging Face Hub"
# feature) needs it here to know which record to read — dropping it would
# silently break that feature after publish. README.md/LICENSE/CITATION.cff/
# checksums-sha256.txt/images/ have no such dependency (B2SHARE's own copy of
# them isn't read back by anything), so they stay out.
KEPT_EXTRA_FILES = [b2share_service.RECORD_FILENAME]


def copy_prepared_output_files(*, output_dir: Path, target_dir: Path) -> Path:
    """Copies the product's own core files (via its ProductAdapter's
    extract_core_files — see metadata.json's product_type) plus
    KEPT_EXTRA_FILES out of `output_dir` into `target_dir` — used to hand the
    user's configured output directory just the product's own files (with
    prepare_b2share_export/upload_to_b2share's modifications applied:
    private media filtered out, media.csv rewritten to B2SHARE/HFH URLs) and
    b2share_record.json, without the rest of the B2SHARE-specific extras
    (README.md, LICENSE, CITATION.cff, checksums-sha256.txt, images/) —
    those only ever exist in the temporary build directory used to stage
    the upload (see start_publish_task)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    product_meta = product.read_metadata_json(output_dir)
    adapter = product.get_adapter(product_meta["product_type"])
    adapter.extract_core_files(output_dir, target_dir)
    product.copy_metadata_json(output_dir, target_dir)
    for filename in KEPT_EXTRA_FILES:
        source = output_dir / filename
        if source.is_file():
            shutil.copy2(source, target_dir / filename)
    return target_dir


def start_publish_task(
    *, input_dir: Path, output_dir: Path, version: str, timeout: int,
    mirror_images: bool, hfh_repo_id: str | None, environment: str, community_id: str, token: str,
    output_mode: str = "prepared",
) -> str:
    """Launches prepare_b2share_export -> upload_to_b2share -> release_on_b2share
    as a background asyncio task (via a worker thread, since each step is
    blocking) and returns a task_id immediately. Poll
    get_publish_task_status(task_id) for progress — 'stage' tells which of
    the three steps is currently running.

    mirror_images: True (mirror) downloads the public images and bundles
    them inside B2SHARE's own camtrapdp.zip (self_contained=True, exactly
    like Zenodo) — 'upload' then uploads just that zip, never the images
    individually. False (link) doesn't download anything and rewrites
    media.csv's filePath to hfh_repo_id's HuggingFace Hub URLs
    (self_contained=False).

    prepare/upload/release always run against a throwaway temporary
    directory, never against `output_dir` directly — most of the
    B2SHARE-specific extras they write (README.md, LICENSE, CITATION.cff,
    checksums-sha256.txt, images/) only exist there and are discarded once
    the publish finishes. `output_dir` (the directory the user actually
    configured) only receives the core Camtrap DP files plus
    b2share_record.json (kept because the "Sync PID/DOI to Hugging Face Hub"
    feature needs it) — see copy_prepared_output_files.

    output_mode controls what 'output_dir' in the final status is (used by
    the frontend as the next repo's inputDir when chaining publish steps):
    - 'prepared' (default): output_dir itself (the core Camtrap DP files).
    - 'passthrough': input_dir itself, unchanged — nothing new is written.
    - 'downloaded': a fresh copy downloaded back from the B2SHARE record
      after a successful publish (see download_files_from_b2share). Falls
      back to 'prepared' behavior if the record has no PID yet (pending
      moderator approval — see below).
    """
    task_id = str(uuid.uuid4())
    _publish_tasks[task_id] = {
        "status": "running", "stage": "preparing", "pid": None, "record_url": None, "output_dir": None, "error": None,
    }

    settings = load_settings()

    async def _run() -> None:
        build_dir = Path(tempfile.mkdtemp(prefix="b2share-build-"))
        try:
            await asyncio.to_thread(
                b2share_service.prepare_b2share_export,
                input_dir=input_dir, output_dir=build_dir, metadata=settings.B2SHARE,
                hfh_repo_id=hfh_repo_id, self_contained=mirror_images,
                version=version, image_timeout=timeout, overwrite=True,
            )
            _publish_tasks[task_id]["stage"] = "uploading"
            await asyncio.to_thread(
                b2share_service.upload_to_b2share, build_dir,
                token=token, environment=environment, community_id=community_id,
                hfh_repo_id=hfh_repo_id,
            )
            _publish_tasks[task_id]["stage"] = "releasing"
            record = await asyncio.to_thread(b2share_service.release_on_b2share, build_dir, token=token)

            await asyncio.to_thread(copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)

            final_output_dir = str(output_dir)
            if output_mode == "passthrough":
                final_output_dir = str(input_dir)
            elif output_mode == "downloaded" and record.get("pid"):
                _publish_tasks[task_id]["stage"] = "downloading"
                download_dir = output_dir.parent / f"{output_dir.name}-downloaded"
                await asyncio.to_thread(
                    download_files_from_b2share, environment=environment,
                    record_id=record["record_id"], token=token, target_dir=download_dir,
                )
                final_output_dir = str(download_dir)

            _publish_tasks[task_id] = {
                "status": "done", "stage": "done", "pid": record.get("pid"), "record_url": record.get("record_url"),
                "output_dir": final_output_dir, "error": None,
            }
        except Exception as exc:
            _publish_tasks[task_id] = {
                "status": "error", "stage": _publish_tasks[task_id]["stage"],
                "pid": None, "record_url": None, "output_dir": None, "error": str(exc),
            }
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)

    asyncio.create_task(_run())
    return task_id


def get_publish_task_status(task_id: str) -> dict[str, Any] | None:
    return _publish_tasks.get(task_id)


def sync_pid_to_hfh(
    *, b2share_output_dir: Path, hfh_output_dir: Path, hfh_repo_id: str, hfh_token: str,
) -> dict:
    """Reflects the already-available B2SHARE PID/DOI in the HFH export's
    CITATION.cff/README.md/checksums (reusing wildintel_publisher.services.
    b2share.sync_pid_to_hfh — which also patches README.md's own "## Citation"
    section, see common.patch_readme_citation_url), and re-uploads just
    those changed files to the given HuggingFace Hub repo — the CLI's own
    'b2share sync-pid' stops at the local edit and tells the user to re-run
    'hfh upload' themselves.

    Returns:
        {"pid": "..." | None, "repo_url": "https://huggingface.co/datasets/..."}
        pid is None if B2SHARE hasn't assigned one yet (pending moderator
        approval) — in that case nothing is re-uploaded.

    Raises:
        RuntimeError: if the HFH export hasn't been prepared (see
        b2share.sync_pid_to_hfh), or if the HuggingFace Hub upload fails.
    """
    pid = b2share_service.sync_pid_to_hfh(b2share_output_dir=b2share_output_dir, hfh_output_dir=hfh_output_dir)

    if pid:
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
                commit_message=f"Sync B2SHARE PID/DOI ({pid}) via wildintel-publisher",
            )

    return {"pid": pid, "repo_url": f"https://huggingface.co/datasets/{hfh_repo_id}"}
