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


def test_zenodo_prepare_without_self_contained_still_bundles_the_whole_dataset(tmp_path):
    """Mirror and Link are the same thing for YOLO (see
    ProductAdapter.always_mirror) — no metadata-only export."""
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "zenodo_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
    ])

    assert result.exit_code == 0, result.output
    _assert_yolo_readme(output_dir)
    assert "self-contained" in (output_dir / "README.md").read_text(encoding="utf-8").lower()
    assert (output_dir / "yolo.zip").is_file()
    assert sorted(p.name for p in output_dir.iterdir()) == [
        "CITATION.cff", "LICENSE", "README.md", "checksums-sha256.txt", "metadata.json", "yolo.zip",
    ]


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


def test_b2share_prepare_without_self_contained_still_bundles_the_whole_dataset(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "b2share_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "b2share", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
    ])

    assert result.exit_code == 0, result.output
    _assert_yolo_readme(output_dir)
    assert (output_dir / "yolo.zip").is_file()
    assert not (output_dir / "images").exists()


def test_hfh_prepare_link_mode_still_ships_the_images(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "hfh_out"
    _generate_metadata(input_dir)

    result = runner.invoke(app, [
        "hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--link-images",
    ])

    assert result.exit_code == 0, result.output
    assert (output_dir / "images" / "train" / "img0.jpg").is_file()


def test_readme_has_statistics_and_points_contributing_at_the_datasets_homepage(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    data = yaml.safe_load((input_dir / "data.yaml").read_text(encoding="utf-8"))
    data["homepage"] = "https://example.org/my-yolo"
    (input_dir / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    labels_dir = input_dir / "labels" / "train"
    labels_dir.mkdir(parents=True)
    (labels_dir / "img0.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    _generate_metadata(input_dir)

    for repo in ("hfh", "zenodo", "b2share"):
        output_dir = tmp_path / f"{repo}_out"
        result = runner.invoke(app, [repo, "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])
        assert result.exit_code == 0, result.output
        readme = (output_dir / "README.md").read_text(encoding="utf-8")
        assert "| train | 1 | 1 | 1 |" in readme
        assert "| val | 1 | 0 | 0 |" in readme
        assert "| dog | 1 |" in readme
        assert "welcome at https://example.org/my-yolo" in readme
        assert "wildintel-publisher/issues" not in readme


def test_readme_omits_contributing_without_a_homepage(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    _generate_metadata(input_dir)
    output_dir = tmp_path / "zenodo_out"

    result = runner.invoke(app, ["zenodo", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "## Contributing" not in readme
    assert "This dataset has no label files." in readme


def test_hfh_readme_has_no_hugging_face_repository_section(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    _generate_metadata(input_dir)
    output_dir = tmp_path / "hfh_out"

    result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert "## Hugging Face repository" not in (output_dir / "README.md").read_text(encoding="utf-8")


def test_hfh_prepare_shards_a_split_over_the_per_folder_limit(tmp_path, monkeypatch):
    from wildintel_publisher.services import yolo_adapter

    monkeypatch.setattr(yolo_adapter, "HFH_MAX_FILES_PER_DIRECTORY", 1)
    shard = yolo_adapter.shard_large_splits
    monkeypatch.setattr(yolo_adapter, "shard_large_splits", lambda d: shard(d, max_files=1))
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    (input_dir / "images" / "train" / "img1.jpg").write_bytes(b"fake-image-bytes")
    _generate_metadata(input_dir)
    output_dir = tmp_path / "hfh_out"

    result = runner.invoke(app, ["hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir)])

    assert result.exit_code == 0, result.output
    # metadata.jsonl (write_hf_metadata_jsonl) is the one loose file that's
    # meant to stay directly under images/<split>/, never sharded — it's a
    # small manifest, not an image subject to Hugging Face Hub's per-folder
    # file-count limit, and its own file_name entries already point into the
    # bucket subfolders for the images they describe.
    assert [p.name for p in (output_dir / "images" / "train").iterdir() if p.is_file()] == ["metadata.jsonl"]
    assert "hash-named subfolders" in (output_dir / "README.md").read_text(encoding="utf-8")
    assert (input_dir / "images" / "train" / "img1.jpg").is_file()  # the source is never touched
