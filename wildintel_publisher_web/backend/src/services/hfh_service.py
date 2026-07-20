"""HuggingFace Hub publishing for the web backend — thin wrapper around
wildintel_publisher.services.hfh.

No server-side session is kept: every call reads settings.toml fresh, and
the actual token is never returned to the frontend (same principle as
services.trapper_service — only whether one is already saved).

The publish pipeline itself (prepare -> upload -> release) reuses
wildintel_publisher.services.hfh directly (the same functions
'hfh pipeline' calls in the CLI) — each step is synchronous and the whole
thing can take a while (image downloads, file uploads), so it runs as a
background asyncio task polled by task_id, same pattern as
trapper_service.start_download_task.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from dynaconf import loaders
from huggingface_hub import snapshot_download, whoami
from wildintel_publisher.config import DEFAULT_CONFIG_FILE, get_hfh_output_dir, load_settings
from wildintel_publisher.services import common as camtrapdp_common
from wildintel_publisher.services import hfh as hfh_service
from wildintel_publisher.services import product

HF_TOKEN_ENV_VAR = "HF_TOKEN"

DEFAULT_VERSION = hfh_service.DEFAULT_VERSION
DEFAULT_TIMEOUT = hfh_service.DEFAULT_IMAGE_TIMEOUT

# Simple in-memory task store {task_id: {status, stage, repo_url, output_dir,
# error}} — same one-process, no-persistence trade-off as trapper_service's
# own _download_tasks. output_dir reflects output_mode (see start_publish_task)
# and is what the frontend chains as the next repo's inputDir.
_publish_tasks: dict[str, dict[str, Any]] = {}


def get_connection_defaults() -> dict:
    """Current HFH defaults from settings.toml. The token itself is never
    returned — only whether one is already saved."""
    settings = load_settings()
    return {
        "username": settings.HFH.username,
        "output_dir": str(get_hfh_output_dir()),
        "version": DEFAULT_VERSION,
        "timeout": DEFAULT_TIMEOUT,
        "has_token": bool(os.environ.get(HF_TOKEN_ENV_VAR) or settings.HFH.token),
    }


def resolve_token(token: str | None) -> str:
    """Mirrors commands/hfh.py's own _require_token: the HF_TOKEN environment
    variable takes priority, then whatever's saved in settings.toml.

    Raises:
        ValueError: if no token is available from any source.
    """
    settings = load_settings()
    resolved = token or os.environ.get(HF_TOKEN_ENV_VAR) or settings.HFH.token
    if not resolved:
        raise ValueError("Missing HuggingFace Hub token — provide one, or save it in the configuration first.")
    return resolved


def save_config(repo_id: str | None, token: str | None) -> None:
    """Persists the HuggingFace Hub username/org and token into the shared
    settings.toml — called once a token has been verified (see the
    /test-token route). Only the username/org part of repo_id is kept
    (settings.HFH.username, not settings.HFH.repo_id): the dataset name
    itself is per-product (derived from metadata.json's title in the
    wizard) and shouldn't be remembered across different products. Rewrites
    the FULL Settings object (message/repository_code stay untouched), same
    footgun guard as trapper_service.save_credentials."""
    settings = load_settings()
    if repo_id:
        settings.HFH.username = repo_id.split("/", 1)[0]
    if token:
        settings.HFH.token = token
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)


def test_token(token: str, repo_id: str | None = None, version: str | None = None) -> dict:
    """Verifies a HuggingFace Hub token with a single whoami() call, and —
    if both repo_id and version are given — warns upfront whether that
    version has already been published there (a tag with that name would
    already exist). This is only a heads-up at this point: publishing
    still enforces it for real (see hfh.upload_to_huggingface's own
    tag_exists check), this just lets the user notice and bump the version
    before spending time on a publish that would fail at the very end.

    Returns:
        {"ok": True, "username": "...", "version_conflict": bool}

    Raises:
        Whatever huggingface_hub.whoami raises for an invalid/expired token —
        left for the router to map to the appropriate HTTP status.
    """
    info = whoami(token=token)
    version_conflict = bool(repo_id and version and hfh_service.tag_exists(repo_id, version, token))
    return {"ok": True, "username": info.get("name"), "version_conflict": version_conflict}


# Copied into the user's configured output_dir in addition to the product's
# own core files: CITATION.cff/checksums-sha256.txt aren't part of any
# product's own format, but sync_doi_to_hfh/sync_pid_to_hfh (the "Sync
# DOI/PID to Hugging Face Hub" feature on the Zenodo/B2SHARE forms) needs
# CITATION.cff to exist here to patch the DOI/PID into it later — dropping it
# would silently break that feature after publish. README.md/LICENSE/
# images/camtrapdp-local.zip have no such dependency, so they stay out.
KEPT_EXTRA_FILES = ["CITATION.cff", camtrapdp_common.CHECKSUM_FILENAME]


def copy_prepared_output_files(*, output_dir: Path, target_dir: Path) -> Path:
    """Copies the product's own core files (via its ProductAdapter's
    extract_core_files — see metadata.json's product_type) plus
    KEPT_EXTRA_FILES out of `output_dir` into `target_dir` — used to hand the
    user's configured output directory just the product's own files (with
    prepare_hfh_export/upload_to_huggingface's modifications applied:
    private media filtered out, media.csv rewritten to HF URLs in mirror
    mode) and CITATION.cff, without the rest of the HFH-specific extras
    (README.md, LICENSE, images/, camtrapdp-local.zip) — those only ever
    exist in the temporary build directory used to stage the upload (see
    start_publish_task)."""
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


def download_from_repo(*, repo_id: str, token: str, target_dir: Path) -> Path:
    """Downloads the dataset repo's current files (the ones that were just
    uploaded) into `target_dir` — used by output_mode='downloaded' to hand
    the next repo in the publish order a verified, actually-round-tripped
    copy instead of the local staging directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo_id, repo_type="dataset", token=token, local_dir=str(target_dir))
    return target_dir


