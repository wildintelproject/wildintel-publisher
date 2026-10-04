"""FastAPI router — local filesystem browsing, for the directory picker used
by the "Local Directory" Camtrap DP source."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from wildintel_publisher.web.schemas.requests import PickDirectoryRequest
from wildintel_publisher.web.services import native_dialog

router = APIRouter(prefix="/api/fs", tags=["fs"])
logger = logging.getLogger(__name__)


@router.get("/browse")
def browse(path: str = "") -> dict:
    """Subdirectories of `path`, for the directory picker.

    No `path` (or one that doesn't exist / isn't a directory) walks up to
    the nearest valid ancestor, falling back to the user's home directory —
    the picker never errors out on a stale starting path, it just corrects
    to somewhere sensible.
    """
    p = Path(path).resolve() if path else Path.home()
    while not p.exists() or not p.is_dir():
        parent = p.parent
        if parent == p:
            p = Path.home()
            break
        p = parent

    try:
        dirs = sorted(
            (item for item in p.iterdir() if item.is_dir() and not item.name.startswith(".")),
            key=lambda x: x.name.lower(),
        )
    except PermissionError as exc:
        logger.warning("Permission denied browsing %s", p)
        raise HTTPException(403, "Permission denied.") from exc

    return {
        "current": str(p),
        "parent": str(p.parent) if p.parent != p else None,
        "dirs": [{"name": d.name, "path": str(d)} for d in dirs],
    }


@router.post("/pick-directory")
def pick_directory(req: PickDirectoryRequest) -> dict:
    """Opens the operating system's own folder dialog (see
    services.native_dialog) and returns the chosen path — {"path": null}
    when the user cancels. 501 when this machine can't open one, so the
    frontend falls back to its in-page browser."""
    try:
        path = native_dialog.pick_directory(req.initial_path, req.title or "Select the directory")
    except native_dialog.NativeDialogUnavailable as exc:
        raise HTTPException(501, f"No native folder dialog available: {exc}") from exc
    return {"path": path}
