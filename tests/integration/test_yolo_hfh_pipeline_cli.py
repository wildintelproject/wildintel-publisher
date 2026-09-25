"""Integration test: a YOLO-format dataset (not Camtrap DP) published to
HuggingFace Hub end to end — 'product generate-metadata' -> 'hfh prepare' ->
'hfh upload'. Proves the ProductAdapter abstraction genuinely generalizes
beyond Camtrap DP, not just in theory. HuggingFace Hub API calls are mocked
out (no real network)."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import yaml
from huggingface_hub.utils import RepositoryNotFoundError
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def _write_yolo_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        images_split_dir = root / "images" / split
        images_split_dir.mkdir(parents=True, exist_ok=True)
        (images_split_dir / "img0.jpg").write_bytes(b"fake-image-bytes")

        labels_split_dir = root / "labels" / split
        labels_split_dir.mkdir(parents=True, exist_ok=True)
        (labels_split_dir / "img0.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    data = {
        "train": "images/train", "val": "images/val", "nc": 1, "names": ["animal"],
        "title": "Test YOLO Dataset", "description": "A test object-detection dataset.",
        "version": "1.0", "license": "MIT",
        "authors": [{"name": "Jane Doe", "affiliation": "Test Org"}],
    }
    (root / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


def test_yolo_dataset_prepared_and_uploaded_to_hfh(tmp_path):
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    output_dir = tmp_path / "hfh_out"

    # Step 1: generate metadata.json for this input — required before any
    # 'hfh prepare' can use it (see services.product.generate_metadata_json).
    gen_result = runner.invoke(app, [
        "product", "generate-metadata", "--input-dir", str(input_dir), "--product-type", "yolo",
    ])
    assert gen_result.exit_code == 0, gen_result.output
    assert (input_dir / "metadata.json").is_file()

    metadata = json.loads((input_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["product_type"] == "yolo"
    assert metadata["title"] == "Test YOLO Dataset"
    assert metadata["publish_history"] == []

    # Step 2: prepare — copies data.yaml + images/ + labels/ and writes
    # README/LICENSE/CITATION/checksums/metadata.json.
    prepare_result = runner.invoke(app, [
        "hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
    ])
    assert prepare_result.exit_code == 0, prepare_result.output

    assert (output_dir / "data.yaml").is_file()
    assert (output_dir / "images" / "train" / "img0.jpg").is_file()
    assert (output_dir / "images" / "val" / "img0.jpg").is_file()
    assert (output_dir / "labels" / "train" / "img0.txt").is_file()
    assert (output_dir / "labels" / "val" / "img0.txt").is_file()
    assert (output_dir / "README.md").is_file()
    assert (output_dir / "CITATION.cff").is_file()
    assert (output_dir / "LICENSE").is_file()

    # A YOLO dataset gets its own README content — not Camtrap DP's (see
    # ProductAdapter.readme_context (repo/product_type pick the README templates directly)).
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "YOLO" in readme
    assert "1 class: animal" in readme
    assert "Camtrap DP" not in readme
    assert "datapackage.json" not in readme

    # No yolo-local.zip: the loose files already are the whole dataset, a
    # zip of them would only double the repository's size.
    assert not list(output_dir.glob("*.zip"))
    assert "yolo-local.zip" not in readme

    # Step 3: upload (mocked HF calls) — mirror mode calls the adapter's
    # link_media_to_hfh (a no-op for YOLO, no CSV to rewrite) and sets
    # metadata.json's homepage to the just-created repo.
    fake_response = httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co"))
    fake_api = MagicMock()
    fake_api.repo_info.side_effect = RepositoryNotFoundError("not found", response=fake_response)

    with patch("wildintel_publisher.services.hfh.whoami", return_value={"name": "tester"}), \
         patch("wildintel_publisher.services.hfh.HfApi", return_value=fake_api), \
         patch("wildintel_publisher.services.hfh.create_repo") as mock_create_repo, \
         patch("wildintel_publisher.services.hfh.upload_folder") as mock_upload_folder:
        upload_result = runner.invoke(app, [
            "hfh", "upload", "--output-dir", str(output_dir), "--repo-id", "alice/yolo-dataset",
        ], env={"HF_TOKEN": "hf_faketoken"})

    assert upload_result.exit_code == 0, upload_result.output
    mock_create_repo.assert_called_once()
    mock_upload_folder.assert_called_once()

    uploaded_metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert uploaded_metadata["homepage"] == "https://huggingface.co/datasets/alice/yolo-dataset"


def test_yolo_publisher_and_copyright_holders_reach_citation_cff(tmp_path):
    """data.yaml's publisher/copyright_holders (set by the web wizard's
    editor from PRODUCT.organizations) end up in CITATION.cff's
    preferred-citation, same as a Camtrap DP's publisher/rightsHolder."""
    input_dir = _write_yolo_dataset(tmp_path / "yolo_dataset")
    data = yaml.safe_load((input_dir / "data.yaml").read_text(encoding="utf-8"))
    data["publisher"] = {"name": "University of Huelva", "website": "https://www.uhu.es/"}
    data["copyright_holders"] = ["Spanish National Research Council"]
    (input_dir / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    output_dir = tmp_path / "hfh_out"

    assert runner.invoke(app, [
        "product", "generate-metadata", "--input-dir", str(input_dir), "--product-type", "yolo",
    ]).exit_code == 0
    metadata = json.loads((input_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["publisher"] == {"name": "University of Huelva", "website": "https://www.uhu.es/"}
    assert metadata["copyright_holders"] == ["Spanish National Research Council"]

    prepare_result = runner.invoke(app, [
        "hfh", "prepare", "--input-dir", str(input_dir), "--output-dir", str(output_dir),
    ])
    assert prepare_result.exit_code == 0, prepare_result.output

    citation = yaml.safe_load((output_dir / "CITATION.cff").read_text(encoding="utf-8"))
    preferred = citation["preferred-citation"]
    assert preferred["publisher"]["name"] == "University of Huelva"
    assert "Spanish National Research Council" in preferred["copyright"]
