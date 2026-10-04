"""FastAPI router — YOLO (AI Dataset) sources: a session-owned working copy
of a local dataset, and the wizard's metadata editor for the keys this tool
adds to its data.yaml (see services.yolo_service)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from wildintel_publisher.web.schemas.requests import LocalSourceResolveRequest, UpdateDataYamlRequest
from wildintel_publisher.web.services import yolo_service

router = APIRouter(prefix="/api/yolo", tags=["yolo"])


@router.post("/resolve-local-source")
def resolve_local_source(req: LocalSourceResolveRequest) -> dict:
    """Copies req.path's data.yaml into a session-owned working directory
    (images/labels stay where they are) and validates the dataset — same
    contract as /api/camtrapdp/resolve-local-source."""
    return yolo_service.resolve_local_source(req.path, task_id=req.session_task_id)


@router.get("/data-yaml-fields")
def data_yaml_fields(path: str) -> dict:
    """title/description/version/homepage/license/authors from
    <path>/data.yaml, plus its classes, images per split and validation
    warnings — works before generate-metadata has ever run."""
    try:
        return yolo_service.read_data_yaml_fields(Path(path))
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/update-data-yaml")
def update_data_yaml(req: UpdateDataYamlRequest) -> dict:
    """Writes the edited metadata keys into <req.input_dir>/data.yaml (the
    working copy). Meant to be called BEFORE /api/camtrapdp/generate-metadata,
    which re-reads them from there."""
    try:
        yolo_service.update_data_yaml(Path(req.input_dir), req.fields())
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}
