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
    ├── train/            same train/val/test split layout as images/;
    │   └── ...            validated if present, see _validate_labels)
    ├── val/
    └── test/
        └── ...
    data.yaml
    <anything else>      (optional — extra files/folders such as a statistics/
                          or lists/ folder, a paper, a .docx README...; gathered under additional_info/, see copy_extra_files)

Validation (see YoloAdapter.validate) is done with Pydantic models:
YoloDataYaml for data.yaml itself (split paths, nc vs names) and
YoloLabelLine for every line of every labels/ file (class id within nc,
normalized coordinates in [0, 1], bounding-box or polygon shape).
Structural problems raise; images with no label file (background images,
legitimate in YOLO) and label files with no image are only warnings (see
check_dataset, which returns them).

The web wizard never edits the user's own dataset: it works on a working
copy holding just data.yaml plus a pointer back to the original directory
for images/ and labels/ (see create_working_copy/dataset_root).

data.yaml is the standard YOLO config (train/val/test split paths, nc,
names) plus a handful of optional top-level keys this tool reads for
metadata.json (not part of the YOLO spec itself, but harmless extra keys
that YOLO training scripts simply ignore): title, description, version,
license (a string treated as the license id, or a {id, name, url} mapping),
authors (a list of {name, affiliation}), homepage, funding (extra text
appended to the README's Funding section), publisher (a {name,
website, email} mapping) and copyright_holders (a list of names).

Unlike Camtrap DP, a YOLO dataset's images are already local, plain files —
there's no per-image "public/private" flag, no remote URL to mirror or link
to. So `mirror` is accepted (for interface parity with the Camtrap DP
adapter) but has no effect: the images/ tree is always copied in full,
regardless of the "Mode" (Mirror/Link) the user picked in the wizard.
"""
from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Optional

import yaml
from PIL import Image
from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, NonNegativeInt, TypeAdapter, ValidationError,
    ValidationInfo, field_validator, model_validator,
)

from wildintel_publisher.core.services import common, product

DATA_YAML_FILENAME = "data.yaml"
IMAGES_DIRNAME = "images"
LABELS_DIRNAME = "labels"
REQUIRED_SPLITS = ["train", "val"]
OPTIONAL_SPLITS = ["test"]
# Same set Ultralytics itself accepts (ultralytics.data.utils.IMG_FORMATS).
IMAGE_SUFFIXES = {".bmp", ".dng", ".jpeg", ".jpg", ".mpo", ".png", ".tif", ".tiff", ".webp", ".pfm", ".heic"}
# How many individual problems each validation error message lists before
# summarizing the rest as a count — a broken export can have thousands.
MAX_REPORTED_PROBLEMS = 10

# Written into a web-wizard session's working copy (see
# create_working_copy) — points at the user's own dataset directory, where
# images/ and labels/ keep being read from, so only data.yaml needs copying.
SOURCE_POINTER_FILENAME = "yolo-source.json"

# Top-level names that are never "extra files": handled on their own
# (data.yaml, images/, labels/), pipeline bookkeeping (the source pointer), or
# editor leftovers nobody wants published (LibreOffice's .~lock.<file>#, .git).
_NOT_EXTRA_NAMES = {DATA_YAML_FILENAME, IMAGES_DIRNAME, LABELS_DIRNAME, SOURCE_POINTER_FILENAME, ".git"}
HF_METADATA_JSONL = "metadata.jsonl"
ADDITIONAL_INFO_DIRNAME = "additional_info"

logger = logging.getLogger(__name__)


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


def _is_extra_entry(entry: Path) -> bool:
    return entry.name not in _NOT_EXTRA_NAMES and not entry.name.startswith(".~lock.")


def _extra_entries(root: Path, *, own_metadata_json: bool) -> list[Path]:
    """Top-level files/folders of `root` besides data.yaml/images/labels —
    what the dataset's authors sent along (statistics, lists, a paper...).
    `own_metadata_json` says whether a metadata.json at root is this
    pipeline's own bookkeeping (root IS the input directory — never part of
    the dataset) or the dataset's own, unrelated file."""
    return sorted(
        entry for entry in root.iterdir()
        if _is_extra_entry(entry) and not (own_metadata_json and entry.name == product.METADATA_FILENAME)
    )


def _loose_extras(root: Path, *, own_metadata_json: bool) -> list[Path]:
    """The extras that sit loose in the dataset's root — i.e. everything
    _extra_entries finds except the additional_info/ folder itself."""
    return [e for e in _extra_entries(root, own_metadata_json=own_metadata_json) if e.name != ADDITIONAL_INFO_DIRNAME]