def start_publish_task(
    *, input_dir: Path, output_dir: Path, version: str, timeout: int,
    repo_id: str, private: bool, token: str, mirror_images: bool = True,
    output_mode: str = "prepared",
) -> str:
    """Launches prepare_hfh_export -> upload_to_huggingface -> release_on_huggingface
    as a background asyncio task (via a worker thread, since each step is
    blocking) and returns a task_id immediately. Poll
    get_publish_task_status(task_id) for progress — 'stage' tells which of
    the three steps is currently running.

    mirror_images: True (mirror, default) downloads/uploads the images and
    rewrites media.csv's filePath to point to them; False (link) leaves
    media.csv untouched.

    prepare/upload always run against a throwaway temporary directory, never
    against `output_dir` directly — most of the HFH-specific extras they
    write (README.md, LICENSE, images/, camtrapdp-local.zip) only exist there
    and are discarded once the publish finishes. `output_dir` (the directory
    the user actually configured) only receives the core Camtrap DP files
    plus CITATION.cff/checksums-sha256.txt (kept because the "Sync DOI/PID to
    Hugging Face Hub" feature needs CITATION.cff to exist here) — see
    copy_prepared_output_files.

    output_mode controls what 'output_dir' in the final status is (used by
    the frontend as the next repo's inputDir when chaining publish steps):
    - 'prepared' (default): output_dir itself (the core Camtrap DP files).
    - 'passthrough': input_dir itself, unchanged — nothing new is written.
    - 'downloaded': a fresh copy downloaded back from the HuggingFace Hub
      repo after a successful upload (see download_from_repo).
    """
    task_id = str(uuid.uuid4())
    _publish_tasks[task_id] = {"status": "running", "stage": "preparing", "repo_url": None, "output_dir": None, "error": None}

    settings = load_settings()

    async def _run() -> None:
        build_dir = Path(tempfile.mkdtemp(prefix="hfh-build-"))
        try:
            await asyncio.to_thread(
                hfh_service.prepare_hfh_export,
                input_dir=input_dir, output_dir=build_dir, metadata=settings.HFH,
                version=version, image_timeout=timeout, overwrite=True, mirror_images=mirror_images,
            )
            _publish_tasks[task_id]["stage"] = "uploading"
            repo_url = await asyncio.to_thread(
                hfh_service.upload_to_huggingface, build_dir, repo_id=repo_id, token=token, private=private,
                mirror_images=mirror_images,
            )
            _publish_tasks[task_id]["stage"] = "releasing"
            # Tagging (the version becomes locked — see hfh.py's own
            # docstring) now happens as its own step, separate from
            # uploading, so a future cross-repo DOI populate step could run
            # in between the two — not wired in yet here (single-repo task).
            # Reads the actually-resolved version from build_dir's own
            # metadata.json (same source upload_to_huggingface itself
            # used) rather than trusting the raw `version` argument, which
            # is only a fallback — metadata.json's own version wins if set.
            build_meta = await asyncio.to_thread(product.read_metadata_json, build_dir)
            resolved_version = build_meta.get("version") or version
            await asyncio.to_thread(
                hfh_service.tag_release_on_huggingface, repo_id=repo_id, token=token, version=resolved_version,
            )
            await asyncio.to_thread(
                hfh_service.release_on_huggingface, repo_id=repo_id, token=token, dry_run=False, verify_only=False,
            )

            await asyncio.to_thread(copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)

            final_output_dir = str(output_dir)
            if output_mode == "passthrough":
                final_output_dir = str(input_dir)
            elif output_mode == "downloaded":
                _publish_tasks[task_id]["stage"] = "downloading"
                download_dir = output_dir.parent / f"{output_dir.name}-downloaded"
                await asyncio.to_thread(download_from_repo, repo_id=repo_id, token=token, target_dir=download_dir)
                final_output_dir = str(download_dir)

            _publish_tasks[task_id] = {
                "status": "done", "stage": "done", "repo_url": repo_url, "output_dir": final_output_dir, "error": None,
            }
        except Exception as exc:
            _publish_tasks[task_id] = {
                "status": "error", "stage": _publish_tasks[task_id]["stage"],
                "repo_url": None, "output_dir": None, "error": str(exc),
            }
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)

    asyncio.create_task(_run())
    return task_id


def get_publish_task_status(task_id: str) -> dict[str, Any] | None:
    return _publish_tasks.get(task_id)
