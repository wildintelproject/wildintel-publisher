"""Fetches a Camtrap DP product from a public URL pointing to a zip
archive — this product type's third way of obtaining its raw source,
alongside a Trapper fetch (trapper.py) or an already-local directory (see
services.camtrapdp_adapter).

Reuses the same download/zip/validate steps as
services.gbif.validate_camtrap_dp_archive (which only checks a
--archive-url upfront, in a throwaway temp dir), but PERSISTS the extracted
directory instead of discarding it — the whole point here is to keep what
gets fetched, since the URL used to fetch it is then directly reusable as
GBIF's own --archive-url (already confirmed public and a valid Camtrap DP,
by the same validation this module runs on the way in).
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import httpx

from wildintel_publisher.services import common

DEFAULT_TIMEOUT = 300


def _slug_from_url(url: str) -> str:
    """Derives a filesystem-safe directory name from a URL, e.g.
    'https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip'
    -> 'camtrapdp-remote'."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = re.sub(r"\.zip$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^\w.-]", "-", name).strip("-")
    return name or "camtrapdp"


def fetch_camtrap_dp_archive(
    url: str, output_dir: Path, *, clear_cache: bool = False, timeout: int = DEFAULT_TIMEOUT,
) -> Path:
    """Downloads `url` (must be a zip archive containing a whole Camtrap DP
    package), validates it against the official Camtrap DP schema, and
    extracts it into output_dir/<slug>, returning that directory.

    clear_cache=True removes any pre-existing extraction at that
    destination first and re-fetches from scratch — same "clear_cache"
    contract trapper.fetch_camtrapdp_package/git_source.clone_repository's
    own flags have. Without it, an existing non-empty destination is reused
    as-is (no re-fetch).

    Raises:
        RuntimeError: if `url` isn't http(s), can't be downloaded, isn't a
        real zip archive, or the extracted content doesn't pass Camtrap DP
        validation (frictionless) — the message identifies which.
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        raise RuntimeError(f"Source URL must be a public http(s) URL, got: {url}")

    destination = output_dir / _slug_from_url(url)

    if clear_cache and destination.exists():
        shutil.rmtree(destination)

    if destination.is_dir() and any(destination.iterdir()):
        return destination

    with tempfile.TemporaryDirectory(prefix="camtrapdp-archive-fetch-") as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "archive.zip"
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Could not download {url}: HTTP {response.status_code}.")
                with zip_path.open("wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not download {url}: {exc}") from exc

        if not zipfile.is_zipfile(zip_path):
            raise RuntimeError(
                f"{url} is not a valid zip archive — it must be a zip containing the whole Camtrap "
                "DP package (e.g. camtrapdp-remote.zip), not a bare datapackage.json."
            )

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        camtrap_dp_root = common.find_camtrap_dp_root(extract_dir)
        common.validate_camtrap_dp(camtrap_dp_root)

        output_dir.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(camtrap_dp_root), str(destination))

    return destination
