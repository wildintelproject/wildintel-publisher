"""Unit tests for services.gbif's pure-logic functions and validation errors —
the GBIF Registry API itself is only exercised in tests/integration/test_gbif_cli.py."""
import json
from unittest.mock import patch

import pytest

from wildintel_publisher.services.gbif import (
    RECORD_FILENAME,
    build_dataset_payload,
    register_gbif_dataset,
)


def test_build_dataset_payload_shape():
    payload = build_dataset_payload(
        publishing_organization_key="org-1", installation_key="inst-1",
        title="T", description="D", license_url="https://creativecommons.org/licenses/by/4.0/",
        registry_language="eng",
    )
    assert payload == {
        "publishingOrganizationKey": "org-1",
        "installationKey": "inst-1",
        "type": "OCCURRENCE",
        "title": "T",
        "description": "D",
        "language": "eng",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }


def _register_kwargs(**overrides):
    kwargs = dict(
        environment="sandbox", publishing_organization_key="org-1", installation_key="inst-1",
        username="user", password="pass", title="T", description="D",
        license_url="https://creativecommons.org/licenses/by/4.0/", registry_language="eng",
    )
    kwargs.update(overrides)
    return kwargs


def test_register_rejects_non_http_archive_url(tmp_path):
    with pytest.raises(RuntimeError, match="http"):
        register_gbif_dataset("ftp://example.org/x.zip", tmp_path, **_register_kwargs())


def test_register_rejects_unknown_environment(tmp_path):
    with pytest.raises(RuntimeError, match="sandbox"):
        register_gbif_dataset(
            "https://example.org/x.zip", tmp_path, **_register_kwargs(environment="staging"),
        )


def test_register_requires_organization_and_installation_keys(tmp_path):
    with pytest.raises(RuntimeError, match="publishing_organization_key"):
        register_gbif_dataset(
            "https://example.org/x.zip", tmp_path, **_register_kwargs(publishing_organization_key=None),
        )


def test_register_requires_credentials(tmp_path):
    with pytest.raises(RuntimeError, match="credentials"):
        register_gbif_dataset(
            "https://example.org/x.zip", tmp_path, **_register_kwargs(username=None, password=None),
        )


def test_register_dry_run_makes_no_http_calls_and_writes_no_record(tmp_path):
    with patch("httpx.post") as fake_post, patch("httpx.put") as fake_put, \
         patch("httpx.get") as fake_get, patch("httpx.delete") as fake_delete:
        result = register_gbif_dataset(
            "https://example.org/x.zip", tmp_path, **_register_kwargs(dry_run=True),
        )
    fake_post.assert_not_called()
    fake_put.assert_not_called()
    fake_get.assert_not_called()
    fake_delete.assert_not_called()
    assert result["dataset_key"] is None
    assert not (tmp_path / RECORD_FILENAME).exists()


def test_register_dry_run_reports_update_when_a_record_already_exists(tmp_path):
    (tmp_path / RECORD_FILENAME).write_text(
        json.dumps({"dataset_key": "existing-key", "environment": "sandbox"}), encoding="utf-8",
    )
    with patch("httpx.post") as fake_post, patch("httpx.put") as fake_put:
        result = register_gbif_dataset(
            "https://example.org/x.zip", tmp_path, **_register_kwargs(dry_run=True),
        )
    fake_post.assert_not_called()
    fake_put.assert_not_called()
    assert result["dataset_key"] == "existing-key"
