"""Unit tests for services.trapper's local datapackage.json patching helpers
(_fix_datapackage_license, _decompress_gzipped_tables/_clear_datapackage_resource_compression),
test_connection's exception-to-RuntimeError mapping, and fetch_camtrapdp_package's
own include_events wiring."""
import gzip
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from trapper_client import err
from trapper_client.schemas.classifications import ResultsDataPackageData, ResultsDataPackageResponse

from wildintel_publisher.services.trapper import (
    _clear_datapackage_resource_compression,
    _decompress_gzipped_tables,
    _fix_datapackage_license,
    fetch_camtrapdp_package,
)
from wildintel_publisher.services.trapper import test_connection as trapper_test_connection


def _write_datapackage(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "datapackage.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_fix_datapackage_license_adds_missing_scopes(tmp_path):
    _write_datapackage(tmp_path, {"licenses": [{"name": "private", "scope": "data"}, {"name": "private", "scope": "media"}]})

    _fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="Creative Commons Attribution 4.0", license_url="https://creativecommons.org/licenses/by/4.0/")

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    scopes = {lic["scope"]: lic for lic in data["licenses"]}
    assert scopes["data"]["name"] == "CC-BY-4.0"
    assert scopes["media"]["name"] == "CC-BY-4.0"
    assert len(data["licenses"]) == 2  # private placeholders replaced, not appended


def test_fix_datapackage_license_leaves_real_scopes_untouched(tmp_path):
    _write_datapackage(tmp_path, {"licenses": [
        {"name": "MIT", "scope": "data"},
        {"name": "private", "scope": "media"},
    ]})

    _fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="CC BY 4.0", license_url="https://example.org")

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    scopes = {lic["scope"]: lic["name"] for lic in data["licenses"]}
    assert scopes["data"] == "MIT"  # untouched
    assert scopes["media"] == "CC-BY-4.0"  # patched


def test_fix_datapackage_license_no_op_when_all_scopes_real(tmp_path):
    original = {"licenses": [{"name": "MIT", "scope": "data"}, {"name": "MIT", "scope": "media"}]}
    path = _write_datapackage(tmp_path, original)
    before = path.read_text(encoding="utf-8")

    _fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="CC BY 4.0", license_url="https://example.org")

    assert path.read_text(encoding="utf-8") == before


def test_fix_datapackage_license_no_op_when_datapackage_missing(tmp_path):
    _fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="CC BY 4.0", license_url="https://example.org")  # must not raise
    assert not (tmp_path / "datapackage.json").exists()


def test_decompress_gzipped_tables_removes_gz_and_strips_compression_marker(tmp_path):
    """Reproduces Trapper's real shape: resources declare "path": "deployments.csv"
    (no .gz suffix) but the physical file inside the zip is deployments.csv.gz,
    with a stray "compression": "gz" key that must be cleared once decompressed
    (otherwise frictionless/any reader tries to gunzip an already-plain CSV)."""
    gz_path = tmp_path / "deployments.csv.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"deploymentID\nd1\n")

    _write_datapackage(tmp_path, {
        "resources": [{"name": "deployments", "path": "deployments.csv", "compression": "gz"}],
    })

    _decompress_gzipped_tables(tmp_path)

    assert not gz_path.exists()
    assert (tmp_path / "deployments.csv").read_bytes() == b"deploymentID\nd1\n"
    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert "compression" not in data["resources"][0]
    assert data["resources"][0]["path"] == "deployments.csv"


def test_clear_datapackage_resource_compression_handles_path_still_ending_in_gz(tmp_path):
    """Fallback branch: if `path` itself still ends in .gz (unlike Trapper's
    real behavior, but defensive in case that convention ever changes), it
    gets renamed to the decompressed name too."""
    _write_datapackage(tmp_path, {
        "resources": [{"name": "media", "path": "media.csv.gz", "compression": "gz"}],
    })

    _clear_datapackage_resource_compression(tmp_path, {"media.csv"})

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["resources"][0]["path"] == "media.csv"
    assert "compression" not in data["resources"][0]


