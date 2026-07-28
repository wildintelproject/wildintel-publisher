"""ProductAdapter for software applications — the raw product is whatever a
`git clone` of a repository URL produced (see services.git_source), minus
`.git` itself. Unlike Camtrap DP/YOLO there's no fixed expected layout, so
`CITATION.cff` (https://citation-file-format.github.io/) is required at the
repo's root and is the sole source `extract_metadata` reads from — the same
standard this project's own generated exports use, so a software repo
that's already citable this way needs no further input from the user.
"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import yaml

from wildintel_publisher.services import product

GIT_DIRNAME = ".git"
CITATION_CFF_FILENAME = "CITATION.cff"


def _git_remote_url(input_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(input_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    url = result.stdout.strip()
    return url or None


def _parse_citation_cff(path: Path) -> dict:
    """Reads title/description/version/license/authors from a CITATION.cff
    (CFF v1.1/1.2 schema) — `license` is a bare SPDX identifier (or the
    first of a list, if more than one applies), and `authors` entries are
    either a "person" (given-names/family-names) or an "entity" (name
    alone, e.g. an organization) — same two shapes this project's own
    CITATION.cff.j2 template writes."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}

    license_value = data.get("license")
    if isinstance(license_value, list):
        license_value = license_value[0] if license_value else None
    license_info = None
    if isinstance(license_value, str) and license_value.strip():
        license_info = {"id": license_value.strip(), "name": license_value.strip(), "url": ""}

    authors = []
    for entry in data.get("authors") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("given-names") or entry.get("family-names"):
            name = " ".join(part for part in (entry.get("given-names"), entry.get("family-names")) if part)
        else:
            name = entry.get("name")
        if name:
            authors.append({"name": name, "affiliation": entry.get("affiliation") or ""})

    return {
        "title": data.get("title"),
        "description": data.get("abstract"),
        "version": data.get("version"),
        "license": license_info,
        "authors": authors,
        "homepage": data.get("repository-code") or data.get("url"),
    }


class SoftwareAdapter:
    product_type = product.SOFTWARE

    def validate(self, input_dir: Path) -> None:
        if not (input_dir / GIT_DIRNAME).is_dir():
            raise RuntimeError(
                f"{input_dir} has no {GIT_DIRNAME}/ — a software application product must come "
                "from a git clone."
            )
        if not (input_dir / CITATION_CFF_FILENAME).is_file():
            raise RuntimeError(
                f"{input_dir} has no {CITATION_CFF_FILENAME} — a software application product must "
                "provide one at its repository root (see https://citation-file-format.github.io/), "
                "used as the source of its title/description/version/license/authors."
            )

    def extract_metadata(self, input_dir: Path) -> dict:
        """Reads title/description/version/license/authors from
        CITATION.cff (validate() already guarantees it exists) — never
        raises for a field CITATION.cff itself doesn't provide, returning
        None/[] for it instead (the UI collects the rest from the user
        afterwards, same as every other adapter). homepage falls back to
        the repo's own git remote if CITATION.cff has neither
        repository-code nor url."""
        metadata = _parse_citation_cff(input_dir / CITATION_CFF_FILENAME)
        if not metadata.get("homepage"):
            metadata["homepage"] = _git_remote_url(input_dir)
        return metadata

    def prepare(self, input_dir: Path, output_dir: Path, *, mirror: bool, image_timeout: int) -> None:
        # mirror/image_timeout accepted for interface parity with the other
        # adapters but unused — a software application has no media to
        # mirror/link, the whole cloned tree (minus .git) IS the product.
        for entry in input_dir.iterdir():
            if entry.name == GIT_DIRNAME:
                continue
            if entry.name == product.METADATA_FILENAME:
                # This is generate_metadata_json's OWN metadata.json (never
                # the product's own file — a genuinely foreign one already
                # got renamed aside to SOURCE_metadata.json by
                # product._preserve_foreign_metadata_json before this ever
                # ran). It's pipeline bookkeeping, copied into output_dir
                # separately and generically by each repo's own
                # prepare_<repo>_export (product.copy_metadata_json) — not
                # "the product's own files" this method is responsible for.
                continue
            destination = output_dir / entry.name
            if entry.name in product.GENERATED_FILENAMES:
                # The repo's own README.md/LICENSE/CITATION.cff would
                # otherwise be silently overwritten by prepare_<repo>_export's
                # generated citation-focused versions of those same
                # filenames — keep the project's own copy under a SOURCE_
                # prefix instead of losing it.
                destination = output_dir / f"SOURCE_{entry.name}"
            if entry.is_dir():
                shutil.copytree(entry, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, destination)

    def extract_core_files(self, output_dir: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        loose_files = [
            p for p in output_dir.iterdir()
            if p.name not in product.GENERATED_FILENAMES and p.suffix != ".zip"
        ]
        if loose_files:
            for entry in loose_files:
                destination = target_dir / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(entry, destination)
            return

        # --self-contained mode already bundled everything into a zip and
        # removed the loose copies (see common.cleanup_self_contained_sources)
        # — pull them back out of that zip instead, same fallback
        # yolo_adapter.YoloAdapter.extract_core_files uses.
        zip_path = next(output_dir.glob("*.zip"), None)
        if zip_path is None:
            return
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                destination = target_dir / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(zf.read(name))

    def link_media_to_hfh(self, output_dir: Path, hfh_repo_id: str) -> int:
        return 0  # no media of any kind to rewrite — a software product is never linked to HFH

    def bundle_local_zip(self, output_dir: Path, zip_path: Path, *, embed_images: bool) -> None:
        product.zip_directory(output_dir, zip_path, exclude_names=product.GENERATED_FILENAMES)

    def readme_context(self, output_dir: Path) -> dict:
        return {}


product.register_adapter(SoftwareAdapter())
