"""Camtrap DP source fetching from a public URL for the web backend — thin
wrapper around wildintel_publisher.services.camtrapdp_source.
fetch_camtrap_dp_archive(), Camtrap DP's third way of obtaining its raw
source (alongside Trapper — trapper_service.py — and an already-local
directory). Same background-task-polled-by-task_id pattern, since a
download+validate can take a while, just like a Trapper fetch or a git
clone (see software_service.py)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from wildintel_publisher.services.camtrapdp_source import (
    fetch_camtrap_dp_archive,
    resolve_local_camtrapdp_source,
)

from services import session_store

# Simple in-memory task store {task_id: {status, path, error}} — one process,
# no persistence across restarts, same trade-off trapper_service.py's own
# _download_tasks/software_service.py's _clone_tasks make.
_fetch_tasks: dict[str, dict[str, Any]] = {}


async def _run_fetch(task_id: str, *, url: str, output_dir: Path, clear_cache: bool) -> None:
    """Shared by start_fetch_task (fresh request) and resume_fetch_task (an
    earlier interruption's own url, replayed) — see trapper_service.py's
    _run_fetch for the identical shape (in-memory poll status + session
    manifest, updated together on success or failure)."""
    fetch = {"source_type": "archive", "params": {"url": url, "clear_cache": clear_cache}, "output_dir": str(output_dir), "input_dir": None}
    try:
        path = await asyncio.to_thread(fetch_camtrap_dp_archive, url, output_dir, clear_cache=clear_cache)
        _fetch_tasks[task_id] = {"status": "done", "path": str(path), "error": None}
        fetch["input_dir"] = str(path)
        session_store.write_fetch_phase(task_id, product_type="camtrapdp", source_type="archive", fetch=fetch, status="done", error=None)
    except Exception as exc:
        _fetch_tasks[task_id] = {"status": "error", "path": None, "error": str(exc)}
        session_store.write_fetch_phase(task_id, product_type="camtrapdp", source_type="archive", fetch=fetch, status="error", error=str(exc))


def start_fetch_task(url: str, *, clear_cache: bool = False) -> str:
    """Mints a brand new session (see session_store's own docstring) and
    launches the fetch in it — its task_id then flows through preprocessing
    and, if the user gets that far, into services.publish_orchestrator's
    own start_publish_all_task(task_id=...). Poll get_fetch_task_status
    (task_id) for progress."""
    task_id = session_store.new_task_id()
    _fetch_tasks[task_id] = {"status": "running", "path": None, "error": None}
    output_dir = session_store.session_dir(task_id) / "source"
    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="archive",
        fetch={"source_type": "archive", "params": {"url": url, "clear_cache": clear_cache}, "output_dir": str(output_dir), "input_dir": None},
        status="running", error=None,
    )

    asyncio.create_task(_run_fetch(task_id, url=url, output_dir=output_dir, clear_cache=clear_cache))
    return task_id


def resume_fetch_task(task_id: str) -> str:
    """Resumes a public-URL Camtrap DP fetch an earlier interruption left
    on disk — same url as the original request (see
    session_store.write_fetch_phase). No credentials involved, unlike
    Trapper — a public URL needs none."""
    manifest = session_store.read_manifest(task_id)
    if manifest is None or manifest.get("fetch", {}).get("source_type") != "archive":
        raise RuntimeError(f"No interrupted archive fetch session found for task {task_id!r}.")
    params = manifest["fetch"]["params"]
    output_dir = Path(manifest["fetch"]["output_dir"])

    _fetch_tasks[task_id] = {"status": "running", "path": None, "error": None}
    asyncio.create_task(_run_fetch(task_id, url=params["url"], output_dir=output_dir, clear_cache=params["clear_cache"]))
    return task_id


def get_fetch_task_status(task_id: str) -> dict[str, Any] | None:
    return _fetch_tasks.get(task_id)


def resolve_local_source(path: str, *, task_id: str | None = None) -> dict[str, Any]:
    """Copies `path`'s core Camtrap DP files into an app-owned working
    directory INSIDE a session (see services.session_store) and validates
    it — synchronous (no polling like start_fetch_task's above), since it's
    just a handful of small local files, not a network download, but still
    gets a session_dir of its own so the working copy (and, later, its
    metadata.json) survives a browser reload instead of living in a
    generic, path-keyed scratch folder that a later, unrelated call could
    reuse/overwrite. Mints a fresh task_id on the very first call for a
    given LocalDirectoryForm instance; every later call for that same form
    (the debounced live-preview re-running as the user keeps editing the
    path, see the frontend) passes that same task_id back in, so it keeps
    reusing the one session_dir instead of leaking a new one per keystroke.

    Returns {status, workingDir, sourceDir, taskId, error} — "taskId" is
    always the session's own task_id (even on failure, so a failed attempt
    can still be retried against the same session instead of minting yet
    another one), mirroring the shape the frontend already expects from a
    source resolution step."""
    task_id = task_id or session_store.new_task_id()
    output_dir = session_store.session_dir(task_id) / "source"
    fetch = {"source_type": "local", "params": {"path": path}, "output_dir": str(output_dir), "input_dir": None}
    try:
        # use_hash_subdir=False: output_dir is already unique to this
        # session (see session_store), so the hash exists only for the
        # CLI's own shared-output_dir usage — nesting it here too would
        # just be a pointless <session_dir>/source/<hash> level.
        working_dir = resolve_local_camtrapdp_source(Path(path), output_dir, use_hash_subdir=False)
        fetch["input_dir"] = str(working_dir)
        session_store.write_fetch_phase(
            task_id, product_type="camtrapdp", source_type="local", fetch=fetch, status="done", error=None,
        )
        return {"status": "valid", "workingDir": str(working_dir), "sourceDir": path, "taskId": task_id, "error": None}
    except Exception as exc:
        session_store.write_fetch_phase(
            task_id, product_type="camtrapdp", source_type="local", fetch=fetch, status="error", error=str(exc),
        )
        return {"status": "invalid", "workingDir": None, "sourceDir": path, "taskId": task_id, "error": str(exc)}
