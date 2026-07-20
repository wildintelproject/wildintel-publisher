"""Regression test for 'product generate-metadata': the command used to
crash with an uncaught TypeError when the underlying product had no
detectable license (metadata['license'] is None, but the command indexed
into it unconditionally) — see wildintel_publisher/commands/product.py."""
from pathlib import Path

import yaml
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _write_yolo_dataset_without_license(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        split_dir = root / "images" / split
        split_dir.mkdir(parents=True, exist_ok=True)
        (split_dir / "img0.jpg").write_bytes(b"fake-image-bytes")

    data = {"train": "images/train", "val": "images/val", "nc": 1, "names": ["cat"]}
    (root / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


def test_generate_metadata_does_not_crash_when_license_is_missing(tmp_path):
    input_dir = _write_yolo_dataset_without_license(tmp_path / "yolo_dataset")

    result = runner.invoke(app, [
        "product", "generate-metadata", "--input-dir", str(input_dir), "--product-type", "yolo",
    ])

    assert result.exit_code == 0, result.output
    assert "license: None" in result.output
    assert "Missing required field(s):" in result.output
    assert "license" in result.output
    assert "title" in result.output
    assert "authors" in result.output