def _has_content(directory: Path) -> bool:
    return directory.is_dir() and any(directory.iterdir())


def copy_extra_files(root: Path, output_dir: Path, *, own_metadata_json: bool) -> None:
    """Gathers everything extra in the dataset's root (see _extra_entries)
    under output_dir/additional_info/ — so none of it can ever collide with
    a file this pipeline generates (README.md, LICENSE, CITATION.cff...).

    The dataset's own additional_info/ folder is copied as it is when there
    are no loose extras. When there are, and it isn't empty, its contents
    move one level down to additional_info/additional_info/ so the loose
    extras can sit directly in additional_info/ without mixing with them."""
    existing = root / ADDITIONAL_INFO_DIRNAME
    loose = _loose_extras(root, own_metadata_json=own_metadata_json)
    target = output_dir / ADDITIONAL_INFO_DIRNAME
    if not loose:
        if existing.is_dir():
            shutil.copytree(existing, target, dirs_exist_ok=True)
        return
    target.mkdir(exist_ok=True)
    if _has_content(existing):
        shutil.copytree(existing, target / ADDITIONAL_INFO_DIRNAME, dirs_exist_ok=True)
    for entry in loose:
        if entry.is_dir():
            shutil.copytree(entry, target / entry.name, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target / entry.name)


def source_conflicts(directory: Path) -> list[str]:
    """Warnings for what this pipeline does NOT publish where/as it found it:
    loose extras (moved into additional_info/), a Hub metadata.jsonl it
    replaces, and data.yaml itself when the wizard's metadata editor changed
    it."""
    root = dataset_root(directory)
    own_metadata_json = root.resolve() == directory.resolve()
    warnings = []
    loose = _loose_extras(root, own_metadata_json=own_metadata_json)
    if loose:
        warnings.append(
            f"{', '.join(f'{e.name}/' if e.is_dir() else e.name for e in loose)} will be published inside "
            f"{ADDITIONAL_INFO_DIRNAME}/ (not in the dataset's root)."
        )
        if _has_content(root / ADDITIONAL_INFO_DIRNAME):
            warnings.append(
                f"The dataset's own {ADDITIONAL_INFO_DIRNAME}/ will be published as "
                f"{ADDITIONAL_INFO_DIRNAME}/{ADDITIONAL_INFO_DIRNAME}/."
            )
    for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
        if (root / IMAGES_DIRNAME / split / HF_METADATA_JSONL).is_file():
            warnings.append(
                f"{IMAGES_DIRNAME}/{split}/{HF_METADATA_JSONL} already exists — the Hugging Face Hub export "
                f"generates its own; the original is kept as SOURCE_{HF_METADATA_JSONL}."
            )
    if root != directory and _data_yaml_path(root).is_file():
        try:
            changed = yaml.safe_load(_data_yaml_path(root).read_text(encoding="utf-8")) != _load_data_yaml(directory)
        except (yaml.YAMLError, OSError, RuntimeError):
            changed = False
        if changed:
            warnings.append(
                "data.yaml will be published with the metadata edited in the wizard (title, authors, license...); "
                "your original file is not modified, but YAML comments are lost in the published copy."
            )
    return warnings


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


def _error_message(error: dict) -> str:
    # Pydantic prefixes every message raised from a custom validator.
    return error["msg"].removeprefix("Value error, ")


def _format_validation_error(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {_error_message(error)}" for error in exc.errors()
    )


def _stringify_scalar(value: Any) -> Any:
    """YAML parses `version: 1.0` as a float and `title: 2024` as an int —
    both are meant as text here."""
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


YamlText = Annotated[Optional[str], BeforeValidator(_stringify_scalar)]


def _normalize_split_path(value: str) -> str:
    return PurePosixPath(value.strip().removeprefix("./")).as_posix()


