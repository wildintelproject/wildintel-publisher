"""Integration tests for 'gbif register' — the GBIF Registry API is mocked
out (no real network). Unlike hfh/zenodo/b2share, there is no 'prepare'/
'upload' step: 'gbif register' only reads metadata.json (already written by
services.product.generate_metadata_json, see the camtrapdp_dir fixture) and
points GBIF at an already-hosted --archive-url."""
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from wildintel_publisher.main import app
from wildintel_publisher.services.gbif import RECORD_FILENAME

runner = CliRunner()

ARCHIVE_URL = "https://huggingface.co/datasets/user/dataset/resolve/main/camtrapdp.zip"


def _fake_response(status_code=200, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data if json_data is not None else {}
    response.text = ""
    return response


def _register_args(output_dir, input_dir, **extra_options):
    args = [
        "gbif", "register", "--archive-url", ARCHIVE_URL,
        "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--publishing-organization-key", "org-1", "--installation-key", "inst-1",
    ]
    for key, value in extra_options.items():
        args += [f"--{key.replace('_', '-')}", str(value)]
    return args


def test_gbif_register_without_credentials_reports_error(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("GBIF_USERNAME", raising=False)
    monkeypatch.delenv("GBIF_PASSWORD", raising=False)
    input_dir = camtrapdp_dir("trapper_out")

    result = runner.invoke(app, _register_args(tmp_path / "gbif_out", input_dir))

    assert result.exit_code == 1
    assert "credentials" in result.output.lower()


def test_gbif_register_without_organization_or_installation_reports_error(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("GBIF_USERNAME", "user")
    monkeypatch.setenv("GBIF_PASSWORD", "pass")
    input_dir = camtrapdp_dir("trapper_out")

    args = [
        "gbif", "register", "--archive-url", ARCHIVE_URL,
        "--input-dir", str(input_dir), "--output-dir", str(tmp_path / "gbif_out"),
    ]
    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert "organization" in result.output.lower()


def test_gbif_register_rejects_non_camtrapdp_product(tmp_path, monkeypatch):
    monkeypatch.setenv("GBIF_USERNAME", "user")
    monkeypatch.setenv("GBIF_PASSWORD", "pass")

    from wildintel_publisher.services import product
    input_dir = tmp_path / "yolo_dataset"
    input_dir.mkdir()
    product.write_metadata_json(input_dir, {
        "product_type": product.YOLO, "title": "T", "description": "D", "version": "1.0",
        "license": {"id": "MIT", "name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        "authors": [{"name": "A"}], "publish_history": [],
    })

    result = runner.invoke(app, _register_args(tmp_path / "gbif_out", input_dir))

    assert result.exit_code == 1
    assert "camtrap dp" in result.output.lower()


def test_gbif_register_creates_then_updates_dataset_and_replaces_endpoint(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("GBIF_USERNAME", "user")
    monkeypatch.setenv("GBIF_PASSWORD", "pass")
    input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    output_dir = tmp_path / "gbif_out"

    state = {"dataset_key": "new-dataset-key", "endpoints": []}

    def fake_post(url, **kwargs):
        if url.endswith("/v1/dataset"):
            return _fake_response(201, state["dataset_key"])
        if url.endswith(f"/v1/dataset/{state['dataset_key']}/endpoint"):
            endpoint = {"key": len(state["endpoints"]) + 1, **kwargs["json"]}
            state["endpoints"].append(endpoint)
            return _fake_response(201, endpoint)
        raise AssertionError(f"unexpected POST {url}")

    def fake_put(url, **kwargs):
        assert url.endswith(f"/v1/dataset/{state['dataset_key']}")
        return _fake_response(200, {})

    def fake_get(url, **kwargs):
        assert url.endswith(f"/v1/dataset/{state['dataset_key']}/endpoint")
        return _fake_response(200, state["endpoints"])

    def fake_delete(url, **kwargs):
        deleted_key = int(url.rsplit("/", 1)[-1])
        state["endpoints"] = [e for e in state["endpoints"] if e["key"] != deleted_key]
        return _fake_response(204, {})

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get), patch("httpx.delete", side_effect=fake_delete):
        first = runner.invoke(app, _register_args(output_dir, input_dir))
        assert first.exit_code == 0, first.output

        record = json.loads((output_dir / RECORD_FILENAME).read_text(encoding="utf-8"))
        assert record["dataset_key"] == "new-dataset-key"
        assert len(state["endpoints"]) == 1
        assert state["endpoints"][0]["type"] == "CAMTRAP_DP"
        assert state["endpoints"][0]["url"] == ARCHIVE_URL

        # Re-running 'register' must update the SAME dataset and replace the
        # endpoint, never create a second dataset or a duplicate endpoint.
        second = runner.invoke(app, _register_args(output_dir, input_dir))
        assert second.exit_code == 0, second.output
        assert len(state["endpoints"]) == 1


def test_gbif_register_dry_run_makes_no_http_calls(camtrapdp_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("GBIF_USERNAME", "user")
    monkeypatch.setenv("GBIF_PASSWORD", "pass")
    input_dir = camtrapdp_dir("trapper_out")
    output_dir = tmp_path / "gbif_out"

    with patch("httpx.post") as fake_post, patch("httpx.put") as fake_put:
        result = runner.invoke(app, _register_args(output_dir, input_dir) + ["--dry-run"])
        assert result.exit_code == 0, result.output

    fake_post.assert_not_called()
    fake_put.assert_not_called()
    assert not (output_dir / RECORD_FILENAME).exists()
