"""Unit tests for services.yolo_adapter.YoloAdapter — proves the
ProductAdapter abstraction genuinely works for a product type that isn't
Camtrap DP."""
import json
from pathlib import Path

import pytest
import yaml

from wildintel_publisher.services import product
from wildintel_publisher.services.yolo_adapter import YoloAdapter


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


def test_prepare_link_mode_copies_only_data_yaml(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "input")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    YoloAdapter().prepare(input_dir, output_dir, mirror=False, image_timeout=60)

    assert (output_dir / "data.yaml").is_file()
    assert not (output_dir / "images").exists()


def test_link_media_to_hfh_is_a_no_op(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo")
    adapter = YoloAdapter()
    assert adapter.link_media_to_hfh(output_dir, "alice/dataset") == 0


def test_bundle_local_zip_packs_data_yaml_and_images_but_not_generated_files(tmp_path):
    import zipfile

    output_dir = _write_yolo_dataset(tmp_path / "yolo")
    (output_dir / "README.md").write_text("# hi", encoding="utf-8")
    (output_dir / "metadata.json").write_text("{}", encoding="utf-8")
    zip_path = output_dir / "yolo-local.zip"

    YoloAdapter().bundle_local_zip(output_dir, zip_path, embed_images=True)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "data.yaml" in names
    assert "images/train/img0.jpg" in names
    assert "README.md" not in names
    assert "metadata.json" not in names


def test_readme_context_reads_class_count_and_names_from_data_yaml(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 2, "names": ["cat", "dog"]})

    context = YoloAdapter().readme_context(output_dir)

    assert context == {"num_classes": 2, "class_names": ["cat", "dog"]}


def test_readme_context_accepts_a_names_mapping(tmp_path):
    output_dir = _write_yolo_dataset(tmp_path / "yolo", data_yaml_extra={"nc": 2, "names": {0: "cat", 1: "dog"}})

    context = YoloAdapter().readme_context(output_dir)

    assert context == {"num_classes": 2, "class_names": ["cat", "dog"]}


def test_checkout_release_noops(tmp_path):
    # A YOLO dataset's raw source isn't a git checkout — never raises,
    # never touches the directory.
    YoloAdapter().checkout_release(tmp_path, version="1.0")
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

    on_disk = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    assert on_disk == result
