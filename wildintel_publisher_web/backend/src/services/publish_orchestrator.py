"""Orchestrates publishing the same product to several repos in one go —
the web wizard's own version of "publish all", now with a cross-repo DOI
populate step wired in between uploading and locking (see
wildintel_publisher.services.doi_populate for the generic
cross-referencing logic).

Flow, for `repos` (an ORDERED list of already-configured
{"repo": "hfh"|"zenodo"|"b2share", ...} dicts — see schemas.requests.
RepoPublishConfig):

  1. Upload phase — prepare + upload every repo, ONE AFTER ANOTHER (each
     one's own build directory becomes the next one's input, same
     chaining the wizard used to do itself before this module existed).
     Whichever repos provide their own DOI (PROVIDES_DOI — Zenodo/B2SHARE)
     already reserve it here, same as 'zenodo upload'/'b2share upload' on
     the CLI.
  2. Populate phase — doi_populate.populate() cross-references whatever
     DOI got reserved above into every OTHER repo's own CITATION.cff (as
     an alternate identifier, or as the primary one for HFH, which never
     has a DOI of its own — see primary_doi_source). Any repo whose files
     actually changed gets re-uploaded (same upload_to_X call as phase 1,
     reusing the same draft/deposition/repository).
  3. Lock phase — release_on_zenodo/release_on_b2share/
     tag_release_on_huggingface+release_on_huggingface for every repo, in
     order — only now, once every cross-reference has already landed.

Only after step 3 are the product's own core files copied into each
repo's user-configured output_dir (see copy_prepared_output_files) and the
throwaway build directories deleted.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from wildintel_publisher.config import load_settings
from wildintel_publisher.services import b2share as b2share_cli
from wildintel_publisher.services import doi_populate
from wildintel_publisher.services import hfh as hfh_cli
from wildintel_publisher.services import product
from wildintel_publisher.services import zenodo as zenodo_cli

from services import b2share_service, camtrapdp_service, hfh_service, zenodo_service

DEFAULT_TIMEOUT = 60

_publish_tasks: dict[str, dict[str, Any]] = {}


def _initial_repo_status() -> dict:
    return {
        "status": "pending", "stage": "", "error": None,
        "repo_url": None, "doi": None, "pid": None, "output_dir": None,
    }


def get_publish_task_status(task_id: str) -> dict[str, Any] | None:
    return _publish_tasks.get(task_id)


def _detect_hfh_repo_id(input_dir: Path) -> str | None:
    """Same detection each PublishForm used to do live from the frontend
    (see camtrapdp_service.detect_hfh_repo_id) — now done server-side,
    right before a link-mode Zenodo/B2SHARE repo's own prepare/upload, from
    whichever directory is actually its input at that point in the chain."""
    try:
        meta = product.read_metadata_json(input_dir)
    except Exception:
        return None
    return camtrapdp_service.detect_hfh_repo_id(meta.get("homepage"))


async def _upload_one(cfg: dict, *, input_dir: Path, build_dir: Path, settings, repo_status: dict) -> None:
    """Phase 1 (and re-run as-is during phase 2 for a changed repo, minus
    the 'preparing' half — see _reupload_one): prepare + upload a single
    repo into its own build_dir."""
    repo = cfg["repo"]
    version = cfg.get("version")
    timeout = cfg.get("timeout") or DEFAULT_TIMEOUT

    if repo == "hfh":
        repo_status["stage"] = "preparing"
        await asyncio.to_thread(
            hfh_cli.prepare_hfh_export, input_dir=input_dir, output_dir=build_dir, metadata=settings.HFH,
            version=version or hfh_cli.DEFAULT_VERSION, image_timeout=timeout, overwrite=True,
            mirror_images=cfg["mirror_images"],
        )
        repo_status["stage"] = "uploading"
        repo_url = await asyncio.to_thread(
            hfh_cli.upload_to_huggingface, build_dir, repo_id=cfg["repo_id"], token=cfg["token"],
            private=cfg["private"], mirror_images=cfg["mirror_images"],
        )
        repo_status["repo_url"] = repo_url
        return

    hfh_repo_id = cfg.get("hfh_repo_id")
    if hfh_repo_id is None and not cfg["mirror_images"]:
        hfh_repo_id = await asyncio.to_thread(_detect_hfh_repo_id, input_dir)
        cfg["hfh_repo_id"] = hfh_repo_id  # remembered for phase 2's re-upload

    if repo == "zenodo":
        repo_status["stage"] = "preparing"
        await asyncio.to_thread(
            zenodo_cli.prepare_zenodo_export, input_dir=input_dir, output_dir=build_dir, metadata=settings.ZENODO,
            hfh_repo_id=hfh_repo_id, self_contained=cfg["mirror_images"],
            version=version or zenodo_cli.DEFAULT_VERSION, image_timeout=timeout, overwrite=True,
        )
        repo_status["stage"] = "uploading"
        await asyncio.to_thread(
            zenodo_cli.upload_to_zenodo, build_dir, token=cfg["token"], environment=cfg["environment"],
            communities=cfg.get("communities"), hfh_repo_id=hfh_repo_id,
        )
    elif repo == "b2share":
        repo_status["stage"] = "preparing"
        await asyncio.to_thread(
            b2share_cli.prepare_b2share_export, input_dir=input_dir, output_dir=build_dir, metadata=settings.B2SHARE,
            hfh_repo_id=hfh_repo_id, self_contained=cfg["mirror_images"],
            version=version or b2share_cli.DEFAULT_VERSION, image_timeout=timeout, overwrite=True,
        )
        repo_status["stage"] = "uploading"
        await asyncio.to_thread(
            b2share_cli.upload_to_b2share, build_dir, token=cfg["token"], environment=cfg["environment"],
            community_id=cfg["community_id"], hfh_repo_id=hfh_repo_id,
        )


async def _reupload_one(cfg: dict, *, build_dir: Path) -> None:
    """Phase 2: re-pushes a repo's already-uploaded files after populate()
    patched its CITATION.cff/README.md — reuses the same draft/deposition/
    repository (see each upload_to_X's own docstring: calling it again is
    safe and expected for exactly this)."""
    repo = cfg["repo"]
    if repo == "hfh":
        await asyncio.to_thread(
            hfh_cli.upload_to_huggingface, build_dir, repo_id=cfg["repo_id"], token=cfg["token"],
            private=cfg["private"], mirror_images=cfg["mirror_images"],
        )
    elif repo == "zenodo":
        await asyncio.to_thread(
            zenodo_cli.upload_to_zenodo, build_dir, token=cfg["token"], environment=cfg["environment"],
            communities=cfg.get("communities"), hfh_repo_id=cfg.get("hfh_repo_id"),
        )
    elif repo == "b2share":
        await asyncio.to_thread(
            b2share_cli.upload_to_b2share, build_dir, token=cfg["token"], environment=cfg["environment"],
            community_id=cfg["community_id"], hfh_repo_id=cfg.get("hfh_repo_id"),
        )


async def _lock_one(cfg: dict, *, build_dir: Path, repo_status: dict) -> None:
    """Phase 3: release_on_zenodo/release_on_b2share, or
    tag_release_on_huggingface+release_on_huggingface for HFH."""
    repo = cfg["repo"]
    repo_status["stage"] = "releasing"
    if repo == "hfh":
        meta = await asyncio.to_thread(product.read_metadata_json, build_dir)
        version = meta.get("version") or hfh_cli.DEFAULT_VERSION
        await asyncio.to_thread(
            hfh_cli.tag_release_on_huggingface, repo_id=cfg["repo_id"], token=cfg["token"], version=version,
        )
        await asyncio.to_thread(
            hfh_cli.release_on_huggingface, repo_id=cfg["repo_id"], token=cfg["token"],
            dry_run=False, verify_only=False,
        )
    elif repo == "zenodo":
        record = await asyncio.to_thread(zenodo_cli.release_on_zenodo, build_dir, token=cfg["token"])
        repo_status["doi"] = record.get("doi")
        repo_status["repo_url"] = record.get("record_url")
    elif repo == "b2share":
        record = await asyncio.to_thread(b2share_cli.release_on_b2share, build_dir, token=cfg["token"])
        repo_status["pid"] = record.get("pid")
        repo_status["repo_url"] = record.get("record_url")


async def _finalize_one(cfg: dict, *, build_dir: Path, previous_output_dir: str) -> str:
    """Copies the product's own core files (see each web service's own
    copy_prepared_output_files) into this repo's user-configured
    output_dir, then resolves output_mode — same three choices each
    single-repo publish endpoint already offered, just computed here since
    chaining is now internal (see the module's own docstring)."""
    repo = cfg["repo"]
    output_dir = Path(cfg["output_dir"])
    output_mode = cfg.get("output_mode", "prepared")

    if repo == "hfh":
        await asyncio.to_thread(hfh_service.copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)
    elif repo == "zenodo":
        await asyncio.to_thread(zenodo_service.copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)
    elif repo == "b2share":
        await asyncio.to_thread(b2share_service.copy_prepared_output_files, output_dir=build_dir, target_dir=output_dir)

    if output_mode == "passthrough":
        return previous_output_dir
    if output_mode == "downloaded":
        download_dir = output_dir.parent / f"{output_dir.name}-downloaded"
        if repo == "hfh":
            await asyncio.to_thread(hfh_service.download_from_repo, repo_id=cfg["repo_id"], token=cfg["token"], target_dir=download_dir)
            return str(download_dir)
        if repo == "zenodo":
            record = json.loads((build_dir / zenodo_cli.RECORD_FILENAME).read_text(encoding="utf-8"))
            await asyncio.to_thread(
                zenodo_service.download_files_from_zenodo, environment=cfg["environment"],
                deposition_id=record["deposition_id"], token=cfg["token"], target_dir=download_dir,
            )
            return str(download_dir)
        if repo == "b2share":
            record = json.loads((build_dir / b2share_cli.RECORD_FILENAME).read_text(encoding="utf-8"))
            if record.get("pid"):
                await asyncio.to_thread(
                    b2share_service.download_files_from_b2share, environment=cfg["environment"],
                    record_id=record["record_id"], token=cfg["token"], target_dir=download_dir,
                )
                return str(download_dir)
    return str(output_dir)


def start_publish_all_task(*, input_dir: Path, repos: list[dict], primary_doi_source: str | None) -> str:
    task_id = str(uuid.uuid4())
    _publish_tasks[task_id] = {
        "status": "running",
        "repos": {cfg["repo"]: _initial_repo_status() for cfg in repos},
    }
    settings = load_settings()

    async def _run() -> None:
        build_dirs: dict[str, Path] = {}
        try:
            current_input_dir = input_dir
            for cfg in repos:
                repo = cfg["repo"]
                repo_status = _publish_tasks[task_id]["repos"][repo]
                repo_status["status"] = "running"
                build_dir = Path(tempfile.mkdtemp(prefix=f"{repo}-build-"))
                build_dirs[repo] = build_dir
                await _upload_one(cfg, input_dir=current_input_dir, build_dir=build_dir, settings=settings, repo_status=repo_status)
                current_input_dir = build_dir

            changed = await asyncio.to_thread(doi_populate.populate, build_dirs, primary_doi_source=primary_doi_source)
            for cfg in repos:
                if changed.get(cfg["repo"]):
                    await _reupload_one(cfg, build_dir=build_dirs[cfg["repo"]])

            previous_output_dir = str(input_dir)
            for cfg in repos:
                repo = cfg["repo"]
                repo_status = _publish_tasks[task_id]["repos"][repo]
                build_dir = build_dirs[repo]
                await _lock_one(cfg, build_dir=build_dir, repo_status=repo_status)
                final_output_dir = await _finalize_one(cfg, build_dir=build_dir, previous_output_dir=previous_output_dir)
                repo_status["output_dir"] = final_output_dir
                repo_status["status"] = "done"
                repo_status["stage"] = "done"
                previous_output_dir = final_output_dir

            _publish_tasks[task_id]["status"] = "done"
        except Exception as exc:
            _publish_tasks[task_id]["status"] = "error"
            _publish_tasks[task_id]["error"] = str(exc)
            for repo, repo_status in _publish_tasks[task_id]["repos"].items():
                if repo_status["status"] == "running":
                    repo_status["status"] = "error"
                    repo_status["error"] = str(exc)
        finally:
            for build_dir in build_dirs.values():
                shutil.rmtree(build_dir, ignore_errors=True)

    asyncio.create_task(_run())
    return task_id
