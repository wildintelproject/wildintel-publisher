"""ProductAdapter for YOLO-format datasets — proves the ProductAdapter
abstraction actually generalizes beyond Camtrap DP.

Expected layout:
    images/
    ├── train/
    │   ├── img001.jpg
    │   └── ...
    ├── val/
    │   └── ...
    └── test/          (optional — train/val are required, test isn't)
        └── ...
    labels/              (optional — YOLO training labels, one .txt per image,
    ├── train/            same train/val/test split layout as images/; not
    │   └── ...            read or validated by this tool, just carried
    ├── val/                along if present)
    └── test/
        └── ...
    data.yaml

data.yaml is the standard YOLO config (train/val/test split paths, nc,
names) plus a handful of optional top-level keys this tool reads for
metadata.json (not part of the YOLO spec itself, but harmless extra keys
that YOLO training scripts simply ignore): title, description, version,
license (a string treated as the license id, or a {id, name, url} mapping),
authors (a list of {name, affiliation}), homepage.

Unlike Camtrap DP, a YOLO dataset's images are already local, plain files —
there's no per-image "public/private" flag, no remote URL to mirror or link
to. So `mirror` is accepted (for interface parity with the Camtrap DP
adapter) but has no effect: the images/ tree is always copied in full,
regardless of the "Mode" (Mirror/Link) the user picked in the wizard.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import yaml

from wildintel_publisher.services import product

DATA_YAML_FILENAME = "data.yaml"
IMAGES_DIRNAME = "images"
LABELS_DIRNAME = "labels"
REQUIRED_SPLITS = ["train", "val"]
OPTIONAL_SPLITS = ["test"]


def _data_yaml_path(directory: Path) -> Path:
    return directory / DATA_YAML_FILENAME


def _copy_splits(source_dir: Path, target_dir: Path, dirname: str) -> None:
    """Copies each existing split (train/val/test) of `dirname` (images or
    labels) from source_dir/dirname/<split> to target_dir/dirname/<split> —
    a no-op for a split that doesn't exist in source_dir (e.g. no labels/ at
    all, or no optional test/ split)."""
    source_root = source_dir / dirname
    target_root = target_dir / dirname
    for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
        split_dir = source_root / split
        if split_dir.is_dir():
            shutil.copytree(split_dir, target_root / split, dirs_exist_ok=True)


def _load_data_yaml(directory: Path) -> dict:
    path = _data_yaml_path(directory)
    if not path.is_file():
        raise RuntimeError(f"{path} not found — a YOLO dataset needs a data.yaml at its root.")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a YAML mapping at the top level.")
    return data


def _resolve_license(value) -> dict:
    if isinstance(value, dict):
        license_id = value.get("id") or value.get("name")
        if not license_id:
            raise RuntimeError("data.yaml's 'license' mapping needs at least an 'id' or 'name'.")
        return {"id": license_id, "name": value.get("name") or license_id, "url": value.get("url") or ""}
    if isinstance(value, str) and value.strip():
        return {"id": value.strip(), "name": value.strip(), "url": ""}
    raise RuntimeError(
        "data.yaml has no real 'license' (string id, or a {id, name, url} mapping) — "
        "add one before publishing."
    )


def _resolve_authors(value) -> list:
    authors = []
    for author in value or []:
        if not isinstance(author, dict):
            continue
        name = author.get("name")
        if not name:
            continue
        authors.append({"name": name, "affiliation": author.get("affiliation") or ""})
    if authors:
        return authors
    raise RuntimeError("data.yaml has no 'authors' entry with a 'name' — add at least one before publishing.")


class YoloAdapter:
    product_type = product.YOLO

    def validate(self, input_dir: Path) -> None:
        _load_data_yaml(input_dir)  # raises if missing/invalid YAML

        images_dir = input_dir / IMAGES_DIRNAME
        if not images_dir.is_dir():
            raise RuntimeError(f"{images_dir} not found — a YOLO dataset needs an images/ directory.")

        for split in REQUIRED_SPLITS:
            split_dir = images_dir / split
            if not split_dir.is_dir() or not any(p.is_file() for p in split_dir.iterdir()):
                raise RuntimeError(
                    f"{split_dir} is missing or empty — a YOLO dataset needs at least one image "
                    f"in images/{split}/."
                )

    def extract_metadata(self, input_dir: Path) -> dict:
        """Best-effort: never raises for a missing title/description/
        license/authors — returns None/[] for whatever data.yaml doesn't
        provide, so generate_metadata_json can still write metadata.json
        and let the user fill the gaps afterwards (see
        product.missing_required_fields)."""
        data = _load_data_yaml(input_dir)
        try:
            license_info = _resolve_license(data.get("license"))
        except RuntimeError:
            license_info = None
        try:
            authors = _resolve_authors(data.get("authors"))
        except RuntimeError:
            authors = []
        return {
            "title": data.get("title"),
            "description": data.get("description"),
            "version": data.get("version"),
            "license": license_info,
            "authors": authors,
            "homepage": data.get("homepage"),
        }

    def prepare(self, input_dir: Path, output_dir: Path, *, mirror: bool, image_timeout: int) -> None:
        # image_timeout is accepted for interface parity with
        # CamtrapDPAdapter but unused: the images are already local files,
        # nothing to download. mirror does matter, though, same as Camtrap
        # DP: True copies the images/ (and labels/, if present) tree
        # alongside data.yaml (the repo ends up self-contained); False
        # copies only data.yaml — there's no "link to an external host" for
        # YOLO images, so link mode simply means the images/labels aren't
        # part of this particular publish.
        shutil.copy2(_data_yaml_path(input_dir), _data_yaml_path(output_dir))

        if mirror:
            _copy_splits(input_dir, output_dir, IMAGES_DIRNAME)
            _copy_splits(input_dir, output_dir, LABELS_DIRNAME)
            self.validate(output_dir)
        else:
            _load_data_yaml(output_dir)  # at least confirm the copy is valid YAML

    def extract_core_files(self, output_dir: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        data_yaml_source = _data_yaml_path(output_dir)
        if data_yaml_source.is_file():
            shutil.copy2(data_yaml_source, _data_yaml_path(target_dir))
            _copy_splits(output_dir, target_dir, IMAGES_DIRNAME)
            _copy_splits(output_dir, target_dir, LABELS_DIRNAME)
            return

        # --self-contained mode already bundled data.yaml/images/labels into a
        # zip and removed the loose copies (see bundle_local_zip/
        # common.cleanup_self_contained_sources) — pull them back out of that
        # zip instead, so this repo's own "prepared" output
        # (output_mode='prepared') and whatever repo comes next in the
        # publish order (see services.publish_orchestrator's chaining) still
        # get something usable.
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
        return 0  # nothing to rewrite — images/ has no remote-URL references

    def bundle_local_zip(self, output_dir: Path, zip_path: Path, *, embed_images: bool) -> None:
        # embed_images is always true in practice here: the images/ tree IS
        # the dataset, there's no "loose alongside the zip" mode like
        # Camtrap DP's camtrapdp-local.zip.
        product.zip_directory(output_dir, zip_path, exclude_names=product.GENERATED_FILENAMES)

    def readme_context(self, output_dir: Path) -> dict:
        data = _load_data_yaml(output_dir)
        names = data.get("names") or []
        if isinstance(names, dict):  # data.yaml also allows {0: "cat", 1: "dog", ...}
            names = [names[key] for key in sorted(names)]
        return {"num_classes": data.get("nc", len(names)), "class_names": names}


product.register_adapter(YoloAdapter())
