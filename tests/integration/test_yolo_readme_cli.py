"""Integration tests proving Zenodo/B2SHARE also render a YOLO-specific
README (not Camtrap DP's) for a YOLO product — see
ProductAdapter.readme_context (repo/product_type pick the README templates directly). HFH's own equivalent
is covered by test_yolo_hfh_pipeline_cli.py; this file only needs to reach
'prepare' (where README.md gets written), not a full upload."""
from pathlib import Path

import yaml
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _write_yolo_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        split_dir = root / "images" / split
        split_dir.mkdir(parents=True, exist_ok=True)
        (split_dir / "img0.jpg").write_bytes(b"fake-image-bytes")

    data = {
        "train": "images/train", "val": "images/val", "nc": 2, "names": ["cat", "dog"],
        "title": "Test YOLO Dataset", "description": "A test object-detection dataset.",
        "version": "1.0", "license": "MIT",
        "authors": [{"name": "Jane Doe", "affiliation": "Test Org"}],
    }
    (root / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


def _generate_metadata(input_dir: Path) -> None:
    result = runner.invoke(app, [
        "product", "generate-metadata", "--input-dir", str(input_dir), "--product-type", "yolo",
    ])
    assert result.exit_code == 0, result.output


def _assert_yolo_readme(output_dir: Path) -> None:
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "YOLO" in readme
    assert "2 classes: cat, dog" in readme
    assert "Camtrap DP" not in readme
    assert "datapackage.json" not in readme


def test_zenodo_prepare_self_contained_renders_the_yolo_readme(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "zenodo_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
    ])

    assert result.exit_code == 0, result.output
    _assert_yolo_readme(output_dir)
    assert "self-contained" in (output_dir / "README.md").read_text(encoding="utf-8").lower()


def test_zenodo_prepare_metadata_only_renders_the_yolo_readme(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "zenodo_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
    ])

    assert result.exit_code == 0, result.output
    _assert_yolo_readme(output_dir)
    assert "metadata-only" in (output_dir / "README.md").read_text(encoding="utf-8").lower()


def test_b2share_prepare_self_contained_renders_the_yolo_readme(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "b2share_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--self-contained",
    ])

    assert result.exit_code == 0, result.output
    _assert_yolo_readme(output_dir)
    assert "self-contained" in (output_dir / "README.md").read_text(encoding="utf-8").lower()
    assert not (output_dir / "images").exists()  # bundled inside yolo.zip, loose copy removed
    assert (output_dir / "yolo.zip").is_file()


def test_b2share_prepare_metadata_only_renders_the_yolo_readme(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "b2share_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
    ])

    assert result.exit_code == 0, result.output
    _assert_yolo_readme(output_dir)
    assert "metadata-only" in (output_dir / "README.md").read_text(encoding="utf-8").lower()
