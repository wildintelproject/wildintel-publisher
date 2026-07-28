"""FastAPI router — cloning a software application's source from a git
repository URL (the "software" product type's source-obtaining step, see
services.software_service)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas.requests import SoftwareCloneRequest
from services import software_service

router = APIRouter(prefix="/api/software", tags=["software"])


@router.post("/clone")
async def clone(req: SoftwareCloneRequest) -> dict:
    """Start cloning req.url as a background task. Returns a task_id; poll
    GET /api/software/clone/{task_id} for status."""
    task_id = software_service.start_clone_task(req.url, clear_cache=req.clear_cache)
    return {"task_id": task_id}


@router.get("/clone/{task_id}")
def clone_status(task_id: str) -> dict:
    """Poll the status of a git clone task."""
    status = software_service.get_clone_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status