class YoloDataYaml(BaseModel):
    """The training-config part of data.yaml — what validate() enforces.
    Extra keys (Ultralytics' own optional ones, and this tool's metadata
    keys — see YoloMetadata) are allowed and ignored here."""

    model_config = ConfigDict(extra="allow")

    train: str
    val: str
    test: Optional[str] = None
    nc: Optional[NonNegativeInt] = None
    names: list[str] | dict[int, str]

    @field_validator("train", "val", "test")
    @classmethod
    def _split_path_follows_the_supported_layout(cls, value: Optional[str], info: ValidationInfo) -> Optional[str]:
        if value is None:
            return None
        expected = f"{IMAGES_DIRNAME}/{info.field_name}"
        if _normalize_split_path(value) != expected:
            raise ValueError(
                f"must be {expected!r} — only the images/<split> layout is supported "
                f"(got {value!r})"
            )
        return value

    @field_validator("names")
    @classmethod
    def _names_as_an_ordered_list(cls, value: list[str] | dict[int, str]) -> list[str]:
        if isinstance(value, dict):
            if sorted(value) != list(range(len(value))):
                raise ValueError("a names mapping must use consecutive class ids starting at 0")
            value = [value[key] for key in sorted(value)]
        if not value:
            raise ValueError("must list at least one class")
        return value

    @model_validator(mode="after")
    def _nc_matches_names(self) -> "YoloDataYaml":
        if self.nc is not None and self.nc != len(self.names):
            raise ValueError(f"nc is {self.nc} but names lists {len(self.names)} classes")
        return self

    @property
    def num_classes(self) -> int:
        return len(self.names)


class YoloLicense(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: Optional[str] = None
    name: Optional[str] = None
    url: str = ""

    @model_validator(mode="after")
    def _needs_an_id_or_name(self) -> "YoloLicense":
        if not (self.id or self.name):
            raise ValueError("a license mapping needs at least an 'id' or 'name'")
        return self


class YoloAuthor(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1)]
    affiliation: YamlText = None


class YoloPublisher(BaseModel):
    """Same shape as metadata.json's own "publisher" (product.
    ProductPublisher): a CFF entity, rendered inside CITATION.cff's
    preferred-citation (see common.write_citation)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1)]
    website: Optional[str] = None
    email: Optional[str] = None


NonBlankText = Annotated[str, Field(min_length=1)]


class YoloMetadata(BaseModel):
    """This tool's own optional metadata keys in data.yaml — parsed
    best-effort by extract_metadata (see its own docstring), never by
    validate()."""

    model_config = ConfigDict(extra="ignore")

    title: YamlText = None
    description: YamlText = None
    version: YamlText = None
    homepage: YamlText = None
    funding: YamlText = None


def _resolve_publisher(value) -> Optional[dict]:
    try:
        return YoloPublisher.model_validate(value).model_dump(exclude_none=True)
    except ValidationError:
        return None


def _resolve_copyright_holders(value) -> list[str]:
    """Skips (rather than rejects) any entry that isn't a non-blank string."""
    return [name.strip() for name in value if isinstance(name, str) and name.strip()] if isinstance(value, list) else []


def parse_data_yaml(directory: Path) -> YoloDataYaml:
    data = _load_data_yaml(directory)
    try:
        return YoloDataYaml.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"{_data_yaml_path(directory)} is not a valid YOLO config: {_format_validation_error(exc)}"
        ) from exc


def _resolve_license(value) -> dict:
    if isinstance(value, str):
        value = {"id": value.strip()} if value.strip() else None
    try:
        license_info = YoloLicense.model_validate(value)
    except ValidationError as exc:
        raise RuntimeError(
            "data.yaml has no real 'license' (string id, or a {id, name, url} mapping) — "
            f"add one before publishing. ({_format_validation_error(exc)})"
        ) from exc
    license_id = license_info.id or license_info.name
    return {"id": license_id, "name": license_info.name or license_id, "url": license_info.url}


def _resolve_authors(value) -> list:
    """Skips (rather than rejects) any malformed entry — only fails when
    not a single usable author is left."""
    authors = []
    for entry in value if isinstance(value, list) else []:
        try:
            author = YoloAuthor.model_validate(entry)
        except ValidationError:
            continue
        authors.append({"name": author.name, "affiliation": author.affiliation or ""})
    if authors:
        return authors
    raise RuntimeError("data.yaml has no 'authors' entry with a 'name' — add at least one before publishing.")


NormalizedCoord = Annotated[float, Field(ge=0.0, le=1.0)]


