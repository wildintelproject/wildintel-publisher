"""Unit tests for test_connection's exception-to-RuntimeError mapping and
fetch_camtrapdp_package's own include_events wiring — its local
datapackage.json patching helpers (fix_datapackage_license,
decompress_gzipped_tables/_clear_datapackage_resource_compression) moved to
services.common (see test_common_fix_datapackage_license.py/
test_common_decompress_gzipped_tables.py), now that
resolve_local_camtrapdp_source/fetch_camtrap_dp_archive reuse them too."""
import io
import json
import zipfile

import httpx
import pytest
from trapper_client import err
from trapper_client.schemas.classifications import ResultsDataPackageData, ResultsDataPackageResponse

from wildintel_publisher.services.trapper import fetch_camtrapdp_package
from wildintel_publisher.services.trapper import test_connection as trapper_test_connection


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
