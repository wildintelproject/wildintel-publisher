"""Shared pytest fixtures.

Redirects HOME / XDG_CONFIG_HOME / APPDATA to a throwaway temp directory
*before* anything imports ``wildintel_publisher.config`` (which
auto-creates a settings file in the user's real app-config dir on first
import). This keeps the test suite from touching the developer's actual
~/.config/wildintel-publisher or ~/Documents.
"""
import atexit
import csv
import json
import os
import shutil
import tempfile
from pathlib import Path

_FAKE_HOME = Path(tempfile.mkdtemp(prefix="wildintel-publisher-test-home-"))
os.environ["HOME"] = str(_FAKE_HOME)
os.environ["XDG_CONFIG_HOME"] = str(_FAKE_HOME / ".config")
os.environ["APPDATA"] = str(_FAKE_HOME / "AppData" / "Roaming")
atexit.register(shutil.rmtree, _FAKE_HOME, True)

import pytest  # noqa: E402


def _write_camtrapdp(root: Path, *, include_private_media: bool = True) -> Path:
    """Writes a minimal, structurally-valid Camtrap DP package (datapackage.json +
    deployments/media/observations.csv) to `root`. Not necessarily schema-valid
    against the full official profile (tests that need real frictionless
    validation to pass should mock it) — just enough shape for
    read_datapackage_metadata/keep_only_public_media/resolve_license/
    resolve_authors/etc. to work against."""
    root.mkdir(parents=True, exist_ok=True)

    datapackage = {
        "name": "test-dataset",
        "title": "Test Dataset",
        "description": "A test camera-trap dataset.",
        "version": "1.0",
        "profile": "https://raw.githubusercontent.com/tdwg/camtrap-dp/1.0.2/camtrap-dp-profile.json",
        "licenses": [
            {"name": "CC-BY-4.0", "title": "Creative Commons Attribution 4.0", "path": "https://creativecommons.org/licenses/by/4.0/", "scope": "data"},
            {"name": "CC-BY-4.0", "title": "Creative Commons Attribution 4.0", "path": "https://creativecommons.org/licenses/by/4.0/", "scope": "media"},
        ],
        "contributors": [{"title": "Jane Doe", "organization": "Test Org", "role": "principalInvestigator"}],
        "project": {"id": "p1", "title": "Test Project"},
        "resources": [
            {"name": "deployments", "path": "deployments.csv"},
            {"name": "media", "path": "media.csv"},
            {"name": "observations", "path": "observations.csv"},
        ],
    }
    (root / "datapackage.json").write_text(json.dumps(datapackage, indent=2), encoding="utf-8")

    with (root / "deployments.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["deploymentID", "locationName"])
        writer.writeheader()
        writer.writerow({"deploymentID": "d1", "locationName": "Loc 1"})

    media_rows = [
        {"mediaID": "m1", "deploymentID": "d1", "filePath": "https://trapper.example/m1.jpg?rt=tok1", "fileName": "m1.jpg", "filePublic": "true"},
    ]
    if include_private_media:
        media_rows.append(
            {"mediaID": "m2", "deploymentID": "d1", "filePath": "https://trapper.example/m2.jpg?rt=tok2", "fileName": "m2.jpg", "filePublic": "false"},
        )
    with (root / "media.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mediaID", "deploymentID", "filePath", "fileName", "filePublic"])
        writer.writeheader()
        writer.writerows(media_rows)

    observation_rows = [{"observationID": "o1", "mediaID": "m1"}]
    if include_private_media:
        observation_rows.append({"observationID": "o2", "mediaID": "m2"})
    with (root / "observations.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["observationID", "mediaID"])
        writer.writeheader()
        writer.writerows(observation_rows)

    return root


@pytest.fixture
def camtrapdp_dir(tmp_path: Path):
    """Factory building a minimal Camtrap DP package directory under tmp_path,
    plus its metadata.json (see services.product.generate_metadata_json) —
    every prepare_*_export requires it to already exist in --input-dir.

    Usage::

        input_dir = camtrapdp_dir("trapper_out")
        input_dir = camtrapdp_dir("trapper_out", include_private_media=False)
    """
    from wildintel_publisher.services import product

    def _make(name: str = "camtrapdp", *, include_private_media: bool = True) -> Path:
        root = _write_camtrapdp(tmp_path / name, include_private_media=include_private_media)
        product.generate_metadata_json(product.CAMTRAPDP, root)
        return root

    return _make


@pytest.fixture(autouse=True)
def _mock_camtrap_dp_validation(monkeypatch: pytest.MonkeyPatch):
    """Camtrap DP validation (services.common.validate_camtrap_dp) calls
    frictionless, which fetches the official schema from GitHub over the
    network — too slow/flaky for a unit/integration test suite, and not what
    most of these tests are meant to exercise. Replaced everywhere with a
    no-op by default, since prepare_*_export()/upload_to_*() call it as
    `common.validate_camtrap_dp(...)` (a module-attribute lookup, so patching
    the attribute here affects every caller).

    tests/unit/test_common_validate.py exercises the real function's own
    logic directly: it imports `validate_camtrap_dp` by name at module import
    time (before this fixture runs), which binds its own independent
    reference to the original function object — unaffected by this fixture
    rebinding the attribute on the `common` module later."""
    monkeypatch.setattr(
        "wildintel_publisher.services.common.validate_camtrap_dp",
        lambda output_dir, *, patch_missing_profile=True: None,
    )
