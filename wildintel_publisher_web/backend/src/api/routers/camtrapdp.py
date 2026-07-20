"""FastAPI router — reading/serving an already-obtained product directory
(Camtrap DP, a YOLO dataset...; regardless of source: Trapper today, a local
directory picked by the user)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas.requests import GenerateMetadataRequest, OpenFolderRequest, UpdateMetadataRequest
from services import camtrapdp_service

router = APIRouter(prefix="/api/camtrapdp", tags=["camtrapdp"])
logger = logging.getLogger(__name__)


@router.post("/generate-metadata")
def generate_metadata(req: GenerateMetadataRequest) -> dict:
    """The "before the flow starts" step: validates the product and writes
    metadata.json into req.input_dir (see
    services.product.generate_metadata_json) — required once, right after a
    product is obtained (download finishes, or a local directory is picked),
    before any publish step or /summary call can use it."""
    try:
        return camtrapdp_service.generate_metadata(req.product_type, Path(req.input_dir))
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/complete-metadata")
def complete_metadata(req: UpdateMetadataRequest) -> dict:
    """Fills in whatever generate-metadata's best-effort extraction
    couldn't determine from the product itself (see
    services.product.missing_required_fields) — the wizard calls this once
    the user has supplied the missing fields, merging only what's actually
    provided into the existing metadata.json."""
    updates = req.model_dump(exclude={"input_dir"}, exclude_none=True)
    try:
        return camtrapdp_service.update_metadata(Path(req.input_dir), updates)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/summary")
def summary(path: str) -> dict:
    """Title/description/version/license/authors/homepage/product_type from
    <path>/metadata.json (see generate_metadata)."""
    try:
        return camtrapdp_service.read_summary(Path(path))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/download")
def download(path: str) -> FileResponse:
    """Serves <path>/datapackage.json for download."""
    file_path = camtrapdp_service.datapackage_path(Path(path))
    if not file_path.is_file():
        raise HTTPException(404, f"{file_path} not found.")
    return FileResponse(file_path, filename="datapackage.json", media_type="application/json")


@router.post("/open-folder")
def open_folder(req: OpenFolderRequest) -> dict:
    """Opens <path> in the OS's native file manager."""
    try:
        camtrapdp_service.open_folder(Path(req.path))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        logger.warning("Could not open folder %s: %s", req.path, exc)
        raise HTTPException(500, f"Could not open the folder: {exc}") from exc
    return {"ok": True}