class YoloLabelLine(BaseModel):
    """One line of a YOLO label file: `class x_center y_center width height`
    (detection) or `class x1 y1 x2 y2 x3 y3 ...` (segmentation polygon),
    every coordinate normalized to [0, 1]. The class id's upper bound (nc)
    comes from the validation context."""

    class_id: NonNegativeInt
    coords: list[NormalizedCoord]

    @field_validator("class_id")
    @classmethod
    def _class_id_within_nc(cls, value: int, info: ValidationInfo) -> int:
        num_classes = (info.context or {}).get("num_classes")
        if num_classes is not None and value >= num_classes:
            raise ValueError(f"class id {value} is out of range — data.yaml defines {num_classes} classes")
        return value

    @field_validator("coords")
    @classmethod
    def _bbox_or_polygon(cls, value: list[float]) -> list[float]:
        if len(value) == 4 or (len(value) >= 6 and len(value) % 2 == 0):
            return value
        raise ValueError(
            f"expected 4 values (x y w h) or an even number >= 6 (polygon), got {len(value)}"
        )


_LABEL_FILE_ADAPTER = TypeAdapter(list[YoloLabelLine])


def _label_rows(label_path: Path) -> tuple[list[int], list[dict]]:
    line_numbers, rows = [], []
    for number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.split()
        if tokens:
            line_numbers.append(number)
            rows.append({"class_id": tokens[0], "coords": tokens[1:]})
    return line_numbers, rows


def _split_files(split_dir: Path, *, suffixes: set[str]) -> dict[PurePosixPath, Path]:
    """Every file under split_dir with one of `suffixes`, keyed by its path
    relative to split_dir WITHOUT the suffix — the key an image and its
    label file share (images/train/a/b.jpg <-> labels/train/a/b.txt)."""
    if not split_dir.is_dir():
        return {}
    return {
        PurePosixPath(path.relative_to(split_dir).with_suffix("").as_posix()): path
        for path in split_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    }


def _summarize(problems: list[str]) -> str:
    shown = problems[:MAX_REPORTED_PROBLEMS]
    rest = len(problems) - len(shown)
    return "\n  - " + "\n  - ".join(shown) + (f"\n  ... and {rest} more" if rest else "")


def _validate_labels(dataset_root: Path, config: YoloDataYaml, images_by_split: dict[str, dict]) -> list[str]:
    labels_root = dataset_root / LABELS_DIRNAME
    if not labels_root.is_dir():
        return []
    problems: list[str] = []
    unlabeled_images, orphan_labels = 0, 0
    for split, images in images_by_split.items():
        labels = _split_files(labels_root / split, suffixes={".txt"})
        unlabeled_images += len(images.keys() - labels.keys())
        orphan_labels += len(labels.keys() - images.keys())
        for label_path in labels.values():
            line_numbers, rows = _label_rows(label_path)
            try:
                _LABEL_FILE_ADAPTER.validate_python(rows, context={"num_classes": config.num_classes})
            except ValidationError as exc:
                rel = label_path.relative_to(dataset_root).as_posix()
                for error in exc.errors():
                    row_index, *field = error["loc"]
                    where = ".".join(str(part) for part in field)
                    problems.append(f"{rel}:{line_numbers[row_index]} ({where}): {_error_message(error)}")
    if problems:
        raise RuntimeError(f"{len(problems)} invalid label line(s) under {labels_root}:{_summarize(problems)}")
    warnings = []
    if unlabeled_images:
        warnings.append(
            f"{unlabeled_images} image(s) under {dataset_root / IMAGES_DIRNAME} have no label file — "
            "fine if they're meant as background images."
        )
    if orphan_labels:
        warnings.append(f"{orphan_labels} label file(s) under {labels_root} have no matching image.")
    return warnings


class YoloSourcePointer(BaseModel):
    """Contents of SOURCE_POINTER_FILENAME."""

    root: Path

    @field_validator("root")
    @classmethod
    def _an_existing_absolute_directory(cls, value: Path) -> Path:
        if not value.is_absolute() or not value.is_dir():
            raise ValueError(f"{value} is not an existing absolute directory")
        return value


def dataset_root(directory: Path) -> Path:
    """Where `directory`'s images/ and labels/ actually live: `directory`
    itself, unless it's a working copy (see create_working_copy) whose
    pointer file names the user's original dataset directory."""
    pointer_path = directory / SOURCE_POINTER_FILENAME
    if not pointer_path.is_file():
        return directory
    try:
        return YoloSourcePointer.model_validate_json(pointer_path.read_text(encoding="utf-8")).root
    except ValidationError as exc:
        raise RuntimeError(f"{pointer_path} is invalid: {_format_validation_error(exc)}") from exc


