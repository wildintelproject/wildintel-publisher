"""Generic "what am I publishing" abstraction so hfh/zenodo/b2share don't
need to know the shape of the underlying product (a Camtrap DP package, a
YOLO dataset, ...). Each product type gets its own ProductAdapter (see
camtrapdp_adapter.py, yolo_adapter.py) that knows how to validate/extract
metadata/copy its own files; the repo services only ever deal with the
generic metadata.json envelope this module reads/writes.

Pipeline shape:
  1. Once the raw product is obtained (Trapper download, a local directory
     picked by the user...), generate_metadata_json() is called ONCE: it
     validates the product and best-effort extracts its generic metadata
     (title, description, version, license, authors, homepage), writing
     metadata.json alongside the raw product files.
  2. If missing_required_fields() on the result is non-empty, the product
     itself didn't provide everything we need — the UI collects the rest
     from the user and calls update_metadata_json() to fill the gaps before
     moving on.
  3. From then on, every publish step's input_dir carries both the raw
     product AND metadata.json. Each repo's prepare_*_export reads
     metadata.json (via read_metadata_json) to learn the product_type (and
     look up the right adapter) and the already-extracted fields — it never
     re-derives them from the underlying format.
  4. Once a repo finishes publishing, it calls append_publish_history() on
     the metadata.json it carried into its own output_dir, recording what it
     did — that's the flow's accumulating history, travelling forward to
     whichever repo publishes next.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

METADATA_FILENAME = "metadata.json"

CAMTRAPDP = "camtrapdp"
YOLO = "yolo"
SOFTWARE = "software"

# Filenames every repo's prepare_*_export writes on top of a product's own
# files — a generic zip bundler (see zip_directory) excludes these so it
# only ever packs the product's actual data, regardless of product type.
GENERATED_FILENAMES = {
    "README.md", "LICENSE", "CITATION.cff", "checksums-sha256.txt", METADATA_FILENAME,
}


class ProductAdapter(Protocol):
    """One implementation per product type. All paths are real directories
    on disk; all methods are synchronous (called from a background thread by
    the web backend, same as the rest of the publish pipeline)."""

    product_type: str

    def validate(self, input_dir: Path) -> None:
        """Raises RuntimeError if input_dir doesn't look like a valid
        product of this type."""
        ...

    def extract_metadata(self, input_dir: Path) -> dict:
        """Returns {"title", "description", "version", "license" (id/name/url
        dict), "authors" (list of {name, affiliation}), "homepage"} — called
        once, right after the product is obtained, to seed metadata.json.

        Raises:
            RuntimeError: if a required field (title/description/license/
            authors) can't be determined from the product.
        """
        ...

    def checkout_release(self, input_dir: Path, *, version: Optional[str]) -> None:
        """Best-effort: if this product type's raw source is a git checkout
        and `version` matches an available tag, switches input_dir to that
        exact tag before anything gets packaged — so what gets published
        actually matches the version metadata.json ends up citing, instead
        of whatever the default branch's HEAD happened to be at clone time.
        Called once (see generate_metadata_json), right after
        extract_metadata (which is what determined `version` in the first
        place). No-op for product types with nothing analogous — only
        SoftwareAdapter's raw source is a git checkout in this pipeline's
        sense."""
        ...

    def prepare(self, input_dir: Path, output_dir: Path, *, mirror: bool, image_timeout: int) -> None:
        """Copies/generates this product type's own files into output_dir
        (already created) — the product-specific equivalent of what used to
        be prepare_hfh_export's file-copy/media-filter/image-mirror section."""
        ...

    def anonymize_coordinates(self, input_dir: Path, *, decimals: int) -> None:
        """Mutates `input_dir` in place, rounding whatever GPS coordinates
        this product type has to `decimals` places — a privacy option for
        sensitive locations, applied once (see generate_metadata_json) as a
        product-level preprocessing step, before any repo-specific prepare
        even runs. Only means anything to CamtrapDPAdapter (rounds
        deployments.csv's latitude/longitude — see
        common.anonymize_deployment_coordinates); other product types accept
        and ignore it, having no coordinates of their own."""
        ...

    def extract_core_files(self, output_dir: Path, target_dir: Path) -> None:
        """Copies just this product type's own files out of an
        already-prepared output_dir (which also has repo-specific extras —
        README.md, LICENSE, CITATION.cff, checksums, images/, zip...) into
        target_dir — used by output_mode='prepared' (see
        hfh_service/zenodo_service/b2share_service.copy_prepared_output_files
        in the web backend) so the next repo in the publish order gets back
        a clean copy of the product, with this step's modifications applied
        (e.g. private media filtered out), and none of this repo's extras."""
        ...

    def link_media_to_hfh(self, output_dir: Path, hfh_repo_id: str) -> int:
        """Rewrites whatever this product type has as "where the media
        lives" to the predictable URL pattern of an HFH repo (its own,
        freshly published one — hfh.py's mirror-mode upload — or an
        external, already-published one — zenodo.py/b2share.py's link mode).
        No-op (returns 0) for product types with no such remote reference to
        rewrite (e.g. media that isn't referenced by URL at all)."""
        ...

    def bundle_local_zip(self, output_dir: Path, zip_path: Path, *, embed_images: bool) -> None:
        """Writes a single self-contained zip of this product's own files —
        for repos like Zenodo that don't host folder structures."""
        ...

    def readme_context(self, output_dir: Path) -> dict:
        """Extra template variables specific to this product type's own
        file structure/content — merged into the repo-generic README
        context (title, description, version, license_id, apa_citation,
        repo_id...) before rendering. {} for product types whose README
        template needs nothing beyond the generic context."""
        ...


