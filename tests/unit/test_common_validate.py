"""Unit tests for services.common.validate_camtrap_dp's own logic (profile
auto-injection + pass/fail reporting) — with frictionless_validate itself
mocked out, so no real network call to fetch the Camtrap DP schema happens.

Imports `validate_camtrap_dp` by name at module-import time, which binds an
independent reference to the original function object — unaffected by the
autouse `_mock_camtrap_dp_validation` fixture (tests/conftest.py), which only
rebinds the `common` module's own attribute for other tests' convenience.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from wildintel_publisher.services.common import CAMTRAP_DP_PROFILE_URL, validate_camtrap_dp


def _fake_report(*, valid: bool, errors: list | None = None):
    errors = errors or []
    return SimpleNamespace(
        valid=valid,
        flatten=lambda fields: [("error", "Package Error", msg) for msg in errors],
    )


def test_validate_camtrap_dp_injects_missing_profile(tmp_path):
    datapackage_path = tmp_path / "datapackage.json"
    datapackage_path.write_text(json.dumps({"title": "T"}), encoding="utf-8")

    with patch("wildintel_publisher.services.common.frictionless_validate", return_value=_fake_report(valid=True)):
        validate_camtrap_dp(tmp_path)

    data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    assert data["profile"] == CAMTRAP_DP_PROFILE_URL


def test_validate_camtrap_dp_leaves_existing_profile_untouched(tmp_path):
    datapackage_path = tmp_path / "datapackage.json"
    datapackage_path.write_text(json.dumps({"title": "T", "profile": "https://example.org/custom-profile.json"}), encoding="utf-8")

    with patch("wildintel_publisher.services.common.frictionless_validate", return_value=_fake_report(valid=True)):
        validate_camtrap_dp(tmp_path)

    data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    assert data["profile"] == "https://example.org/custom-profile.json"


def test_validate_camtrap_dp_raises_on_invalid_report(tmp_path):
    datapackage_path = tmp_path / "datapackage.json"
    datapackage_path.write_text(json.dumps({"title": "T", "profile": CAMTRAP_DP_PROFILE_URL}), encoding="utf-8")

    with patch(
        "wildintel_publisher.services.common.frictionless_validate",
        return_value=_fake_report(valid=False, errors=["'project' is a required property"]),
    ):
        with pytest.raises(RuntimeError, match="does not pass Camtrap DP validation"):
            validate_camtrap_dp(tmp_path)


def test_validate_camtrap_dp_raises_on_missing_profile_when_patch_disabled(tmp_path):
    datapackage_path = tmp_path / "datapackage.json"
    datapackage_path.write_text(json.dumps({"title": "T"}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="does not declare a \"profile\""):
        validate_camtrap_dp(tmp_path, patch_missing_profile=False)

    # Nothing written — unlike the default, this path never touches the file,
    # since it's meant for a throwaway copy of a zip hosted somewhere this
    # project doesn't control (see gbif.validate_camtrap_dp_archive).
    data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    assert "profile" not in data


def test_validate_camtrap_dp_raises_when_datapackage_missing(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        validate_camtrap_dp(tmp_path)


def test_validate_camtrap_dp_raises_on_malformed_json(tmp_path):
    (tmp_path / "datapackage.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        validate_camtrap_dp(tmp_path)
