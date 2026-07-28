"""FastAPI router — fetching a Camtrap DP from a public URL pointing to a
zip archive (Camtrap DP's third source-obtaining step, alongside Trapper —
api/routers/trapper.py — and a local directory, see
services.camtrapdp_source_service)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas.requests import CamtrapDPArchiveFetchRequest
from services import camtrapdp_source_service

router = APIRouter(prefix="/api/camtrapdp", tags=["camtrapdp"])


@router.post("/fetch-archive")
async def fetch_archive(req: CamtrapDPArchiveFetchRequest) -> dict:
    """Start fetching req.url as a background task. Returns a task_id; poll
    GET /api/camtrapdp/fetch-archive/{task_id} for status."""
    task_id = camtrapdp_source_service.start_fetch_task(req.url, clear_cache=req.clear_cache)
    return {"task_id": task_id}


@router.get("/fetch-archive/{task_id}")
def fetch_archive_status(task_id: str) -> dict:
    """Poll the status of a Camtrap DP archive fetch task."""
    status = camtrapdp_source_service.get_fetch_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status
