"""FastAPI router — Trapper integration.

No server-side session: every endpoint resolves credentials fresh per call
(request body, falling back to settings.toml — see services.trapper_service).
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from trapper_client import err

from schemas.requests import ClassificationProjectsRequest, DeploymentsRequest, DownloadRequest, TrapperCredentials
from services import trapper_service

router = APIRouter(prefix="/api/trapper", tags=["trapper"])
logger = logging.getLogger(__name__)


def _http_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, err.UnauthorizedError):
        return HTTPException(401, "Incorrect Trapper username or password.")
    if isinstance(exc, err.ForbiddenError):
        return HTTPException(403, "You don't have permission to access this Trapper resource.")
    if isinstance(exc, err.NotFoundError):
        return HTTPException(404, "Trapper resource not found.")
    if isinstance(exc, err.APIError):
        return HTTPException(400, str(exc))
    if isinstance(exc, httpx.ConnectError):
        return HTTPException(502, f"Could not connect to the Trapper server: {exc}")
    if isinstance(exc, httpx.TimeoutException):
        return HTTPException(504, f"Timed out connecting to the Trapper server: {exc}")
    return HTTPException(400, str(exc))


def _resolve(req: TrapperCredentials) -> tuple[str, str, str]:
    try:
        return trapper_service.resolve_credentials(req.url, req.username, req.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/config")
def get_config() -> dict:
    """Current TRAPPER connection defaults from settings.toml (no password value)."""
    return trapper_service.get_connection_defaults()


@router.post("/test-connection")
def test_connection(req: TrapperCredentials) -> dict:
    """Verify Trapper credentials (without selecting any project yet), and
    save them to settings.toml once verified — so they don't need to be
    retyped next time."""
    url, username, password = _resolve(req)
    logger.info("Trapper test-connection: url=%s user=%s", url, username)
    try:
        result = trapper_service.test_connection(url, username, password)
    except Exception as exc:
        logger.warning("Trapper test-connection failed: %s", exc)
        raise _http_exc(exc) from exc
    trapper_service.save_credentials(url, username, password)
    return result


@router.post("/research-projects")
def research_projects(req: TrapperCredentials) -> dict:
    """List research projects accessible to the given Trapper user."""
    url, username, password = _resolve(req)
    try:
        return {"results": trapper_service.list_research_projects(url, username, password)}
    except Exception as exc:
        raise _http_exc(exc) from exc


@router.post("/classification-projects")
def classification_projects(req: ClassificationProjectsRequest) -> dict:
    """List classification projects belonging to a research project."""
    url, username, password = _resolve(req)
    try:
        return {"results": trapper_service.list_classification_projects(
            url, username, password, req.research_project_pk,
        )}
    except Exception as exc:
        raise _http_exc(exc) from exc


@router.post("/deployments")
def deployments(req: DeploymentsRequest) -> dict:
    """List deployments belonging to a classification project."""
    url, username, password = _resolve(req)
    try:
        return {"results": trapper_service.list_deployments(
            url, username, password, req.classification_project_pk,
        )}
    except Exception as exc:
        raise _http_exc(exc) from exc


@router.post("/download")
async def download(req: DownloadRequest) -> dict:
    """Start fetching the Camtrap DP package as a background task.
    Returns a task_id; poll GET /api/trapper/download/{task_id} for status."""
    url, username, password = _resolve(req)
    logger.info(
        "Trapper download requested: project_id=%d deployment_id=%s clear_cache=%s",
        req.project_id, req.deployment_id, req.clear_cache,
    )
    task_id = trapper_service.start_download_task(
        url=url, username=username, password=password,
        project_id=req.project_id, deployment_id=req.deployment_id, clear_cache=req.clear_cache,
    )
    return {"task_id": task_id}


@router.get("/download/{task_id}")
def download_status(task_id: str) -> dict:
    """Poll the status of a Camtrap DP download task."""
    status = trapper_service.get_download_task_status(task_id)
    if status is None:
        raise HTTPException(404, f"Task {task_id!r} not found.")
    return status