def create_working_copy(source_dir: Path, working_dir: Path) -> Path:
    """Copies just `source_dir`'s data.yaml into `working_dir`, plus a
    pointer back to `source_dir` for its images/ and labels/ (never
    copied — they can be gigabytes) — so the web wizard's metadata editor
    (see update_editable_fields) and metadata.json never touch the user's
    own files. Always re-copies data.yaml, so a later call picks up edits
    made to the original in between."""
    if not source_dir.is_dir():
        raise RuntimeError(f"{source_dir} does not exist or is not a directory.")
    source_yaml = _data_yaml_path(source_dir)
    if not source_yaml.is_file():
        raise RuntimeError(f"{source_yaml} not found — a YOLO dataset needs a data.yaml at its root.")
    working_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_yaml, _data_yaml_path(working_dir))
    pointer = YoloSourcePointer(root=source_dir.resolve())
    (working_dir / SOURCE_POINTER_FILENAME).write_text(pointer.model_dump_json(), encoding="utf-8")
    return working_dir


def check_dataset(directory: Path) -> list[str]:
    """Validates the dataset at `directory` (see the module docstring) and
    returns its warnings — non-blocking problems worth showing the user.

    Raises:
        RuntimeError: on anything that makes the dataset unpublishable.
    """
    config = parse_data_yaml(directory)
    root = dataset_root(directory)

    images_dir = root / IMAGES_DIRNAME
    if not images_dir.is_dir():
        raise RuntimeError(f"{images_dir} not found — a YOLO dataset needs an images/ directory.")

    warnings = []
    images_by_split = {}
    for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
        split_dir = images_dir / split
        images = _split_files(split_dir, suffixes=IMAGE_SUFFIXES)
        if split in REQUIRED_SPLITS and not images:
            raise RuntimeError(
                f"{split_dir} is missing or has no images — a YOLO dataset needs at least one image "
                f"({', '.join(sorted(IMAGE_SUFFIXES))}) in images/{split}/."
            )
        if split == "test" and config.test and not images:
            # Only needed when evaluating on the test split — not a reason
            # to block publishing.
            warnings.append(f"data.yaml declares a 'test' split, but {split_dir} has no images.")
        if images:
            images_by_split[split] = images
        other_files = sum(
            1 for path in split_dir.rglob("*")
            if path.is_file() and path.suffix.lower() not in IMAGE_SUFFIXES
        ) if split_dir.is_dir() else 0
        if other_files:
            warnings.append(f"{other_files} non-image file(s) under {split_dir} will be published as-is.")

    return [*warnings, *source_conflicts(directory), *_validate_labels(root, config, images_by_split)]


def dataset_statistics(directory: Path, config: YoloDataYaml) -> dict:
    """Per-split image/label/object counts and per-class object counts, for
    the README. Counts only what's actually on disk (images under
    images/<split>, their label files under labels/<split>) — meant to run
    after check_dataset, so every label line is already known to be valid."""
    root = dataset_root(directory)
    split_stats = []
    class_counts = [0] * config.num_classes
    for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
        images = _split_files(root / IMAGES_DIRNAME / split, suffixes=IMAGE_SUFFIXES)
        if not images:
            continue
        labels = _split_files(root / LABELS_DIRNAME / split, suffixes={".txt"})
        objects = 0
        for key in images.keys() & labels.keys():
            for line in labels[key].read_text(encoding="utf-8").splitlines():
                tokens = line.split()
                if tokens:
                    objects += 1
                    class_counts[int(tokens[0])] += 1
        split_stats.append({
            "split": split, "images": len(images),
            "labeled_images": len(images.keys() & labels.keys()), "objects": objects,
        })
    return {
        "split_stats": split_stats,
        "class_stats": [{"name": name, "objects": count} for name, count in zip(config.names, class_counts)],
        "has_labels": any(s["labeled_images"] for s in split_stats),
    }


# Hugging Face Hub rejects a push with more than this many files in any one
# directory — see shard_large_splits. Same limit (and the same hash-bucket
# scheme, common._image_bucket) the Camtrap DP export already works around.
HFH_MAX_FILES_PER_DIRECTORY = 10_000


def _direct_files(directory: Path) -> list[Path]:
    return [p for p in directory.iterdir() if p.is_file()] if directory.is_dir() else []


