"""Software application source fetching for the web backend — thin wrapper
around wildintel_publisher.services.git_source.clone_repository(), the
"software" product type's equivalent of trapper_service.py's download task
(same background-task-polled-by-task_id pattern, since a clone can take a
while just like a Trapper fetch)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from wildintel_publisher.config import get_software_output_dir
from wildintel_publisher.services.git_source import clone_repository

# Simple in-memory task store {task_id: {status, path, error}} — one process,
# no persistence across restarts, same trade-off trapper_service.py's own
# _download_tasks makes.
_clone_tasks: dict[str, dict[str, Any]] = {}


def start_clone_task(url: str, *, clear_cache: bool = False) -> str:
    """Launches 'clone_repository' as a background asyncio task (via a
    worker thread, since it's a blocking/synchronous call) and returns a
    task_id immediately. Poll get_clone_task_status(task_id) for progress."""
    task_id = str(uuid.uuid4())
    _clone_tasks[task_id] = {"status": "running", "path": None, "error": None}
    output_dir = get_software_output_dir()

    async def _run() -> None:
        try:
            path = await asyncio.to_thread(clone_repository, url, output_dir, clear_cache=clear_cache)
            _clone_tasks[task_id] = {"status": "done", "path": str(path), "error": None}
        except Exception as exc:
            _clone_tasks[task_id] = {"status": "error", "path": None, "error": str(exc)}

    asyncio.create_task(_run())
    return task_id


def get_clone_task_status(task_id: str) -> dict[str, Any] | None:
    return _clone_tasks.get(task_id)
