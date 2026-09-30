"""Obtains a Camtrap DP product's raw source when it's a public URL pointing
to a zip archive, or an already-local directory — two of this product
type's three ways of obtaining its raw source, alongside a Trapper fetch
(trapper.py).

fetch_camtrap_dp_archive() reuses the same download/zip/validate steps as
services.gbif.validate_camtrap_dp_archive (which only checks a
--archive-url upfront, in a throwaway temp dir), but PERSISTS the extracted
directory instead of discarding it — the whole point here is to keep what
gets fetched, since the URL used to fetch it is then directly reusable as
GBIF's own --archive-url (already confirmed public and a valid Camtrap DP,
by the same validation this module runs on the way in).

resolve_local_camtrapdp_source() gives the local-directory case the same
"never touch the original" property those two already have — see its own
docstring."""
from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import httpx

from wildintel_publisher.config import settings
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


def _fix_license_from_trapper_settings(output_dir: Path) -> None:
    """Same patch trapper.fetch_camtrapdp_package applies to Trapper's own
    "private" license placeholder, using the exact same configured defaults
    (settings.CAMTRAPDP.license_id/license_name/license_url — 'camtrapdp config
    set license_id=...' to change them) — a Camtrap DP that reaches this
    project via Local Directory or Public URL is very often itself a
    Trapper export that just didn't go through 'trapper download' directly
    (e.g. downloaded as a zip and extracted by hand), so it can carry that
    same placeholder Trapper's own get_package_metadata() writes when no
    real license was set at generation time. A no-op if CAMTRAPDP.license_id
    isn't configured, or if every scope already has a real license — see
    common.fix_datapackage_license."""
    if settings.CAMTRAPDP.license_id:
        # WildINTEL project policy: every dataset is published under
        # CC-BY-NC-4.0 (see CamtrapDPSettings.license_id's own comment in
        # config.py) — this is the actual value edited into the camtrapdp's
        # datapackage.json below, deliberately fixed rather than something
        # meant to vary per project/dataset.
        common.fix_datapackage_license(
            output_dir,
            license_id=settings.CAMTRAPDP.license_id,
            license_name=settings.CAMTRAPDP.license_name,
            license_url=settings.CAMTRAPDP.license_url,
        )


def resolve_local_camtrapdp_source(source_dir: Path, output_dir: Path, *, use_hash_subdir: bool = True) -> Path:
    """Takes a local directory the user pointed at as a Camtrap DP source
    and returns a working COPY of just its core files (datapackage.json +
    deployments/media/observations.csv) under output_dir/<slug> — never the
    original `source_dir` itself, so the rest of the pipeline
    (generate_metadata_json's validate/anonymize/randomize, all of which
    mutate their input in place) never touches the user's own files. Any
    media referenced by relative path in media.csv is deliberately NOT
    copied here — it stays at `source_dir`, read from there later (only) by
    the mirror step, via ProductAdapter.prepare's own media_dir parameter.

    use_hash_subdir=False skips the <slug> subfolder, using `output_dir`
    itself as the destination — for a caller whose own `output_dir` is
    already unique per source (the web backend's own session_dir/source,
    see services.camtrapdp_source_service.resolve_local_source), where the
    hash exists only to dedupe several distinct local sources sharing ONE
    output_dir — never the case there, so the extra nesting is pure noise.
    True (the default) keeps that dedupe for a caller that DOES reuse one
    shared output_dir across different local sources (the CLI's own
    'prepare' commands, via a single get_*_output_dir()).

    Always re-copies from scratch (no caching): these are a handful of small
    CSV/JSON files, cheap to redo, and caching would risk serving a stale
    copy if the user edits their original files between calls.

    If the tables are still gzip-compressed (e.g. a Trapper export
    downloaded as a zip and extracted by hand, whose tables Trapper itself
    would normally decompress on the way in — see trapper.fetch_camtrapdp_package),
    copy_core_camtrapdp_files picks up the `.gz` counterpart when the plain
    `.csv` isn't present, and decompress_gzipped_tables below unpacks it
    (and clears datapackage.json's own "compression" marker) before
    validating — without this, frictionless failed with a "No such file or
    directory: .../deployments.csv.gz" that never got any clearer than that.

    Same reasoning for the license: if it's still Trapper's own "private"
    placeholder, _fix_license_from_trapper_settings patches it with
    whatever's configured for 'trapper download' — otherwise extract_metadata's
    own resolve_license call finds no real license at all and the wizard
    has to ask for one by hand, even though generating this same package via
    'trapper download' directly would never have hit that.

    Raises:
        RuntimeError: if `source_dir` doesn't exist or isn't a directory, or
        if the copied core files don't pass Camtrap DP validation
        (frictionless) — same failure mode as fetch_camtrap_dp_archive.
    """
    if not source_dir.is_dir():
        raise RuntimeError(f"{source_dir} does not exist or is not a directory.")

    if use_hash_subdir:
        slug = hashlib.sha1(str(source_dir.resolve()).encode("utf-8")).hexdigest()[:16]
        destination = output_dir / slug
    else:
        destination = output_dir

    if destination.exists():
        shutil.rmtree(destination)

    common.copy_core_camtrapdp_files(source_dir, destination)
    common.decompress_gzipped_tables(destination)
    _fix_license_from_trapper_settings(destination)
    common.validate_camtrap_dp(destination)

    return destination


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
        # A Camtrap DP standard-compliant archive from a source this project
        # doesn't control could still ship gzip-compressed tables (this
        # project's own generated zips never do) — same fix as
        # resolve_local_camtrapdp_source, same underlying failure mode
        # otherwise ("No such file or directory: .../deployments.csv.gz").
        common.decompress_gzipped_tables(camtrap_dp_root)
        _fix_license_from_trapper_settings(camtrap_dp_root)
        common.validate_camtrap_dp(camtrap_dp_root)

        output_dir.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(camtrap_dp_root), str(destination))

    return destination