def shard_large_splits(output_dir: Path, *, max_files: int = HFH_MAX_FILES_PER_DIRECTORY) -> list[str]:
    """For a Hugging Face Hub export only: every split whose images/<split>
    or labels/<split> holds more than `max_files` files directly gets both
    spread over hash-named subfolders (images/train/3f/img.jpg,
    labels/train/3f/img.txt — the bucket is a hash of the file's stem, so an
    image and its label always land in the same one). Still valid YOLO:
    trainers look for images recursively under each split and find each
    label by swapping images/ for labels/ in its path. Undone by
    unshard_splits (see extract_core_files), so nothing downstream of the
    Hub export ever sees these subfolders.

    Returns:
        The splits that got sharded.
    """
    sharded = []
    for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
        split_dirs = [output_dir / IMAGES_DIRNAME / split, output_dir / LABELS_DIRNAME / split]
        files_by_dir = {d: _direct_files(d) for d in split_dirs}
        if all(len(files) <= max_files for files in files_by_dir.values()):
            continue
        for split_dir, files in files_by_dir.items():
            for file_path in files:
                bucket_dir = split_dir / common._image_bucket(file_path.stem)
                bucket_dir.mkdir(exist_ok=True)
                file_path.rename(bucket_dir / file_path.name)
        sharded.append(split)
    return sharded


def _is_shard_bucket(directory: Path) -> bool:
    """A subfolder shard_large_splits created: named like a bucket, and
    every file in it hashes to exactly that bucket — never a user's own
    subfolder in practice."""
    files = _direct_files(directory)
    return (
        len(directory.name) == common.IMAGE_SHARD_HEX_CHARS and bool(files)
        and all(common._image_bucket(f.stem) == directory.name for f in files)
        and not any(p.is_dir() for p in directory.iterdir())
    )


def unshard_splits(directory: Path) -> None:
    """Reverses shard_large_splits in place — e.g. on a copy extracted from a
    Hugging Face Hub build or download (see extract_core_files)."""
    for dirname in (IMAGES_DIRNAME, LABELS_DIRNAME):
        for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
            split_dir = directory / dirname / split
            if not split_dir.is_dir():
                continue
            for bucket_dir in [d for d in split_dir.iterdir() if d.is_dir() and _is_shard_bucket(d)]:
                for file_path in _direct_files(bucket_dir):
                    destination = split_dir / file_path.name
                    if not destination.exists():
                        file_path.rename(destination)
                if not any(bucket_dir.iterdir()):
                    bucket_dir.rmdir()


def sharded_splits(directory: Path) -> list[str]:
    return [
        split for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]
        if (directory / IMAGES_DIRNAME / split).is_dir()
        and any(d.is_dir() and _is_shard_bucket(d) for d in (directory / IMAGES_DIRNAME / split).iterdir())
    ]


def split_image_counts(directory: Path) -> dict[str, int]:
    images_dir = dataset_root(directory) / IMAGES_DIRNAME
    return {
        split: len(_split_files(images_dir / split, suffixes=IMAGE_SUFFIXES))
        for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]
        if (images_dir / split).is_dir()
    }


def _coords_to_pixel_bbox(coords: list[float], width: int, height: int) -> list[float]:
    """Converts one YoloLabelLine's normalized coords — either a bounding
    box (4 values: x_center, y_center, w, h) or a polygon (an even number
    >= 6 of x, y vertices) — into a single pixel-space [x, y, width, height]
    box (top-left corner), the shape Hugging Face's ImageFolder object-
    detection convention expects. A polygon's box is just its own bounding
    box (min/max over its vertices) — there's no tighter shape metadata.jsonl
    can represent."""
    if len(coords) == 4:
        cx, cy, w, h = coords
        box_w, box_h = w * width, h * height
        return [(cx * width) - box_w / 2, (cy * height) - box_h / 2, box_w, box_h]
    xs = [coords[i] * width for i in range(0, len(coords), 2)]
    ys = [coords[i] * height for i in range(1, len(coords), 2)]
    x_min, y_min = min(xs), min(ys)
    return [x_min, y_min, max(xs) - x_min, max(ys) - y_min]


