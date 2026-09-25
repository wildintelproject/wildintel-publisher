"""Unit tests for the /api/yolo endpoints — a real (tiny) YOLO dataset on
disk, since the working copy and data.yaml editing are the whole point."""
from pathlib import Path

import yaml
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _write_yolo_dataset(root: Path, **data_yaml_extra) -> Path:
    for split in ("train", "val"):
        split_dir = root / "images" / split
        split_dir.mkdir(parents=True, exist_ok=True)
        (split_dir / "img0.jpg").write_bytes(b"fake-image-bytes")
    data = {
        "train": "images/train", "val": "images/val", "nc": 2, "names": ["cat", "dog"],
        "title": "Original title", "version": "1.0", "license": "MIT",
        "authors": [{"name": "Jane Doe"}],
        **data_yaml_extra,
    }
    (root / "data.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


def test_resolve_local_source_creates_a_working_copy_and_a_session(tmp_path):
    source = _write_yolo_dataset(tmp_path / "dataset")

    body = _client().post("/api/yolo/resolve-local-source", json={"path": str(source)}).json()

    assert body["status"] == "valid", body
    working_dir = Path(body["workingDir"])
    assert working_dir != source
    assert (working_dir / "data.yaml").is_file()
    assert not (working_dir / "images").exists()  # images stay in the original

    from services import session_store
    manifest = session_store.read_manifest(body["taskId"])
    assert manifest["product_type"] == "yolo"
    assert manifest["phase"] == "fetched"


def test_resolve_local_source_reports_an_invalid_dataset(tmp_path):
    source = _write_yolo_dataset(tmp_path / "dataset", nc=3)

    body = _client().post("/api/yolo/resolve-local-source", json={"path": str(source)}).json()

    assert body["status"] == "invalid"
    assert "nc is 3 but names lists 2 classes" in body["error"]
    assert body["taskId"]


def test_data_yaml_fields_returns_metadata_dataset_facts_and_warnings(tmp_path):
    source = _write_yolo_dataset(tmp_path / "dataset", test="images/test")
    client = _client()
    working_dir = client.post("/api/yolo/resolve-local-source", json={"path": str(source)}).json()["workingDir"]

    response = client.get("/api/yolo/data-yaml-fields", params={"path": working_dir})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Original title"
    assert body["license"] == {"id": "MIT", "name": "MIT", "url": ""}
    assert body["authors"] == [{"name": "Jane Doe", "affiliation": ""}]
    assert body["class_names"] == ["cat", "dog"]
    assert body["split_image_counts"] == {"train": 1, "val": 1}
    assert any("declares a 'test' split" in w for w in body["warnings"])


def test_update_data_yaml_edits_only_the_working_copy(tmp_path):
    source = _write_yolo_dataset(tmp_path / "dataset")
    original_yaml = (source / "data.yaml").read_text(encoding="utf-8")
    client = _client()
    working_dir = Path(client.post("/api/yolo/resolve-local-source", json={"path": str(source)}).json()["workingDir"])

    response = client.post("/api/yolo/update-data-yaml", json={
        "input_dir": str(working_dir), "title": "Edited title", "description": "Now with a description",
        "version": "2.0", "homepage": None,
        "license": {"id": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0", "url": ""},
        "authors": [{"name": "Ada Lovelace", "affiliation": "Analytical Engines"}],
    })

    assert response.status_code == 200, response.text
    edited = yaml.safe_load((working_dir / "data.yaml").read_text(encoding="utf-8"))
    assert edited["title"] == "Edited title"
    assert edited["authors"] == [{"name": "Ada Lovelace", "affiliation": "Analytical Engines"}]
    assert edited["names"] == ["cat", "dog"]
    assert (source / "data.yaml").read_text(encoding="utf-8") == original_yaml  # original untouched

    summary = client.post("/api/camtrapdp/generate-metadata", json={
        "input_dir": str(working_dir), "product_type": "yolo",
    }).json()
    assert summary["title"] == "Edited title"
    assert summary["license"]["id"] == "CC-BY-4.0"


def test_update_data_yaml_rejects_an_author_without_a_name(tmp_path):
    source = _write_yolo_dataset(tmp_path / "dataset")
    client = _client()
    working_dir = client.post("/api/yolo/resolve-local-source", json={"path": str(source)}).json()["workingDir"]

    response = client.post("/api/yolo/update-data-yaml", json={
        "input_dir": working_dir, "authors": [{"name": "", "affiliation": "Somewhere"}],
    })

    assert response.status_code == 422
