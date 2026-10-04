"""FastAPI router — fetching a Camtrap DP from a public URL pointing to a
zip archive (Camtrap DP's third source-obtaining step, alongside Trapper —
api/routers/trapper.py — and a local directory, see
services.camtrapdp_source_service)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from wildintel_publisher.web.schemas.requests import CamtrapDPArchiveFetchRequest, LocalSourceResolveRequest
from wildintel_publisher.web.services import camtrapdp_source_service

router = APIRouter(prefix="/api/camtrapdp", tags=["camtrapdp"])


@router.post("/fetch-archive")
async def fetch_archive(req: CamtrapDPArchiveFetchRequest) -> dict:
    """Start fetching req.url as a background task. Returns a task_id; poll
    GET /api/camtrapdp/fetch-archive/{task_id} for status."""
    task_id = camtrapdp_source_service.start_fetch_task(req.url, clear_cache=req.clear_cache)
    return {"task_id": task_id}


@router.post("/resolve-local-source")
def resolve_local_source(req: LocalSourceResolveRequest) -> dict:
    """Copies req.path's core Camtrap DP files into an app-owned working
    directory (inside a session — see services.session_store) and validates
    it. Synchronous — unlike fetch-archive/Trapper's download, this never
    touches the network, so it returns immediately instead of a task_id to
    poll; the response's own "taskId" is what the caller should thread
    through as req.session_task_id on every later call for this same form,
    and into generate-metadata/publish-start afterwards."""
    return camtrapdp_source_service.resolve_local_source(req.path, task_id=req.session_task_id)


@router.get("/fetch-archive/{task_id}")
def fetch_archive_status(task_id: str) -> dict:
    """Poll the status of a Camtrap DP archive fetch task."""
    status = camtrapdp_source_service.get_fetch_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status


@router.post("/fetch-archive/{task_id}/resume")
async def resume_fetch_archive(task_id: str) -> dict:
    """Resumes an interrupted public-URL fetch — same url as the original
    request (persisted in the session); no credentials to re-enter."""
    try:
        resumed_task_id = camtrapdp_source_service.resume_fetch_task(task_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"task_id": resumed_task_id}