class ProductLicense(BaseModel):
    """Shape of metadata.json's "license" — matches
    services.common.resolve_license's return value."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str | None = None
    url: str | None = None


class ProductAuthor(BaseModel):
    """Shape of one entry in metadata.json's "authors" — matches
    services.common.resolve_authors's return value."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    affiliation: str | None = None


class ProductMetadata(BaseModel):
    """Schema of metadata.json — the generic envelope every ProductAdapter's
    extract_metadata() feeds into and every repo's prepare_*_export reads
    back. Only describes the document's shape (field types/names); whether
    a given field must actually be present for a specific product type is
    each adapter's own business rule (see extract_metadata's RuntimeErrors
    for missing title/description/license/authors), not enforced here."""

    model_config = ConfigDict(extra="forbid")

    product_type: str
    title: str | None = None
    description: str | None = None
    version: str | None = None
    license: ProductLicense | None = None
    authors: list[ProductAuthor] = Field(default_factory=list)
    homepage: str | None = None
    publish_history: list[dict[str, Any]] = Field(default_factory=list)


# Fields the extractor tries to fill from the product itself but that we
# genuinely need regardless — if any is still empty after extract_metadata,
# the UI should ask the user to fill it in before proceeding (see
# missing_required_fields). "homepage" is deliberately excluded: it's the
# one field allowed to stay null indefinitely (only set once a repo
# publishes in mirror mode — see write_homepage), never something to block on.
REQUIRED_METADATA_FIELDS = ("title", "description", "version", "license", "authors")


_ADAPTERS: dict[str, ProductAdapter] = {}


def register_adapter(adapter: ProductAdapter) -> None:
    _ADAPTERS[adapter.product_type] = adapter


def registered_product_types() -> list[str]:
    return sorted(_ADAPTERS)


def get_adapter(product_type: str) -> ProductAdapter:
    try:
        return _ADAPTERS[product_type]
    except KeyError:
        raise RuntimeError(
            f"Unknown product type {product_type!r} — no ProductAdapter registered for it "
            f"(known types: {', '.join(sorted(_ADAPTERS)) or 'none'})."
        ) from None


def metadata_path(directory: Path) -> Path:
    return directory / METADATA_FILENAME


def write_metadata_json(directory: Path, data: dict) -> None:
    """Validates `data` against ProductMetadata before writing — raises
    RuntimeError if it doesn't match metadata.json's schema (wrong field
    types, unknown fields...). The dict itself, not the validated model, is
    what gets serialized, so callers keep getting back exactly what they
    put in (no fields silently added/reordered)."""
    try:
        ProductMetadata.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"metadata.json content is invalid: {exc}") from exc
    metadata_path(directory).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_metadata_json(directory: Path) -> dict:
    path = metadata_path(directory)
    if not path.is_file():
        raise RuntimeError(
            f"{path} not found — this input was not generated by generate_metadata_json "
            "(or an earlier publish step didn't carry it forward)."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc
    try:
        ProductMetadata.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"{path} does not match the expected metadata.json schema: {exc}") from exc
    return data


def _preserve_foreign_metadata_json(directory: Path) -> None:
    """If `directory` already has its own metadata.json that ISN'T one this
    tool wrote — i.e. it doesn't validate as ProductMetadata — renames it
    aside (SOURCE_metadata.json) before generate_metadata_json overwrites it
    below, so an unrelated file that just happens to share the name isn't
    silently destroyed. Most likely with a git-cloned software application
    (see software_adapter.py), whose raw source is arbitrary and could
    reasonably contain its own metadata.json for entirely unrelated reasons
    — Trapper downloads/curated YOLO directories essentially never do.

    A metadata.json that DOES validate is treated as ours (e.g. re-running
    generate_metadata_json on an already-processed directory — see this
    function's own idempotent contract) and is left alone, to be overwritten
    in place as before."""
    path = metadata_path(directory)
    if not path.is_file():
        return
    try:
        ProductMetadata.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError):
        pass
    else:
        return  # already ours — fine to overwrite in place

    destination = directory / f"SOURCE_{METADATA_FILENAME}"
    suffix = 1
    while destination.exists():
        destination = directory / f"SOURCE_{suffix}_{METADATA_FILENAME}"
        suffix += 1
    path.rename(destination)


