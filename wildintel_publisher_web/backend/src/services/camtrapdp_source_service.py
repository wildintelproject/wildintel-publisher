"""Camtrap DP source fetching from a public URL for the web backend — thin
wrapper around wildintel_publisher.services.camtrapdp_source.
fetch_camtrap_dp_archive(), Camtrap DP's third way of obtaining its raw
source (alongside Trapper — trapper_service.py — and an already-local
directory). Same background-task-polled-by-task_id pattern, since a
download+validate can take a while, just like a Trapper fetch or a git
clone (see software_service.py)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from wildintel_publisher.config import get_camtrapdp_archive_output_dir, get_working_output_dir
from wildintel_publisher.services.camtrapdp_source import (
    fetch_camtrap_dp_archive,
    resolve_local_camtrapdp_source,
)

# Simple in-memory task store {task_id: {status, path, error}} — one process,
# no persistence across restarts, same trade-off trapper_service.py's own
# _download_tasks/software_service.py's _clone_tasks make.
_fetch_tasks: dict[str, dict[str, Any]] = {}


def start_fetch_task(url: str, *, clear_cache: bool = False) -> str:
    """Launches 'fetch_camtrap_dp_archive' as a background asyncio task (via
    a worker thread, since it's a blocking/synchronous call) and returns a
    task_id immediately. Poll get_fetch_task_status(task_id) for progress."""
    task_id = str(uuid.uuid4())
    _fetch_tasks[task_id] = {"status": "running", "path": None, "error": None}
    output_dir = get_camtrapdp_archive_output_dir()

    async def _run() -> None:
        try:
            path = await asyncio.to_thread(fetch_camtrap_dp_archive, url, output_dir, clear_cache=clear_cache)
            _fetch_tasks[task_id] = {"status": "done", "path": str(path), "error": None}
        except Exception as exc:
            _fetch_tasks[task_id] = {"status": "error", "path": None, "error": str(exc)}

    asyncio.create_task(_run())
    return task_id


def get_fetch_task_status(task_id: str) -> dict[str, Any] | None:
    return _fetch_tasks.get(task_id)


def resolve_local_source(path: str) -> dict[str, Any]:
    """Copies `path`'s core Camtrap DP files into an app-owned working
    directory and validates it — synchronous (no task_id/polling like
    start_fetch_task's above), since it's just a handful of small local
    files, not a network download. Returns {status, workingDir, sourceDir,
    error}, mirroring the shape the frontend already expects from a source
    resolution step."""
    try:
        working_dir = resolve_local_camtrapdp_source(Path(path), get_working_output_dir())
        return {"status": "valid", "workingDir": str(working_dir), "sourceDir": path, "error": None}
    except Exception as exc:
        return {"status": "invalid", "workingDir": None, "sourceDir": path, "error": str(exc)}
