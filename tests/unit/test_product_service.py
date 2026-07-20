"""Unit tests for services.product's generic metadata.json envelope
(independent of any specific ProductAdapter)."""
import json

import pytest

from wildintel_publisher.services import product


def test_registered_product_types_includes_the_built_in_adapters():
    # camtrapdp_adapter/yolo_adapter self-register on import (see
    # services/__init__.py) — this fails loudly if that wiring breaks.
    assert {"camtrapdp", "yolo"} <= set(product.registered_product_types())


def test_get_adapter_raises_for_an_unknown_product_type():
    with pytest.raises(RuntimeError, match="Unknown product type"):
        product.get_adapter("something-nobody-registered")


def test_write_and_read_metadata_json_round_trip(tmp_path):
    data = {"product_type": "camtrapdp", "title": "T", "publish_history": []}
    product.write_metadata_json(tmp_path, data)
    assert product.read_metadata_json(tmp_path) == data


def test_read_metadata_json_raises_when_missing(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        product.read_metadata_json(tmp_path)


def test_write_metadata_json_rejects_a_license_that_is_not_an_object(tmp_path):
    with pytest.raises(RuntimeError, match="invalid"):
        product.write_metadata_json(tmp_path, {"product_type": "camtrapdp", "license": "CC-BY-4.0"})


def test_write_metadata_json_rejects_an_unknown_field(tmp_path):
    with pytest.raises(RuntimeError, match="invalid"):
        product.write_metadata_json(tmp_path, {"product_type": "camtrapdp", "not_a_real_field": True})


def test_read_metadata_json_rejects_a_file_that_was_hand_edited_into_a_bad_shape(tmp_path):
    # write_metadata_json would have caught this on the way in — this
    # simulates a metadata.json that got edited outside the tool.
    (tmp_path / "metadata.json").write_text(
        json.dumps({"product_type": "camtrapdp", "authors": {"name": "Alice"}}), encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="does not match"):
        product.read_metadata_json(tmp_path)


def test_copy_metadata_json_carries_the_file_forward(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    product.write_metadata_json(input_dir, {"product_type": "camtrapdp", "publish_history": [{"note": "a"}]})

    product.copy_metadata_json(input_dir, output_dir)

    assert product.read_metadata_json(output_dir) == {"product_type": "camtrapdp", "publish_history": [{"note": "a"}]}


def test_append_publish_history_accumulates_entries(tmp_path):
    product.write_metadata_json(tmp_path, {"product_type": "camtrapdp", "publish_history": []})

    product.append_publish_history(tmp_path, {"repo": "hfh", "mode": "mirror"})
    product.append_publish_history(tmp_path, {"repo": "zenodo", "mode": "link"})

    data = product.read_metadata_json(tmp_path)
    assert data["publish_history"] == [
        {"repo": "hfh", "mode": "mirror"},
        {"repo": "zenodo", "mode": "link"},
    ]


def test_missing_required_fields_lists_what_the_extractor_could_not_determine():
    data = {
        "product_type": "camtrapdp", "title": "T", "description": None,
        "version": "1.0", "license": None, "authors": [], "homepage": None,
    }
    assert product.missing_required_fields(data) == ["description", "license", "authors"]


def test_missing_required_fields_ignores_homepage():
    # homepage is allowed to stay null forever (see write_homepage) — it's
    # never something the user has to fill in before proceeding.
    data = {
        "product_type": "camtrapdp", "title": "T", "description": "D",
        "version": "1.0", "license": {"id": "MIT"}, "authors": [{"name": "A"}], "homepage": None,
    }
    assert product.missing_required_fields(data) == []


def test_update_metadata_json_fills_the_gaps_and_keeps_the_rest(tmp_path):
    product.write_metadata_json(tmp_path, {
        "product_type": "camtrapdp", "title": "T", "description": None,
        "version": None, "license": None, "authors": [], "publish_history": [],
    })

    result = product.update_metadata_json(tmp_path, {
        "description": "D", "version": "2.0",
        "license": {"id": "CC-BY-4.0", "name": "CC BY 4.0", "url": ""},
        "authors": [{"name": "Alice", "affiliation": "Test Org"}],
    })

    assert product.missing_required_fields(result) == []
    assert result["title"] == "T"
    assert product.read_metadata_json(tmp_path) == result


def test_write_homepage_sets_the_field_without_touching_the_rest(tmp_path):
    product.write_metadata_json(tmp_path, {"product_type": "camtrapdp", "title": "T", "publish_history": []})

    product.write_homepage(tmp_path, "https://huggingface.co/datasets/alice/dataset")

    data = product.read_metadata_json(tmp_path)
    assert data["homepage"] == "https://huggingface.co/datasets/alice/dataset"
    assert data["title"] == "T"


def test_zip_directory_excludes_the_given_names(tmp_path):
    import zipfile

    source_dir = tmp_path / "src"
    (source_dir / "sub").mkdir(parents=True)
    (source_dir / "data.txt").write_text("x", encoding="utf-8")
    (source_dir / "sub" / "nested.txt").write_text("y", encoding="utf-8")
    (source_dir / "README.md").write_text("skip me", encoding="utf-8")
    zip_path = source_dir / "bundle.zip"

    product.zip_directory(source_dir, zip_path, exclude_names={"README.md"})

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert names == {"data.txt", "sub/nested.txt"}
