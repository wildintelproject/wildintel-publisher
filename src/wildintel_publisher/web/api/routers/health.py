"""FastAPI router — health check and version info."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

import httpx
from fastapi import APIRouter

router = APIRouter(tags=["health"])

_GITHUB_RELEASES = "https://api.github.com/repos/wildintelproject/wildintel-publisher/releases/latest"


def _current_version() -> str:
    try:
        return _pkg_version("wildintel-publisher")
    except PackageNotFoundError:
        return "dev"


def _parse(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("-")[0].split(".")[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/api/version")
async def version_check() -> dict:
    current = _current_version()

    if current == "dev":
        return {"current": current, "latest": None, "update_available": False, "release_url": None}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(_GITHUB_RELEASES, headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            data = r.json()
            latest = data.get("tag_name", "").lstrip("v")
            return {
                "current": current,
                "latest": latest,
                "update_available": _parse(latest) > _parse(current),
                "release_url": data.get("html_url"),
            }
    except Exception:
        return {"current": current, "latest": None, "update_available": False, "release_url": None}
