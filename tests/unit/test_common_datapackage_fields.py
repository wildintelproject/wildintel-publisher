"""Unit tests for services.common.read_datapackage_metadata's "name" field
and update_datapackage_fields — reading/patching datapackage.json's own
name/title/description/version/homepage fields directly, as distinct from
services.product.update_metadata_json (which only ever touches
metadata.json, the app's own publish-pipeline wrapper)."""
import json
from pathlib import Path

from wildintel_publisher.services.common import read_datapackage_metadata, update_datapackage_fields


def _write_datapackage(path: Path, data: dict) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "datapackage.json").write_text(json.dumps(data), encoding="utf-8")
    return path


def test_read_datapackage_metadata_includes_name(tmp_path):
    _write_datapackage(tmp_path, {"name": "my-dataset", "title": "My Dataset"})

    result = read_datapackage_metadata(tmp_path)

    assert result["name"] == "my-dataset"
    assert result["title"] == "My Dataset"


def test_update_datapackage_fields_overwrites_only_the_given_keys(tmp_path):
    _write_datapackage(tmp_path, {
        "name": "old-name", "title": "Old Title", "description": "Old description",
        "version": "1.0", "homepage": "https://old.example",
        "resources": [{"name": "media", "path": "media.csv"}],
    })

    update_datapackage_fields(tmp_path, {"title": "New Title", "version": "2.0"})

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["title"] == "New Title"
    assert data["version"] == "2.0"
    # Untouched keys survive as-is.
    assert data["name"] == "old-name"
    assert data["description"] == "Old description"
    assert data["homepage"] == "https://old.example"
    assert data["resources"] == [{"name": "media", "path": "media.csv"}]


def test_update_datapackage_fields_ignores_none_values(tmp_path):
    _write_datapackage(tmp_path, {"title": "Keep me"})

    update_datapackage_fields(tmp_path, {"title": None, "description": "New description"})

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["title"] == "Keep me"
    assert data["description"] == "New description"


def test_update_datapackage_fields_can_add_a_previously_missing_name(tmp_path):
    _write_datapackage(tmp_path, {"title": "No name yet"})

    update_datapackage_fields(tmp_path, {"name": "brand-new-name"})

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["name"] == "brand-new-name"


def test_patching_datapackage_before_generate_metadata_json_syncs_metadata_json_for_free(camtrapdp_dir):
    """The whole point of editing datapackage.json (rather than
    metadata.json directly, as services.product.update_metadata_json does):
    CamtrapDPAdapter.extract_metadata re-reads title/description/version/
    homepage from datapackage.json every time generate_metadata_json runs —
    so patching datapackage.json BEFORE that call is enough for
    metadata.json (and everything generated from it) to pick up the new
    value, with no separate sync step."""
    from wildintel_publisher.services import product

    input_dir = camtrapdp_dir()  # already has a metadata.json with title "Test Dataset"
    assert product.read_metadata_json(input_dir)["title"] == "Test Dataset"

    update_datapackage_fields(input_dir, {"title": "Edited via the new screen"})
    product.generate_metadata_json(product.CAMTRAPDP, input_dir)

    assert product.read_metadata_json(input_dir)["title"] == "Edited via the new screen"