def write_hf_metadata_jsonl(output_dir: Path) -> None:
    """Writes images/<split>/metadata.jsonl for every split — the format
    Hugging Face's ImageFolder loader recognizes for object-detection
    datasets (a "objects" column of {bbox, categories} per row, keyed by
    file_name — see https://huggingface.co/docs/datasets/image_dataset),
    so the Hub's Dataset Viewer can render each image with its bounding
    boxes instead of just the raw label .txt lines. Additive only: the
    images/<split>/*.jpg + labels/<split>/*.txt layout trainers already read
    directly is untouched, so this changes nothing for YOLO training itself.
    Must run after shard_large_splits (if that ran at all), so file_name
    already reflects any hash-bucket subfolder."""
    root = dataset_root(output_dir)
    for split in [*REQUIRED_SPLITS, *OPTIONAL_SPLITS]:
        images_split_dir = root / IMAGES_DIRNAME / split
        images = _split_files(images_split_dir, suffixes=IMAGE_SUFFIXES)
        if not images:
            continue
        labels = _split_files(root / LABELS_DIRNAME / split, suffixes={".txt"})
        lines = []
        for key in sorted(images, key=str):
            image_path = images[key]
            entry: dict[str, Any] = {"file_name": image_path.relative_to(images_split_dir).as_posix()}
            label_path = labels.get(key)
            if label_path is not None:
                try:
                    with Image.open(image_path) as img:
                        width, height = img.size
                except Exception:
                    # Unreadable/corrupt image — skip its bounding boxes
                    # rather than fail the whole export over one bad file;
                    # it still gets a file_name row, just without "objects".
                    logger.warning(f"Could not read {image_path} to compute its bounding boxes for metadata.jsonl.")
                    width = height = None
                if width is not None:
                    bboxes, categories = [], []
                    for line in label_path.read_text(encoding="utf-8").splitlines():
                        tokens = line.split()
                        if not tokens:
                            continue
                        categories.append(int(tokens[0]))
                        bboxes.append(_coords_to_pixel_bbox([float(t) for t in tokens[1:]], width, height))
                    if bboxes:
                        entry["objects"] = {"bbox": bboxes, "categories": categories}
            lines.append(json.dumps(entry))
        jsonl_path = images_split_dir / HF_METADATA_JSONL
        if jsonl_path.is_file():
            # The dataset's own — keep it rather than silently overwrite.
            jsonl_path.replace(images_split_dir / f"SOURCE_{HF_METADATA_JSONL}")
        jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class YoloAdapter:
    product_type = product.YOLO
    always_mirror = True  # see product.ProductAdapter.always_mirror

    def validate(self, input_dir: Path) -> None:
        for warning in check_dataset(input_dir):
            logger.warning(warning)

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
        try:
            meta = YoloMetadata.model_validate(data)
        except ValidationError:
            meta = YoloMetadata()
        return {
            "title": meta.title,
            "description": meta.description,
            "version": meta.version,
            "license": license_info,
            "authors": authors,
            "homepage": meta.homepage,
            "publisher": _resolve_publisher(data.get("publisher")),
            "copyright_holders": _resolve_copyright_holders(data.get("copyright_holders")),
        }

    def checkout_release(self, input_dir: Path, *, version: Optional[str]) -> Optional[str]:
        return None  # a YOLO dataset's raw source isn't a git checkout in this pipeline's sense

    def prepare(
        self, input_dir: Path, output_dir: Path, *, mirror: bool, image_timeout: int,
        media_dir: Optional[Path] = None, media_cache_dir: Optional[Path] = None,
    ) -> None:
        # image_timeout, media_dir and media_cache_dir are accepted for
        # interface parity with CamtrapDPAdapter but unused: the images are
        # already local files — alongside input_dir itself, or wherever its
        # working-copy pointer says (see dataset_root) — with nothing to
        # download. mirror is ignored too (see always_mirror): there's no
        # external host a Link-mode export could point YOLO images at, so
        # the images/ (and labels/, if present) tree is always copied.
        shutil.copy2(_data_yaml_path(input_dir), _data_yaml_path(output_dir))
        root = dataset_root(input_dir)
        _copy_splits(root, output_dir, IMAGES_DIRNAME)
        _copy_splits(root, output_dir, LABELS_DIRNAME)
        copy_extra_files(root, output_dir, own_metadata_json=root.resolve() == input_dir.resolve())
        self.validate(output_dir)

    def anonymize_coordinates(self, input_dir: Path, *, decimals: int) -> None:
        pass  # a YOLO dataset has no GPS coordinates of its own

    def randomize_media_ids(self, input_dir: Path, *, domain: str = "localhost") -> None:
        pass  # a YOLO dataset has no mediaID of its own

    def extract_core_files(self, output_dir: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        data_yaml_source = _data_yaml_path(output_dir)
        if data_yaml_source.is_file():
            shutil.copy2(data_yaml_source, _data_yaml_path(target_dir))
            _copy_splits(output_dir, target_dir, IMAGES_DIRNAME)
            _copy_splits(output_dir, target_dir, LABELS_DIRNAME)
            for entry in output_dir.iterdir():
                # additional_info/ travels on;
                # this repo's own generated files and zip don't.
                if _is_extra_entry(entry) and entry.name not in product.GENERATED_FILENAMES and entry.suffix != ".zip":
                    if entry.is_dir():
                        shutil.copytree(entry, target_dir / entry.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(entry, target_dir / entry.name)
            # A Hugging Face Hub build/download may be sharded (see
            # shard_large_splits) — hand everything downstream (the next
            # repo in the chain, the user's own output_dir) the original
            # layout instead.
            unshard_splits(target_dir)
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

    def bundle_local_zip(self, input_dir: Path, output_dir: Path, zip_path: Path, *, embed_images: bool) -> None:
        # embed_images is always true in practice here: the images/ tree IS
        # the dataset, there's no "loose alongside the zip" mode like
        # Camtrap DP's camtrapdp-local.zip.
        product.zip_directory(output_dir, zip_path, exclude_names=product.GENERATED_FILENAMES)

    def readme_context(self, output_dir: Path) -> dict:
        config = parse_data_yaml(output_dir)  # names already normalized to a list
        try:
            homepage = YoloMetadata.model_validate(_load_data_yaml(output_dir)).homepage
        except ValidationError:
            homepage = None
        stats = dataset_statistics(output_dir, config)
        total_images = sum(s["images"] for s in stats["split_stats"])
        return {
            "num_classes": config.num_classes, "class_names": config.names,
            **stats,
            "sharded_splits": sharded_splits(output_dir),
            # The dataset's own homepage, if data.yaml gives one — where the
            # README's "Contributing" section points (omitted otherwise).
            "contributing_url": homepage,
            # Extra text for the shared README "Funding" section (see
            # templates/common/_readme-funding.md.j2), from data.yaml's own
            # "funding" key — the wizard's metadata editor writes it there.
            "funding_extra": (_read_funding(output_dir) or "").strip(),
            # Hugging Face Hub Dataset Card discovery fields (see
            # README-yolo-body.md.j2's frontmatter) — size_category is
            # computed from what's actually on disk (common.hf_size_category),
            # never hand-maintained, so it can't go stale.
            "task_categories": ["object-detection"],
            "tags": ["wildlife", "camera-trap", "yolo"],
            "size_category": common.hf_size_category(total_images),
        }


class YoloEditableMetadata(BaseModel):
    """This tool's own metadata keys in data.yaml (not part of the YOLO
    spec) — what the web wizard's metadata editor reads and writes back
    (see read_editable_fields/update_editable_fields). An empty value
    removes the key from data.yaml."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    homepage: Optional[str] = None
    # Free text (Markdown) appended to the README's "Funding" section, after
    # the standard WildINTEL text — see readme_context's funding_extra.
    funding: Optional[str] = None
    license: Optional[YoloLicense] = None
    authors: list[YoloAuthor] = Field(default_factory=list)
    # Same meaning as metadata.json's own publisher/copyright_holders —
    # picked in the wizard from settings.toml's PRODUCT.organizations.
    publisher: Optional[YoloPublisher] = None
    copyright_holders: list[NonBlankText] = Field(default_factory=list)


def _read_funding(directory: Path) -> Optional[str]:
    try:
        return YoloMetadata.model_validate(_load_data_yaml(directory)).funding
    except (ValidationError, RuntimeError):
        return None


def read_editable_fields(directory: Path) -> dict:
    """Best-effort, same as extract_metadata: a missing or malformed key
    just comes back empty, for the user to fill in."""
    fields = YoloAdapter().extract_metadata(directory)
    # funding only feeds the README (see readme_context), so it never goes
    # through extract_metadata/metadata.json — read straight from data.yaml.
    return {**fields, "funding": _read_funding(directory)}


def update_editable_fields(directory: Path, fields: YoloEditableMetadata) -> None:
    """Rewrites only YoloEditableMetadata's own keys in `directory`'s
    data.yaml, leaving every YOLO key untouched (though YAML comments are
    lost — meant for a working copy, see create_working_copy)."""
    data = _load_data_yaml(directory)
    for key, value in fields.model_dump().items():
        if key in ("license", "publisher") and value:
            value = {k: v for k, v in value.items() if v}
        elif key == "authors":
            value = [{k: v for k, v in author.items() if v} for author in value]
        if value:
            data[key] = value
        else:
            data.pop(key, None)
    _data_yaml_path(directory).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )


product.register_adapter(YoloAdapter())