def generate_metadata_json(
    product_type: str, input_dir: Path, *,
    anonymize_coordinates: bool = False, coordinate_decimals: int = 2,
) -> dict:
    """The "before the flow starts" step: validates the raw product, extracts
    whatever generic metadata it can from it, and writes metadata.json into
    input_dir — from here on, every publish step in the pipeline reads/
    carries this file forward instead of re-deriving anything from the
    underlying format.

    If `anonymize_coordinates` is True, also mutates input_dir in place
    (see ProductAdapter.anonymize_coordinates) before extracting metadata —
    a product-level preprocessing step, applied exactly once here, so every
    repo that later prepares its own export from this same input_dir (or
    from another repo's already-prepared output, chained forward) inherits
    the same already-anonymized coordinates automatically, with no
    per-repository flag of its own.

    extract_metadata is best-effort: a field it couldn't determine from the
    product comes back as None/[] rather than raising, so the caller should
    check missing_required_fields() on the result and, if anything's
    missing, collect it from the user (see update_metadata_json) before
    moving on to the actual publish steps.

    Also calls ProductAdapter.checkout_release with whatever version
    extract_metadata determined — for a software application, switches its
    git checkout to the matching tag (if one exists) before anything gets
    packaged, so what's published actually matches the version being
    cited. metadata.json's own fields are still the ones extract_metadata
    read *before* this switch — if a repository's tagged release's
    CITATION.cff genuinely differs from its default branch's, the exported
    metadata won't perfectly match the checked-out code (accepted
    trade-off, avoids a second extract pass).

    Raises:
        RuntimeError: if the product itself doesn't validate (see
        ProductAdapter.validate) — this is unrelated to individual metadata
        fields being missing.
    """
    adapter = get_adapter(product_type)
    adapter.validate(input_dir)
    _preserve_foreign_metadata_json(input_dir)
    if anonymize_coordinates:
        adapter.anonymize_coordinates(input_dir, decimals=coordinate_decimals)
    metadata = adapter.extract_metadata(input_dir)
    adapter.checkout_release(input_dir, version=metadata.get("version"))
    data = {"product_type": product_type, **metadata, "publish_history": []}
    write_metadata_json(input_dir, data)
    return data


def missing_required_fields(data: dict) -> list[str]:
    """Which of REQUIRED_METADATA_FIELDS are still empty in `data` — the
    extractor couldn't determine them from the product itself, so the UI
    should ask the user to fill them in before proceeding to the actual
    publish steps."""
    return [field for field in REQUIRED_METADATA_FIELDS if not data.get(field)]


def update_metadata_json(directory: Path, updates: dict) -> dict:
    """Merges user-supplied values into an existing metadata.json — used
    once generate_metadata_json couldn't determine every required field on
    its own (see missing_required_fields) and the UI collected the rest
    from the user. Re-validates and re-writes the file, and returns the
    merged result."""
    data = read_metadata_json(directory)
    data.update(updates)
    write_metadata_json(directory, data)
    return data


def copy_metadata_json(input_dir: Path, output_dir: Path) -> None:
    """Carries metadata.json (with its accumulated publish_history) forward
    from one step's input to its own output, so a later append_publish_history
    call (or the next step in the pipeline) has it."""
    write_metadata_json(output_dir, read_metadata_json(input_dir))


def write_homepage(directory: Path, url: str) -> None:
    """Sets/overwrites metadata.json's "homepage" — called by a repo's
    upload step in mirror mode, once the repo is known to exist, so a later
    publish step in the pipeline can detect it (e.g. to prefill the HFH
    repository fields on the Zenodo/B2SHARE forms) instead of asking the
    user to retype it. Not called in link mode: the media stays wherever it
    already was, so this repo isn't really the media's home."""
    data = read_metadata_json(directory)
    data["homepage"] = url
    write_metadata_json(directory, data)


def append_publish_history(output_dir: Path, entry: dict) -> None:
    """Records what a publish step did (repo, mode, where it published, what
    output_mode was reported) into metadata.json's history — called after a
    successful upload, on the metadata.json copy_metadata_json already
    carried into this same output_dir."""
    data = read_metadata_json(output_dir)
    data.setdefault("publish_history", []).append(entry)
    write_metadata_json(output_dir, data)


def zip_directory(source_dir: Path, zip_path: Path, *, exclude_names: set[str] = frozenset()) -> None:
    """Generic zip bundler: packs every file under source_dir (relative
    paths preserved) except zip_path itself and anything in exclude_names —
    used by product types (like YOLO) with no product-specific packing
    quirks. Camtrap DP keeps using common.write_local_zip instead, since it
    also needs to rewrite media.csv's filePath to a relative path first."""
    from zipfile import ZipFile

    with ZipFile(zip_path, "w") as zf:
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file() or file_path == zip_path or file_path.name in exclude_names:
                continue
            zf.write(file_path, file_path.relative_to(source_dir).as_posix())