def test_clear_datapackage_resource_compression_no_op_when_nothing_decompressed(tmp_path):
    original = {"resources": [{"name": "media", "path": "media.csv", "compression": "gz"}]}
    path = _write_datapackage(tmp_path, original)
    before = path.read_text(encoding="utf-8")

    _clear_datapackage_resource_compression(tmp_path, set())

    assert path.read_text(encoding="utf-8") == before


def test_test_connection_maps_unauthorized_to_runtime_error(monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            self.classification_projects = self

        def find(self, pk):
            raise err.UnauthorizedError("bad credentials")

    monkeypatch.setattr("wildintel_publisher.services.trapper.TrapperClient", _FakeClient)
    with pytest.raises(RuntimeError, match="Incorrect Trapper username or password"):
        trapper_test_connection(trapper_url="https://trapper.example", trapper_user="u", trapper_password="p", project_id=1)


def test_test_connection_maps_not_found_to_runtime_error(monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            self.classification_projects = self

        def find(self, pk):
            raise err.NotFoundError("no such project")

    monkeypatch.setattr("wildintel_publisher.services.trapper.TrapperClient", _FakeClient)
    with pytest.raises(RuntimeError, match="does not exist"):
        trapper_test_connection(trapper_url="https://trapper.example", trapper_user="u", trapper_password="p", project_id=99)


def test_test_connection_maps_connect_error_to_runtime_error(monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            self.classification_projects = self

        def find(self, pk):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("wildintel_publisher.services.trapper.TrapperClient", _FakeClient)
    with pytest.raises(RuntimeError, match="Could not connect"):
        trapper_test_connection(trapper_url="https://trapper.example", trapper_user="u", trapper_password="p", project_id=1)


def _minimal_camtrapdp_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("datapackage.json", json.dumps({"resources": []}))
    return buffer.getvalue()


def test_fetch_camtrapdp_package_forwards_include_events(tmp_path, monkeypatch):
    captured = {}

    class _FakePackageComponent:
        def get_project_package(self, **kwargs):
            captured["kwargs"] = kwargs
            return ResultsDataPackageResponse(
                data=ResultsDataPackageData(message="ok", package="https://trapper.example/download?rt=xyz"),
            )

    class _FakeClient:
        def __init__(self, **kwargs):
            self.classification_package = _FakePackageComponent()

        def make_request(self, endpoint, method):
            return type("R", (), {"content": _minimal_camtrapdp_zip_bytes()})()

    monkeypatch.setattr("wildintel_publisher.services.trapper.TrapperClient", _FakeClient)

    fetch_camtrapdp_package(
        trapper_url="https://trapper.example", trapper_user="u", trapper_password="p",
        project_id=1, deployment_id="d1", output_dir=tmp_path, include_events=False,
    )

    assert captured["kwargs"]["include_events"] is False


def test_fetch_camtrapdp_package_defaults_include_events_to_true(tmp_path, monkeypatch):
    captured = {}

    class _FakePackageComponent:
        def get_project_package(self, **kwargs):
            captured["kwargs"] = kwargs
            return ResultsDataPackageResponse(
                data=ResultsDataPackageData(message="ok", package="https://trapper.example/download?rt=xyz"),
            )

    class _FakeClient:
        def __init__(self, **kwargs):
            self.classification_package = _FakePackageComponent()

        def make_request(self, endpoint, method):
            return type("R", (), {"content": _minimal_camtrapdp_zip_bytes()})()

    monkeypatch.setattr("wildintel_publisher.services.trapper.TrapperClient", _FakeClient)

    fetch_camtrapdp_package(
        trapper_url="https://trapper.example", trapper_user="u", trapper_password="p",
        project_id=1, deployment_id="d1", output_dir=tmp_path,
    )

    assert captured["kwargs"]["include_events"] is True


def test_test_connection_returns_project_on_success(monkeypatch):
    sentinel_project = object()

    class _FakeClient:
        def __init__(self, **kwargs):
            self.classification_projects = self

        def find(self, pk):
            return sentinel_project

    monkeypatch.setattr("wildintel_publisher.services.trapper.TrapperClient", _FakeClient)
    result = trapper_test_connection(trapper_url="https://trapper.example", trapper_user="u", trapper_password="p", project_id=1)
    assert result is sentinel_project
