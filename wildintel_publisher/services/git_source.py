"""Fetches a "software" product's raw source via `git clone` — this product
type's equivalent of trapper.fetch_camtrapdp_package (Camtrap DP) or a
user-picked local directory (YOLO): the one way its raw files get onto disk
before generate_metadata_json ever runs (see services.software_adapter).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = 300


def _slug_from_url(url: str) -> str:
    """Derives a filesystem-safe directory name from a git URL, e.g.
    'https://github.com/user/repo.git' -> 'repo',
    'git@host:group/repo.git' -> 'repo'."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if "/" not in name:
        name = name.rsplit(":", 1)[-1]  # scp-like git@host:path form
    name = re.sub(r"\.git$", "", name)
    name = re.sub(r"[^\w.-]", "-", name).strip("-")
    return name or "repository"


def clone_repository(url: str, output_dir: Path, *, clear_cache: bool = False, timeout: int = DEFAULT_TIMEOUT) -> Path:
    """Clones `url` (shallow, depth=1) into output_dir/<repo-slug>, returning
    the resulting directory.

    clear_cache=True removes any pre-existing clone at that destination
    first and re-clones from scratch — same "clear_cache" contract
    trapper.fetch_camtrapdp_package's own flag has. Without it, an existing
    non-empty destination is reused as-is (no re-fetch), same trade-off
    Trapper's own cache makes.

    Raises:
        RuntimeError: if git isn't installed, the URL is unreachable/invalid,
        or the clone otherwise fails — wraps git's own stderr message.
    """
    destination = output_dir / _slug_from_url(url)

    if clear_cache and destination.exists():
        shutil.rmtree(destination)

    if destination.is_dir() and any(destination.iterdir()):
        return destination

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(destination)],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not installed or not available on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Cloning {url!r} timed out after {timeout}s.") from exc
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError(f"git clone failed for {url!r}: {(exc.stderr or '').strip() or exc}") from exc

    return destination
