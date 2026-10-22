"""Unit tests for services.yolo_adapter.YoloAdapter — proves the
ProductAdapter abstraction genuinely works for a product type that isn't
Camtrap DP."""
import json
from pathlib import Path

import pytest
import yaml

from wildintel_publisher.core.services import product
from wildintel_publisher.core.services.yolo_adapter import YoloAdapter, dataset_root


def _write_yolo_dataset(root: Path, *, data_yaml_extra: dict | None = None, with_test_split: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for split, count in [("train", 2), ("val", 1)] + ([("test", 1)] if with_test_split else []):
        split_dir = root / "images" / split
        split_dir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            (split_dir / f"img{i}.jpg").write_bytes(b"fake-image-bytes")

    data = {
        "train": "images/train", "val": "images/val", "test": "images/test",
        "nc": 2, "names": ["cat", "dog"],
        "title": "Test YOLO Dataset", "description": "A test object-detection dataset.",
        "version": "1.0", "license": "MIT",
        "authors": [{"name": "Jane Doe", "affiliation": "Test Org"}],
    }
    if data_yaml_extra:
        data.update(data_yaml_extra)
    (root / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


def test_validate_passes_for_a_well_formed_dataset(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    YoloAdapter().validate(root)  # must not raise


def test_validate_fails_when_data_yaml_missing(tmp_path):
    root = tmp_path / "yolo"
    root.mkdir()
    with pytest.raises(RuntimeError, match="data.yaml"):
        YoloAdapter().validate(root)


def test_validate_fails_when_a_required_split_is_empty(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    for f in (root / "images" / "val").iterdir():
        f.unlink()
    with pytest.raises(RuntimeError, match="images/val"):
        YoloAdapter().validate(root)


def test_validate_does_not_require_the_optional_test_split(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", with_test_split=False)
    YoloAdapter().validate(root)  # must not raise


def _write_label(root: Path, split: str, stem: str, content: str) -> Path:
    label_dir = root / "labels" / split
    label_dir.mkdir(parents=True, exist_ok=True)
    path = label_dir / f"{stem}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def _label_every_image(root: Path, content: str = "0 0.5 0.5 0.2 0.2\n") -> None:
    for image in (root / "images").rglob("*.jpg"):
        split = image.parent.name
        _write_label(root, split, image.stem, content)


def test_validate_rejects_nc_not_matching_names(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 3})
    with pytest.raises(RuntimeError, match="nc is 3 but names lists 2 classes"):
        YoloAdapter().validate(root)


def test_validate_rejects_a_names_mapping_with_gaps(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 2, "names": {0: "cat", 2: "dog"}})
    with pytest.raises(RuntimeError, match="consecutive class ids"):
        YoloAdapter().validate(root)


def test_validate_rejects_empty_names(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": None, "names": []})
    with pytest.raises(RuntimeError, match="names"):
        YoloAdapter().validate(root)


def test_validate_rejects_an_unsupported_split_layout(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"train": "train/images"})
    with pytest.raises(RuntimeError, match="images/train"):
        YoloAdapter().validate(root)


def test_validate_accepts_equivalent_split_path_spellings(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"train": "./images/train/", "val": "images/val"})
    YoloAdapter().validate(root)  # must not raise


def test_validate_ignores_non_image_files_when_counting_a_split(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    for f in (root / "images" / "val").iterdir():
        f.unlink()
    (root / "images" / "val" / "notes.txt").write_text("not an image", encoding="utf-8")
    with pytest.raises(RuntimeError, match="images/val"):
        YoloAdapter().validate(root)


def test_validate_finds_images_in_nested_subdirectories(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    nested = root / "images" / "val" / "site-a"
    for f in list((root / "images" / "val").iterdir()):
        f.unlink()
    nested.mkdir()
    (nested / "img9.jpg").write_bytes(b"fake-image-bytes")
    YoloAdapter().validate(root)  # must not raise


def test_validate_passes_with_well_formed_labels(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_every_image(root, "0 0.5 0.5 0.2 0.2\n1 0.1 0.1 0.05 0.05\n\n")
    _write_label(root, "train", "img1", "1 0.1 0.1 0.3 0.1 0.2 0.4\n")  # segmentation polygon
    YoloAdapter().validate(root)  # must not raise


def test_validate_rejects_a_class_id_out_of_range(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_every_image(root)
    _write_label(root, "train", "img0", "0 0.5 0.5 0.2 0.2\n2 0.5 0.5 0.2 0.2\n")
    with pytest.raises(RuntimeError, match=r"labels/train/img0.txt:2 .*class id 2 is out of range"):
        YoloAdapter().validate(root)


def test_validate_rejects_coordinates_outside_zero_one(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_every_image(root)
    _write_label(root, "val", "img0", "0 1.5 0.5 0.2 0.2\n")
    with pytest.raises(RuntimeError, match=r"labels/val/img0.txt:1 \(coords.0\)"):
        YoloAdapter().validate(root)


def test_validate_rejects_a_line_with_the_wrong_number_of_values(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_every_image(root)
    _write_label(root, "val", "img0", "0 0.5 0.5 0.2\n")
    with pytest.raises(RuntimeError, match="expected 4 values"):
        YoloAdapter().validate(root)


def test_validate_rejects_a_non_numeric_value(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_every_image(root)
    _write_label(root, "val", "img0", "cat 0.5 0.5 0.2 0.2\n")
    with pytest.raises(RuntimeError, match=r"labels/val/img0.txt:1 \(class_id\)"):
        YoloAdapter().validate(root)


def test_validate_caps_the_number_of_reported_label_problems(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_every_image(root)
    _write_label(root, "train", "img0", "9 0.5 0.5 0.2 0.2\n" * 25)
    with pytest.raises(RuntimeError, match=r"25 invalid label line\(s\)[\s\S]*and 15 more"):
        YoloAdapter().validate(root)


def test_validate_only_warns_about_unlabeled_images_and_orphan_labels(tmp_path, caplog):
    root = _write_yolo_dataset(tmp_path / "yolo")
    _write_label(root, "train", "img0", "0 0.5 0.5 0.2 0.2\n")
    _write_label(root, "train", "ghost", "0 0.5 0.5 0.2 0.2\n")
    with caplog.at_level("WARNING"):
        YoloAdapter().validate(root)  # must not raise
    assert "3 image(s)" in caplog.text  # img1 (train), img0 (val), img0 (test)
    assert "1 label file(s)" in caplog.text


def test_validate_only_warns_when_the_declared_test_split_has_no_images(tmp_path, caplog):
    root = _write_yolo_dataset(tmp_path / "yolo", with_test_split=False)
    with caplog.at_level("WARNING"):
        YoloAdapter().validate(root)  # must not raise
    assert "declares a 'test' split" in caplog.text


def test_extract_metadata_stringifies_a_numeric_version(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"version": 1.0})
    assert YoloAdapter().extract_metadata(root)["version"] == "1.0"


def test_extract_metadata_skips_malformed_authors(tmp_path):
    root = _write_yolo_dataset(
        tmp_path / "yolo",
        data_yaml_extra={"authors": ["just a string", {"affiliation": "No Name"}, {"name": "Jane Doe"}]},
    )
    assert YoloAdapter().extract_metadata(root)["authors"] == [{"name": "Jane Doe", "affiliation": ""}]


def test_extract_metadata_reads_the_generic_fields(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")
    metadata = YoloAdapter().extract_metadata(root)

    assert metadata["title"] == "Test YOLO Dataset"
    assert metadata["description"] == "A test object-detection dataset."
    assert metadata["version"] == "1.0"
    assert metadata["license"] == {"id": "MIT", "name": "MIT", "url": ""}
    assert metadata["authors"] == [{"name": "Jane Doe", "affiliation": "Test Org"}]
    assert metadata["homepage"] is None


def test_extract_metadata_returns_none_when_title_is_missing(tmp_path):
    # Best-effort: the adapter never raises for a missing field — it's up
    # to product.missing_required_fields/the UI to notice and ask the user.
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"title": None})
    metadata = YoloAdapter().extract_metadata(root)
    assert metadata["title"] is None


def test_extract_metadata_returns_none_license_when_not_resolvable(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"license": None})
    metadata = YoloAdapter().extract_metadata(root)
    assert metadata["license"] is None


def test_extract_metadata_returns_empty_authors_when_none_named(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"authors": []})
    metadata = YoloAdapter().extract_metadata(root)
    assert metadata["authors"] == []


def test_extract_metadata_accepts_a_license_mapping(tmp_path):
    root = _write_yolo_dataset(
        tmp_path / "yolo",
        data_yaml_extra={"license": {"id": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}},
    )
    metadata = YoloAdapter().extract_metadata(root)
    assert metadata["license"]["id"] == "CC-BY-4.0"
    assert metadata["license"]["url"] == "https://creativecommons.org/licenses/by/4.0/"


def test_prepare_mirror_mode_copies_data_yaml_and_all_splits(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "input")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "data.yaml").is_file()
    assert (output_dir / "images" / "train" / "img0.jpg").is_file()
    assert (output_dir / "images" / "val" / "img0.jpg").is_file()
    assert (output_dir / "images" / "test" / "img0.jpg").is_file()


def test_prepare_link_mode_is_the_same_as_mirror(tmp_path):
    """No external host YOLO images could point at instead — see
    YoloAdapter.always_mirror."""
    input_dir = _write_yolo_dataset(tmp_path / "input")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=False, image_timeout=60)

    assert (output_dir / "data.yaml").is_file()
    assert (output_dir / "images" / "train" / "img0.jpg").is_file()
    assert YoloAdapter.always_mirror is True


def test_link_media_to_hfh_is_a_no_op(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo")
    adapter = YoloAdapter()
    assert adapter.link_media_to_hfh(output_dir, "alice/dataset") == 0


def _zip_names(directory) -> dict[str, set[str]]:
    import zipfile

    return {z.name: set(zipfile.ZipFile(z).namelist()) for z in sorted(directory.glob("*.zip"))}


def test_bundle_local_zip_packs_the_dataset_in_a_single_zip_but_not_generated_files(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo")
    (output_dir / "README.md").write_text("# hi", encoding="utf-8")
    (output_dir / "metadata.json").write_text("{}", encoding="utf-8")

    YoloAdapter().bundle_local_zip(output_dir, output_dir, output_dir / "yolo.zip", embed_images=True)

    zips = _zip_names(output_dir)
    assert list(zips) == ["yolo.zip"]
    assert {"data.yaml", "images/train/img0.jpg"} <= zips["yolo.zip"]
    assert "README.md" not in zips["yolo.zip"] and "metadata.json" not in zips["yolo.zip"]


def test_extract_core_files_unpacks_every_zip_when_the_loose_files_are_gone(tmp_path):
    import shutil

    output_dir = _write_yolo_dataset(tmp_path / "yolo")
    expected = {p.relative_to(output_dir).as_posix() for p in output_dir.rglob("*") if p.is_file()}
    YoloAdapter().bundle_local_zip(output_dir, output_dir, output_dir / "yolo.zip", embed_images=True)
    for entry in list(output_dir.iterdir()):
        if entry.suffix != ".zip":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()

    YoloAdapter().extract_core_files(output_dir, tmp_path / "chain")

    assert {p.relative_to(tmp_path / "chain").as_posix() for p in (tmp_path / "chain").rglob("*") if p.is_file()} == expected


def test_readme_context_reads_class_count_and_names_from_data_yaml(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 2, "names": ["cat", "dog"]})

    context = YoloAdapter().readme_context(output_dir)

    assert (context["num_classes"], context["class_names"]) == (2, ["cat", "dog"])


def test_readme_context_accepts_a_names_mapping(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 2, "names": {0: "cat", 1: "dog"}})

    context = YoloAdapter().readme_context(output_dir)

    assert (context["num_classes"], context["class_names"]) == (2, ["cat", "dog"])


def test_checkout_release_noops(tmp_path):
    # A YOLO dataset's raw source isn't a git checkout — never raises,
    # never touches the directory.
    result = YoloAdapter().checkout_release(tmp_path, version="1.0")
    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_generate_metadata_json_writes_product_type_and_history(tmp_path):
    """End-to-end through services.product, not just the adapter directly —
    proves YoloAdapter is properly registered and reachable via
    product.get_adapter/generate_metadata_json."""
    root = _write_yolo_dataset(tmp_path / "yolo")

    result = product.generate_metadata_json(product.YOLO, root)

    assert result["product_type"] == "yolo"
    assert result["title"] == "Test YOLO Dataset"
    assert result["publish_history"] == []
    # Reporting-only — never part of metadata.json's own schema (see
    # ProductAdapter.checkout_release) — a YOLO dataset has no git tag to
    # check out in the first place.
    assert result["checked_out_tag"] is None

    on_disk = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk == {k: v for k, v in result.items() if k != "checked_out_tag"}


# ── web-wizard working copy (data.yaml + pointer to the original dataset) ──

def test_create_working_copy_copies_only_data_yaml_and_points_back_to_the_source(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import create_working_copy, dataset_root

    source = _write_yolo_dataset(tmp_path / "source")
    working = create_working_copy(source, tmp_path / "working")

    assert sorted(p.name for p in working.iterdir()) == ["data.yaml", "yolo-source.json"]
    assert dataset_root(working) == source.resolve()
    YoloAdapter().validate(working)  # images/ found through the pointer


def test_create_working_copy_fails_without_data_yaml(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import create_working_copy

    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(RuntimeError, match="data.yaml"):
        create_working_copy(source, tmp_path / "working")


def test_dataset_root_rejects_a_pointer_to_a_missing_directory(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import dataset_root

    working = tmp_path / "working"
    working.mkdir()
    (working / "yolo-source.json").write_text(json.dumps({"root": str(tmp_path / "gone")}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="yolo-source.json is invalid"):
        dataset_root(working)


def test_prepare_from_a_working_copy_takes_images_from_the_source_and_never_ships_the_pointer(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import create_working_copy

    source = _write_yolo_dataset(tmp_path / "source")
    _write_label(source, "train", "img0", "0 0.5 0.5 0.2 0.2\n")
    working = create_working_copy(source, tmp_path / "working")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    YoloAdapter().prepare(working, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "images" / "train" / "img0.jpg").is_file()
    assert (output_dir / "labels" / "train" / "img0.txt").is_file()
    assert not (output_dir / "yolo-source.json").exists()


def test_check_dataset_returns_its_warnings(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import check_dataset

    root = _write_yolo_dataset(tmp_path / "yolo", with_test_split=False)
    warnings = check_dataset(root)
    assert any("declares a 'test' split" in w for w in warnings)


def test_update_editable_fields_rewrites_only_the_metadata_keys(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import (
        YoloEditableMetadata, read_editable_fields, update_editable_fields,
    )

    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"homepage": "https://old.example"})
    update_editable_fields(root, YoloEditableMetadata(
        title="  New title  ", description="New description", version="2.0", homepage="",
        license={"id": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0", "url": ""},
        authors=[{"name": "Ada Lovelace", "affiliation": "Analytical Engines"}, {"name": "Grace Hopper"}],
    ))

    data = yaml.safe_load((root / "data.yaml").read_text(encoding="utf-8"))
    assert data["title"] == "New title"
    assert "homepage" not in data  # emptied -> removed
    assert data["license"] == {"id": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0"}
    assert data["authors"] == [{"name": "Ada Lovelace", "affiliation": "Analytical Engines"}, {"name": "Grace Hopper"}]
    # YOLO's own keys are untouched
    assert data["nc"] == 2 and data["names"] == ["cat", "dog"] and data["train"] == "images/train"

    fields = read_editable_fields(root)
    assert fields["version"] == "2.0"
    assert fields["license"]["id"] == "CC-BY-4.0"
    assert fields["authors"][1] == {"name": "Grace Hopper", "affiliation": ""}


def test_editable_metadata_rejects_an_author_without_a_name():
    from pydantic import ValidationError

    from wildintel_publisher.core.services.yolo_adapter import YoloEditableMetadata

    with pytest.raises(ValidationError):
        YoloEditableMetadata(authors=[{"name": "  ", "affiliation": "X"}])


def test_extract_metadata_reads_publisher_and_copyright_holders(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={
        "publisher": {"name": "University of Huelva", "website": "https://www.uhu.es/"},
        "copyright_holders": ["Spanish National Research Council", "", 42],
    })
    metadata = YoloAdapter().extract_metadata(root)
    assert metadata["publisher"] == {"name": "University of Huelva", "website": "https://www.uhu.es/"}
    assert metadata["copyright_holders"] == ["Spanish National Research Council"]


def test_extract_metadata_ignores_a_publisher_without_a_name(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"publisher": {"website": "https://x.example"}})
    assert YoloAdapter().extract_metadata(root)["publisher"] is None


def test_update_editable_fields_writes_and_clears_publisher_and_copyright_holders(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import YoloEditableMetadata, update_editable_fields

    root = _write_yolo_dataset(tmp_path / "yolo")
    update_editable_fields(root, YoloEditableMetadata(
        publisher={"name": "University of Huelva", "website": "https://www.uhu.es/", "email": ""},
        copyright_holders=["Spanish National Research Council"],
    ))
    data = yaml.safe_load((root / "data.yaml").read_text(encoding="utf-8"))
    assert data["publisher"] == {"name": "University of Huelva", "website": "https://www.uhu.es/"}
    assert data["copyright_holders"] == ["Spanish National Research Council"]

    update_editable_fields(root, YoloEditableMetadata())
    data = yaml.safe_load((root / "data.yaml").read_text(encoding="utf-8"))
    assert "publisher" not in data and "copyright_holders" not in data


def test_readme_context_counts_images_labels_and_objects_per_split_and_class(tmp_path):
    root = _write_yolo_dataset(tmp_path / "yolo")  # train: 2 images, val: 1, test: 1
    _write_label(root, "train", "img0", "0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n")
    _write_label(root, "train", "img1", "1 0.5 0.5 0.2 0.2\n")
    _write_label(root, "val", "img0", "0 0.4 0.4 0.2 0.2\n\n")

    context = YoloAdapter().readme_context(root)

    assert context["split_stats"] == [
        {"split": "train", "images": 2, "labeled_images": 2, "objects": 3},
        {"split": "val", "images": 1, "labeled_images": 1, "objects": 1},
        {"split": "test", "images": 1, "labeled_images": 0, "objects": 0},
    ]
    assert context["class_stats"] == [{"name": "cat", "objects": 2}, {"name": "dog", "objects": 2}]
    assert context["has_labels"] is True


def test_readme_context_contributing_url_is_data_yamls_homepage(tmp_path):
    with_homepage = _write_yolo_dataset(tmp_path / "a", data_yaml_extra={"homepage": "https://example.org/ds"})
    without = _write_yolo_dataset(tmp_path / "b")

    assert YoloAdapter().readme_context(with_homepage)["contributing_url"] == "https://example.org/ds"
    assert YoloAdapter().readme_context(without)["contributing_url"] is None
    assert YoloAdapter().readme_context(without)["has_labels"] is False


# ── Hugging Face Hub's per-folder file limit ──

def _big_split(root: Path, count: int) -> None:
    train = root / "images" / "train"
    labels = root / "labels" / "train"
    labels.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (train / f"big{i}.jpg").write_bytes(b"x")
        (labels / f"big{i}.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")


def test_shard_large_splits_only_touches_splits_over_the_limit(tmp_path):
    from wildintel_publisher.core.services.common import _image_bucket
    from wildintel_publisher.core.services.yolo_adapter import shard_large_splits

    root = _write_yolo_dataset(tmp_path / "yolo")
    _big_split(root, 20)  # train now holds 22 images, val just 1

    assert shard_large_splits(root, max_files=10) == ["train"]

    assert not [p for p in (root / "images" / "train").iterdir() if p.is_file()]
    bucket = _image_bucket("big7")
    assert (root / "images" / "train" / bucket / "big7.jpg").is_file()
    assert (root / "labels" / "train" / bucket / "big7.txt").is_file()  # same bucket as its image
    assert (root / "images" / "val" / "img0.jpg").is_file()  # untouched
    YoloAdapter().validate(root)  # still a valid YOLO dataset


def test_unshard_splits_restores_the_original_layout_but_keeps_the_users_own_subfolders(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import shard_large_splits, unshard_splits

    root = _write_yolo_dataset(tmp_path / "yolo")
    _big_split(root, 20)
    own = root / "images" / "val" / "ab"  # a user's own two-letter subfolder
    own.mkdir()
    (own / "mine.jpg").write_bytes(b"x")
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())

    shard_large_splits(root, max_files=10)
    unshard_splits(root)

    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert after == before


def test_extract_core_files_hands_downstream_the_unsharded_layout(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import shard_large_splits

    build = _write_yolo_dataset(tmp_path / "hfh-build")
    _big_split(build, 20)
    shard_large_splits(build, max_files=10)

    YoloAdapter().extract_core_files(build, tmp_path / "chain")

    assert (tmp_path / "chain" / "images" / "train" / "big7.jpg").is_file()
    assert (tmp_path / "chain" / "labels" / "train" / "big7.txt").is_file()


def test_readme_context_reports_sharded_splits_and_still_counts_everything(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import shard_large_splits

    root = _write_yolo_dataset(tmp_path / "yolo")
    _big_split(root, 20)
    shard_large_splits(root, max_files=10)

    context = YoloAdapter().readme_context(root)

    assert context["sharded_splits"] == ["train"]
    train = next(s for s in context["split_stats"] if s["split"] == "train")
    assert train == {"split": "train", "images": 22, "labeled_images": 20, "objects": 20}


def _add_extras(root: Path) -> None:
    (root / "additional_info" / "lists").mkdir(parents=True)
    (root / "additional_info" / "lists" / "README.md").write_text("nested readme", encoding="utf-8")
    (root / "paper.docx").write_bytes(b"docx")
    (root / ".~lock.paper.docx#").write_text("lock", encoding="utf-8")
    (root / "README.md").write_text("the authors' own readme", encoding="utf-8")


def test_prepare_gathers_loose_extras_under_additional_info(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo")
    _add_extras(input_dir)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    extra = output_dir / "additional_info"
    assert (extra / "paper.docx").read_bytes() == b"docx"
    assert (extra / "README.md").read_text(encoding="utf-8") == "the authors' own readme"
    # _add_extras gives the dataset its own additional_info/ too, nested one level down.
    assert (extra / "additional_info" / "lists" / "README.md").read_text(encoding="utf-8") == "nested readme"
    assert not (output_dir / "README.md").exists()  # left free for the generated one
    assert not (output_dir / "paper.docx").exists()
    assert not list(output_dir.rglob(".~lock.*"))


def test_prepare_leaves_an_existing_additional_info_as_it_is(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo")
    (input_dir / "additional_info" / "lists").mkdir(parents=True)
    (input_dir / "additional_info" / "lists" / "a.csv").write_text("a", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "additional_info" / "lists" / "a.csv").read_text(encoding="utf-8") == "a"
    assert sorted(p.name for p in output_dir.iterdir()) == ["additional_info", "data.yaml", "images"]


def test_prepare_nests_an_existing_additional_info_when_there_are_loose_extras(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo")
    (input_dir / "additional_info").mkdir()
    (input_dir / "additional_info" / "a.csv").write_text("a", encoding="utf-8")
    (input_dir / "paper.docx").write_bytes(b"docx")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert (output_dir / "additional_info" / "paper.docx").is_file()
    assert (output_dir / "additional_info" / "additional_info" / "a.csv").read_text(encoding="utf-8") == "a"
    assert not (output_dir / "additional_info" / "a.csv").exists()


def test_prepare_ignores_an_empty_additional_info_when_there_are_loose_extras(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo")
    (input_dir / "additional_info").mkdir()
    (input_dir / "paper.docx").write_bytes(b"docx")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=True, image_timeout=60)

    assert sorted(p.name for p in (output_dir / "additional_info").iterdir()) == ["paper.docx"]


def test_check_dataset_warns_about_what_gets_moved_or_replaced(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import check_dataset

    root = _write_yolo_dataset(tmp_path / "yolo")
    _add_extras(root)
    (root / "images" / "train" / "metadata.jsonl").write_text("{}", encoding="utf-8")

    warnings = "\n".join(check_dataset(root))

    assert "README.md" in warnings and "paper.docx" in warnings and "inside additional_info/" in warnings
    assert "images/train/metadata.jsonl already exists" in warnings


def test_extract_core_files_carries_extras_but_not_generated_files(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "out")
    (output_dir / "paper.docx").write_bytes(b"docx")
    (output_dir / "additional_info").mkdir()
    (output_dir / "additional_info" / "README.md").write_text("orig", encoding="utf-8")
    (output_dir / "README.md").write_text("generated", encoding="utf-8")

    YoloAdapter().extract_core_files(output_dir, tmp_path / "chain")

    assert (tmp_path / "chain" / "paper.docx").is_file()
    assert (tmp_path / "chain" / "additional_info" / "README.md").is_file()
    assert not (tmp_path / "chain" / "README.md").exists()


def test_zip_only_leaves_out_top_level_generated_files(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "out")
    (output_dir / "README.md").write_text("generated", encoding="utf-8")
    (output_dir / "additional_info").mkdir()
    (output_dir / "additional_info" / "README.md").write_text("theirs", encoding="utf-8")

    YoloAdapter().bundle_local_zip(output_dir, output_dir, output_dir / "yolo.zip", embed_images=True)

    names = _zip_names(output_dir)["yolo.zip"]
    assert "additional_info/README.md" in names and "README.md" not in names


def test_the_readme_context_lists_the_zip_that_will_be_built(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "out")

    listed = [part["name"] for part in YoloAdapter().readme_context(output_dir)["zip_parts"]]

    YoloAdapter().bundle_local_zip(output_dir, output_dir, output_dir / "yolo.zip", embed_images=True)
    assert listed == [p.name for p in output_dir.glob("*.zip")] == ["yolo.zip"]


def test_funding_round_trips_through_the_editor_and_reaches_the_readme_context(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import (
        YoloEditableMetadata, read_editable_fields, update_editable_fields,
    )

    root = _write_yolo_dataset(tmp_path / "yolo")
    assert read_editable_fields(root)["funding"] is None
    assert YoloAdapter().readme_context(root)["funding_extra"] == ""

    update_editable_fields(root, YoloEditableMetadata(funding="Also funded by **Foo**.", authors=[{"name": "Jane"}], license={"id": "MIT"}))

    assert read_editable_fields(root)["funding"] == "Also funded by **Foo**."
    assert YoloAdapter().readme_context(root)["funding_extra"] == "Also funded by **Foo**."
    # never leaks into metadata.json's own schema
    assert "funding" not in YoloAdapter().extract_metadata(root)


def test_funding_extra_is_appended_to_the_shared_funding_section():
    from wildintel_publisher.core.services import common

    render = lambda **kw: common._jinja_env.from_string('{% include "common/_readme-funding.md.j2" %}').render(**kw)

    assert render(funding_extra="Also funded by **Foo**.").rstrip().endswith("(Germany).\n\nAlso funded by **Foo**.")
    assert render().rstrip().endswith("(Germany).")


def test_acknowledgements_round_trips_through_the_editor_and_reaches_the_readme_context(tmp_path):
    from wildintel_publisher.core.services.yolo_adapter import (
        YoloEditableMetadata, read_editable_fields, update_editable_fields,
    )

    root = _write_yolo_dataset(tmp_path / "yolo")
    assert read_editable_fields(root)["acknowledgements"] is None
    assert YoloAdapter().readme_context(root)["acknowledgements_extra"] == ""

    update_editable_fields(root, YoloEditableMetadata(acknowledgements="Thanks to **Foo**.", authors=[{"name": "Jane"}], license={"id": "MIT"}))

    assert read_editable_fields(root)["acknowledgements"] == "Thanks to **Foo**."
    assert YoloAdapter().readme_context(root)["acknowledgements_extra"] == "Thanks to **Foo**."
    assert "acknowledgements" not in YoloAdapter().extract_metadata(root)


def test_acknowledgements_extra_is_appended_to_the_fixed_acknowledgements_section():
    from wildintel_publisher.core.services import common

    render = lambda **kw: common._jinja_env.from_string('{% include "common/_readme-acknowledgements.md.j2" %}').render(**kw)

    assert "## Acknowledgements" in render()
    assert render(acknowledgements_extra="Thanks to **Foo**.").rstrip().endswith("\n\nThanks to **Foo**.")
    assert "Thanks to **Foo**." not in render()


def test_structure_checks_pass_one_by_one_for_a_well_formed_dataset(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    checks = yolo_adapter.structure_checks(_write_yolo_dataset(tmp_path / "yolo"))

    assert [c["check"] for c in checks] == ["data_yaml", "config", "classes", "images", "labels"]
    assert all(c["ok"] for c in checks)
    assert "nc is 2 and 2 classes" in checks[2]["message"]
    assert "train: 2" in checks[3]["message"] and "val: 1" in checks[3]["message"]
    assert "no labels/ folder" in checks[4]["message"].lower()


def test_structure_checks_say_what_is_wrong_and_what_could_not_be_checked(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    missing = yolo_adapter.structure_checks(tmp_path / "nothing")
    assert [c["ok"] for c in missing] == [False] * 5
    assert "data.yaml" in missing[0]["message"] and missing[1]["message"].startswith("Not checked")

    root = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"train": "somewhere/else"})
    bad = yolo_adapter.structure_checks(root)
    assert [c["ok"] for c in bad] == [True, False, False, False, False]
    assert "images/train" in bad[1]["message"]

    root = _write_yolo_dataset(tmp_path / "noval")
    for image in (root / "images" / "val").iterdir():
        image.unlink()
    assert [c["ok"] for c in yolo_adapter.structure_checks(root)] == [True, True, True, False, True]


def test_structure_checks_flag_a_malformed_label_file(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    (root / "labels" / "train").mkdir(parents=True)
    (root / "labels" / "train" / "img0.txt").write_text("0 0.5 0.5 1.5 0.1\n", encoding="utf-8")

    labels = yolo_adapter.structure_checks(root)[4]
    assert not labels["ok"] and "img0.txt:1" in labels["message"]


def test_the_images_without_a_label_file_are_listed(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    for split, names in (("train", ["img0"]), ("val", ["img0"]), ("test", ["img0"])):
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for name in names:
            (root / "labels" / split / f"{name}.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")

    [result] = yolo_adapter.run_deep_checks(root, ["image_labels"])

    assert not result["ok"] and result["total"] == 1 and result["failures"] == ["images/train/img1.jpg"]
    assert "1 of 4 images" in result["message"]
    with pytest.raises(RuntimeError, match="Unknown"):
        yolo_adapter.run_deep_checks(root, ["nope"])


def test_every_image_labelled_passes_the_deep_check(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    for split in ("train", "val", "test"):
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for image in (root / "images" / split).iterdir():
            (root / "labels" / split / f"{image.stem}.txt").write_text("", encoding="utf-8")

    [result] = yolo_adapter.run_deep_checks(root, ["image_labels"])
    assert result["ok"] and result["failures"] == [] and result["message"] == "All 4 images have a label file."


def test_nc_that_disagrees_with_the_names_is_its_own_failed_check_and_does_not_hide_the_others(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    checks = yolo_adapter.structure_checks(_write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 5}))

    assert [c["ok"] for c in checks] == [True, True, False, True, True]
    assert checks[2]["message"] == "nc is 5 but names lists 2 classes."


def _label_everything(root, content="0 0.5 0.5 0.1 0.1\n"):
    for split in ("train", "val", "test"):
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for image in (root / "images" / split).iterdir():
            (root / "labels" / split / f"{image.stem}.txt").write_text(content, encoding="utf-8")


def test_a_declared_class_that_never_appears_in_the_labels_is_listed(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_everything(root)  # only class 0 (cat) is used

    [used] = yolo_adapter.run_deep_checks(root, ["class_use"])

    assert not used["ok"] and used["failures"] == ["dog (class 1)"]
    assert used["message"] == "1 of 2 declared classes never appear in the 4 label files."


def test_a_label_using_an_undeclared_class_is_listed_with_its_line(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_everything(root)
    (root / "labels" / "val" / "img0.txt").write_text("0 0.5 0.5 0.1 0.1\n7 0.5 0.5 0.1 0.1\n", encoding="utf-8")

    [ids] = yolo_adapter.run_deep_checks(root, ["class_ids"])

    assert not ids["ok"] and ids["failures"] == ["labels/val/img0.txt:2 (class 7)"]
    clean = _write_yolo_dataset(tmp_path / "clean")
    _label_everything(clean)
    [ok] = yolo_adapter.run_deep_checks(clean, ["class_ids"])
    assert ok["ok"]


def test_a_label_file_without_an_image_is_an_orphan(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_everything(root)
    (root / "labels" / "train" / "ghost.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    (root / "labels" / "val" / "img0.txt").unlink()  # an image without a label is another check

    [orphans] = yolo_adapter.run_deep_checks(root, ["orphan_labels"])

    assert not orphans["ok"] and orphans["failures"] == ["labels/train/ghost.txt"]
    assert orphans["message"] == "1 of 4 label files have no image."
    assert orphans["failure_message"] == "No image with this name in the same split."


def test_the_label_name_must_match_the_image_in_the_same_split(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_everything(root)
    (root / "labels" / "val" / "img0.txt").rename(root / "labels" / "test" / "elsewhere.txt")

    results = {r["check"]: r for r in yolo_adapter.run_deep_checks(root, ["image_labels", "orphan_labels"])}

    assert results["orphan_labels"]["failures"] == ["labels/test/elsewhere.txt"]
    assert results["image_labels"]["failures"] == ["images/val/img0.jpg"]


def test_a_dataset_whose_labels_all_have_an_image_passes_the_orphan_check(tmp_path):
    from wildintel_publisher.core.services import yolo_adapter

    root = _write_yolo_dataset(tmp_path / "yolo")
    _label_everything(root)

    [result] = yolo_adapter.run_deep_checks(root, ["orphan_labels"])

    assert result["ok"] and result["message"] == "All 4 label files have an image."


def test_prepare_hardlinks_images_and_labels_instead_of_copying_them(tmp_path):
    source = _write_yolo_dataset(tmp_path / "yolo")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    YoloAdapter().prepare(source, output_dir, mirror=True, image_timeout=1)

    assert (output_dir / "images" / "train" / "img0.jpg").samefile(source / "images" / "train" / "img0.jpg")
    assert not (output_dir / "data.yaml").samefile(source / "data.yaml")  # data.yaml is edited later: a real copy


def test_prepare_copies_the_images_when_they_cannot_be_hardlinked(tmp_path, monkeypatch):
    import os

    def no_link(*args, **kwargs):
        raise OSError("Invalid cross-device link")

    source = _write_yolo_dataset(tmp_path / "yolo")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setattr(os, "link", no_link)

    YoloAdapter().prepare(source, output_dir, mirror=True, image_timeout=1)

    copied = output_dir / "images" / "train" / "img0.jpg"
    assert copied.read_bytes() == (source / "images" / "train" / "img0.jpg").read_bytes()
    assert not copied.samefile(source / "images" / "train" / "img0.jpg")


def test_bundling_a_hardlinked_build_leaves_the_original_dataset_untouched(tmp_path):
    source = _write_yolo_dataset(tmp_path / "yolo")
    before = sorted(p.relative_to(source).as_posix() for p in source.rglob("*"))
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    adapter = YoloAdapter()

    adapter.prepare(source, output_dir, mirror=True, image_timeout=1)
    adapter.bundle_local_zip(source, output_dir, output_dir / "yolo.zip", embed_images=True)
    import shutil
    for entry in list(output_dir.iterdir()):
        if entry.name != "yolo.zip":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()

    assert sorted(p.relative_to(source).as_posix() for p in source.rglob("*")) == before
    assert (source / "images" / "train" / "img0.jpg").is_file()



def test_prepare_in_place_copies_no_media_and_points_at_the_dataset(tmp_path):
    source = _write_yolo_dataset(tmp_path / "yolo")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    YoloAdapter().prepare(source, output_dir, mirror=True, image_timeout=1, media_in_place=True)

    assert not (output_dir / "images").exists() and not (output_dir / "labels").exists()
    assert (output_dir / "data.yaml").is_file()
    assert dataset_root(output_dir) == source.resolve()


def test_an_in_place_build_is_zipped_straight_from_the_dataset(tmp_path):
    source = _write_yolo_dataset(tmp_path / "yolo")
    before = sorted(p.relative_to(source).as_posix() for p in source.rglob("*"))
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    adapter = YoloAdapter()

    adapter.prepare(source, output_dir, mirror=True, image_timeout=1, media_in_place=True)
    adapter.bundle_local_zip(source, output_dir, output_dir / "yolo.zip", embed_images=True)

    names = _zip_names(output_dir)["yolo.zip"]
    assert {"data.yaml", "images/train/img0.jpg"} <= names
    assert "yolo-source.json" not in names
    assert sorted(p.relative_to(source).as_posix() for p in source.rglob("*")) == before


def test_extract_core_files_of_an_in_place_build_hands_on_just_the_small_files(tmp_path):
    import shutil

    source = _write_yolo_dataset(tmp_path / "yolo")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    adapter = YoloAdapter()
    adapter.prepare(source, output_dir, mirror=True, image_timeout=1, media_in_place=True)
    adapter.bundle_local_zip(source, output_dir, output_dir / "yolo.zip", embed_images=True)
    for entry in list(output_dir.iterdir()):
        if entry.name not in ("yolo.zip", "yolo-source.json"):
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()

    adapter.extract_core_files(output_dir, tmp_path / "next")

    assert not (tmp_path / "next" / "images").exists()
    assert (tmp_path / "next" / "data.yaml").is_file()
    assert dataset_root(tmp_path / "next") == source.resolve()
