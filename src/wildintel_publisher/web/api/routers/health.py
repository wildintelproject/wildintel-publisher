"""FastAPI router — health check and version info."""
from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import httpx
from fastapi import APIRouter

router = APIRouter(tags=["health"])

_GITHUB_RELEASES = "https://api.github.com/repos/wildintelproject/wildintel-publisher/releases"
# The CLI and the web app are released independently (see CHANGELOG.md): the
# web app's own releases are the ones tagged web-vX.Y.Z.
_WEB_TAG_PREFIX = "web-v"


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


def _platform_keyword() -> str:
    system = platform.system()
    return {"Windows": "windows", "Darwin": "macos"}.get(system, "linux")


def _download_url(release: dict) -> str | None:
    """The release asset built for this OS (named ...-linux-x86_64,
    ...-windows-x86_64.exe...), else the release's own page."""
    keyword = _platform_keyword()
    for asset in release.get("assets") or []:
        if keyword in asset.get("name", "").lower():
            return asset.get("browser_download_url")
    return release.get("html_url")


def _latest_web_release(releases: list[dict]) -> dict | None:
    candidates = [
        r for r in releases
        if r.get("tag_name", "").startswith(_WEB_TAG_PREFIX) and not r.get("draft") and not r.get("prerelease")
    ]
    return max(candidates, key=lambda r: _parse(r["tag_name"].removeprefix(_WEB_TAG_PREFIX)), default=None)


@router.get("/api/version")
async def version_check() -> dict:
    """Whether a newer web-app release exists. "error" is set when that
    couldn't be found out (offline, GitHub's rate limit...) — distinct from
    "up to date", so the UI can offer a retry."""
    current = _current_version()
    result = {
        "current": current, "latest": None, "update_available": False,
        "release_url": None, "download_url": None, "error": None,
    }
    if current == "dev":
        return result

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                _GITHUB_RELEASES, params={"per_page": 30}, headers={"Accept": "application/vnd.github+json"},
            )
            r.raise_for_status()
            release = _latest_web_release(r.json())
    except Exception as exc:
        return {**result, "error": f"Could not check for updates: {exc}"}

    if release is None:
        return result
    latest = release["tag_name"].removeprefix(_WEB_TAG_PREFIX)
    return {
        **result, "latest": latest, "update_available": _parse(latest) > _parse(current),
        "release_url": release.get("html_url"), "download_url": _download_url(release),
    }
