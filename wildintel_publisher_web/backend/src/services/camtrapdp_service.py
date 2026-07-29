"""Reading/serving an already-obtained product directory (Camtrap DP, a YOLO
dataset...) via its generic metadata.json (see
wildintel_publisher.services.product) — despite the historical
"camtrapdp" name (kept so existing /api/camtrapdp/* frontend callers don't
need to change), nothing here is Camtrap DP-specific anymore other than
datapackage_path (used only by the /download endpoint, which does remain
Camtrap DP-only — a YOLO dataset has no datapackage.json to download).
"""
from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path

from wildintel_publisher.services import product
from wildintel_publisher.services.common import DATAPACKAGE_FILENAME

# Matches metadata.json's "homepage" once hfh_service.upload_to_huggingface
# has set it (mirror mode only — see product.write_homepage): lets the
# Zenodo/B2SHARE forms detect an already-published HuggingFace Hub repo
# straight from the input product instead of asking the user to retype it.
_HFH_HOMEPAGE_PATTERN = re.compile(r"^https://huggingface\.co/datasets/([^/]+/[^/]+)/?$")


def datapackage_path(output_dir: Path) -> Path:
    return output_dir / DATAPACKAGE_FILENAME


def generate_metadata(
    product_type: str, input_dir: Path, *,
    anonymize_coordinates: bool = False, coordinate_decimals: int = 2,
    randomize_media_ids: bool = False,
) -> dict:
    """The "before the flow starts" step (see product.generate_metadata_json)
    — validates the raw product and best-effort extracts its metadata into
    metadata.json, so every publish step from here on can read it instead of
    re-deriving anything from the underlying format.

    anonymize_coordinates/coordinate_decimals (Camtrap DP only) round
    deployments.csv's latitude/longitude in input_dir itself, once, here —
    a product-level preprocessing step every later repo-specific prepare
    step inherits automatically, with no flag of its own.

    randomize_media_ids (Camtrap DP only) replaces every mediaID that isn't
    already a UUID, same "applied once here" shape.

    The caller should check product.missing_required_fields() on the
    result — if it's non-empty, the product itself didn't provide
    everything needed and the wizard should collect the rest from the user
    (see update_metadata) before moving on.

    Raises:
        RuntimeError: if the product itself doesn't validate (see
        ProductAdapter.validate) — unrelated to individual fields missing.
    """
    return product.generate_metadata_json(
        product_type, input_dir,
        anonymize_coordinates=anonymize_coordinates, coordinate_decimals=coordinate_decimals,
        randomize_media_ids=randomize_media_ids,
    )


def update_metadata(input_dir: Path, updates: dict) -> dict:
    """Merges user-supplied values into an existing metadata.json — used
    once generate_metadata's best-effort extraction couldn't determine
    every required field on its own and the wizard collected the rest from
    the user."""
    return product.update_metadata_json(input_dir, updates)


def detect_hfh_repo_id(homepage: str | None) -> str | None:
    """Extracts a HuggingFace Hub repo_id ("user_or_org/dataset") from
    metadata.json's "homepage", if it matches the URL a previous 'hfh
    publish' step in mirror mode would have set (see product.write_homepage).

    Returns:
        None if homepage is empty or doesn't match — a product that was
        never mirror-published to HFH (link mode doesn't set it either,
        since the media doesn't actually live there).
    """
    if not homepage:
        return None
    match = _HFH_HOMEPAGE_PATTERN.match(homepage)
    return match.group(1) if match else None


def read_summary(input_dir: Path) -> dict:
    """Title/description/version/license/authors/homepage/product_type from
    metadata.json (see product.generate_metadata_json), plus hfh_repo_id
    detected from homepage (see detect_hfh_repo_id).

    Raises:
        FileNotFoundError: if input_dir/metadata.json doesn't exist (i.e.
        generate_metadata hasn't been called for it yet).
    """
    metadata_file = product.metadata_path(input_dir)
    if not metadata_file.is_file():
        raise FileNotFoundError(f"{metadata_file} not found.")
    data = product.read_metadata_json(input_dir)
    return {
        "product_type": data.get("product_type"),
        "title": data.get("title"),
        "description": data.get("description"),
        "version": data.get("version"),
        "license": data.get("license"),
        "authors": data.get("authors") or [],
        "homepage": data.get("homepage"),
        "hfh_repo_id": detect_hfh_repo_id(data.get("homepage")),
    }


def _opener_command(path: Path) -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return ["open", str(path)]
    if system == "Windows":
        return ["explorer", str(path)]
    return ["xdg-open", str(path)]


def open_folder(path: Path) -> None:
    """Opens `path` in the OS's native file manager.

    This is a local, single-user tool — the backend always runs on the same
    machine as the browser using it, same trust model as the rest of this
    app's path-taking endpoints.
    """
    if not path.is_dir():
        raise FileNotFoundError(f"{path} is not a directory.")
    subprocess.Popen(_opener_command(path), start_new_session=True)
