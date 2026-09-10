"""Software application source fetching for the web backend — thin wrapper
around wildintel_publisher.services.git_source.clone_repository(), the
"software" product type's equivalent of trapper_service.py's download task
(same background-task-polled-by-task_id pattern, since a clone can take a
while just like a Trapper fetch)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from wildintel_publisher.services.git_source import clone_repository

from services import session_store

# Simple in-memory task store {task_id: {status, path, error}} — one process,
# no persistence across restarts, same trade-off trapper_service.py's own
# _download_tasks makes.
_clone_tasks: dict[str, dict[str, Any]] = {}


async def _run_clone(task_id: str, *, url: str, output_dir: Path, clear_cache: bool) -> None:
    """Shared by start_clone_task (fresh request) and resume_clone_task (an
    earlier interruption's own url, replayed) — see trapper_service.py's
    _run_fetch for the identical shape (in-memory poll status + session
    manifest, updated together on success or failure)."""
    fetch = {"source_type": "git", "params": {"url": url, "clear_cache": clear_cache}, "output_dir": str(output_dir), "input_dir": None}
    try:
        path = await asyncio.to_thread(clone_repository, url, output_dir, clear_cache=clear_cache)
        _clone_tasks[task_id] = {"status": "done", "path": str(path), "error": None}
        fetch["input_dir"] = str(path)
        session_store.write_fetch_phase(task_id, product_type="software", source_type="git", fetch=fetch, status="done", error=None)
    except Exception as exc:
        _clone_tasks[task_id] = {"status": "error", "path": None, "error": str(exc)}
        session_store.write_fetch_phase(task_id, product_type="software", source_type="git", fetch=fetch, status="error", error=str(exc))


def start_clone_task(url: str, *, clear_cache: bool = False) -> str:
    """Mints a brand new session (see session_store's own docstring) and
    launches the clone in it — its task_id then flows through
    preprocessing and, if the user gets that far, into
    services.publish_orchestrator's own start_publish_all_task(task_id=...).
    Poll get_clone_task_status(task_id) for progress."""
    task_id = session_store.new_task_id()
    _clone_tasks[task_id] = {"status": "running", "path": None, "error": None}
    output_dir = session_store.session_dir(task_id) / "source"
    session_store.write_fetch_phase(
        task_id, product_type="software", source_type="git",
        fetch={"source_type": "git", "params": {"url": url, "clear_cache": clear_cache}, "output_dir": str(output_dir), "input_dir": None},
        status="running", error=None,
    )

    asyncio.create_task(_run_clone(task_id, url=url, output_dir=output_dir, clear_cache=clear_cache))
    return task_id


def resume_clone_task(task_id: str) -> str:
    """Resumes a git clone an earlier interruption left on disk — same url
    as the original request (see session_store.write_fetch_phase). No
    credentials involved — a git clone URL needs none here."""
    manifest = session_store.read_manifest(task_id)
    if manifest is None or manifest.get("fetch", {}).get("source_type") != "git":
        raise RuntimeError(f"No interrupted git clone session found for task {task_id!r}.")
    params = manifest["fetch"]["params"]
    output_dir = Path(manifest["fetch"]["output_dir"])

    _clone_tasks[task_id] = {"status": "running", "path": None, "error": None}
    asyncio.create_task(_run_clone(task_id, url=params["url"], output_dir=output_dir, clear_cache=params["clear_cache"]))
    return task_id


def get_clone_task_status(task_id: str) -> dict[str, Any] | None:
    return _clone_tasks.get(task_id)
