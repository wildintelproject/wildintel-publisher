"""Unit tests for services.gbif's pure-logic functions and validation errors —
the GBIF Registry API itself is only exercised in tests/integration/test_gbif_cli.py."""
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from wildintel_publisher.services.gbif import (
    RECORD_FILENAME,
    build_dataset_payload,
    register_gbif_dataset,
    validate_camtrap_dp_archive,
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


def test_build_dataset_payload_includes_homepage_when_given():
    payload = build_dataset_payload(
        publishing_organization_key="org-1", installation_key="inst-1",
        title="T", description="D", license_url="https://creativecommons.org/licenses/by/4.0/",
        registry_language="eng", homepage="https://huggingface.co/datasets/alice/dataset",
    )
    assert payload["homepage"] == "https://huggingface.co/datasets/alice/dataset"


def test_build_dataset_payload_omits_homepage_when_not_given():
    payload = build_dataset_payload(
        publishing_organization_key="org-1", installation_key="inst-1",
        title="T", description="D", license_url="https://creativecommons.org/licenses/by/4.0/",
        registry_language="eng",
    )
    assert "homepage" not in payload


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


def _fake_stream_response(status_code: int, body: bytes) -> MagicMock:
    """A stand-in for httpx.stream(...)'s context manager — mirrors the
    shape validate_camtrap_dp_archive actually uses (status_code,
    iter_bytes())."""
    response = MagicMock()
    response.status_code = status_code
    response.iter_bytes.return_value = [body]
    context_manager = MagicMock()
    context_manager.__enter__.return_value = response
    context_manager.__exit__.return_value = False
    return context_manager


def test_validate_camtrap_dp_archive_rejects_non_http_url():
    with pytest.raises(RuntimeError, match="http"):
        validate_camtrap_dp_archive("ftp://example.org/archive.zip")


def test_validate_camtrap_dp_archive_rejects_a_failed_download():
    with patch("httpx.stream", return_value=_fake_stream_response(404, b"")):
        with pytest.raises(RuntimeError, match="Could not download"):
            validate_camtrap_dp_archive("https://example.org/archive.zip")


def test_validate_camtrap_dp_archive_rejects_content_that_is_not_a_zip():
    # This is exactly the mistake that produces GBIF's silent
    # finishReason=ABORT: pointing --archive-url at a bare datapackage.json
    # (plain JSON, not an archive) instead of a zip.
    not_a_zip = json.dumps({"name": "test"}).encode("utf-8")
    with patch("httpx.stream", return_value=_fake_stream_response(200, not_a_zip)):
        with pytest.raises(RuntimeError, match="not a valid zip archive"):
            validate_camtrap_dp_archive("https://example.org/datapackage.json")


def test_validate_camtrap_dp_archive_passes_for_a_valid_camtrap_dp_zip(camtrapdp_dir, tmp_path):
    # common.validate_camtrap_dp itself is mocked to a no-op by the autouse
    # tests/conftest.py::_mock_camtrap_dp_validation fixture (real
    # frictionless validation needs network access to fetch the official
    # schema) — this test only proves validate_camtrap_dp_archive's own
    # download/zip-extraction plumbing reaches that call correctly.
    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        validate_camtrap_dp_archive("https://example.org/camtrapdp-local.zip")  # must not raise


def test_validate_camtrap_dp_archive_passes_for_a_zip_nested_in_a_single_top_level_folder(camtrapdp_dir, tmp_path):
    """The real shape services.common.write_remote_zip produces — GBIF's own
    CAMTRAP_DP crawler requires exactly one root directory once it unpacks
    the archive (org.gbif.utils.file.CompressionUtil errors with "More than
    one root directory" for a flat zip otherwise, silently treating the
    whole dataset as empty)."""
    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, f"camtrapdp-remote/{filename}")

    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        validate_camtrap_dp_archive("https://example.org/camtrapdp-remote.zip")  # must not raise


def test_validate_camtrap_dp_archive_rejects_relative_media_filepaths(camtrapdp_dir, tmp_path):
    # A self-contained package's own filePath convention (relative to a
    # sibling images/ folder) is valid Camtrap DP on its own, but useless to
    # GBIF — it never hosts the media itself, so every filePath must already
    # be an absolute, independently resolvable URL.
    input_dir = camtrapdp_dir()
    (input_dir / "media.csv").write_text(
        "mediaID,deploymentID,filePath,fileName,filePublic\n"
        "m1,d1,images/m1.jpg,m1.jpg,true\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        with pytest.raises(RuntimeError, match="filePath value.*http\\(s\\) URL"):
            validate_camtrap_dp_archive("https://example.org/camtrapdp.zip")


def test_validate_camtrap_dp_archive_rejects_local_absolute_media_filepaths(camtrapdp_dir, tmp_path):
    input_dir = camtrapdp_dir()
    (input_dir / "media.csv").write_text(
        "mediaID,deploymentID,filePath,fileName,filePublic\n"
        "m1,d1,/home/user/images/m1.jpg,m1.jpg,true\n",
        encoding="utf-8",
    )
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        with pytest.raises(RuntimeError, match="filePath value.*http\\(s\\) URL"):
            validate_camtrap_dp_archive("https://example.org/camtrapdp.zip")


def test_validate_camtrap_dp_archive_disables_profile_patching(camtrapdp_dir, tmp_path, monkeypatch):
    # This is a throwaway extraction of a URL this project doesn't control —
    # patching a missing "profile" here would only fix a copy that's about
    # to be discarded, while the real, unpatched remote file is what GBIF's
    # own crawler will actually fetch (see common.validate_camtrap_dp's own
    # patch_missing_profile docstring). validate_camtrap_dp_archive must
    # therefore call it with patch_missing_profile=False.
    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    fake_validate = MagicMock()
    monkeypatch.setattr("wildintel_publisher.services.gbif.common.validate_camtrap_dp", fake_validate)
    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        validate_camtrap_dp_archive("https://example.org/camtrapdp-local.zip")

    fake_validate.assert_called_once()
    assert fake_validate.call_args.kwargs.get("patch_missing_profile") is False


def test_validate_camtrap_dp_archive_propagates_a_schema_validation_failure(camtrapdp_dir, tmp_path, monkeypatch):
    # Build the fixture BEFORE overriding the mock: camtrapdp_dir() itself
    # validates the package on the way in (via the same common.
    # validate_camtrap_dp attribute, normally a harmless no-op — see
    # tests/conftest.py::_mock_camtrap_dp_validation), so the failing
    # override below must only apply to validate_camtrap_dp_archive's own,
    # later call.
    input_dir = camtrapdp_dir()
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for filename in ["datapackage.json", "deployments.csv", "media.csv", "observations.csv"]:
            zf.write(input_dir / filename, filename)

    monkeypatch.setattr(
        "wildintel_publisher.services.gbif.common.validate_camtrap_dp",
        MagicMock(side_effect=RuntimeError("does not pass Camtrap DP validation")),
    )
    with patch("httpx.stream", return_value=_fake_stream_response(200, zip_path.read_bytes())):
        with pytest.raises(RuntimeError, match="does not pass Camtrap DP validation"):
            validate_camtrap_dp_archive("https://example.org/camtrapdp-local.zip")
