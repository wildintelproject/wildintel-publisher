"""Unit tests for services.common.fix_datapackage_license — moved here from
services.trapper (still exercised there via 'trapper download', but now
also reused by camtrapdp_source.resolve_local_camtrapdp_source/
fetch_camtrap_dp_archive, for a Camtrap DP whose datapackage.json still
carries Trapper's own "private" license placeholder, e.g. an export
downloaded and extracted by hand instead of through 'trapper download')."""
import json
from pathlib import Path

from wildintel_publisher.core.services.common import fix_datapackage_license


def _write_datapackage(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "datapackage.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_fix_datapackage_license_adds_missing_scopes(tmp_path):
    _write_datapackage(tmp_path, {"licenses": [{"name": "private", "scope": "data"}, {"name": "private", "scope": "media"}]})

    fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="Creative Commons Attribution 4.0", license_url="https://creativecommons.org/licenses/by/4.0/")

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

    fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="CC BY 4.0", license_url="https://example.org")

    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    scopes = {lic["scope"]: lic["name"] for lic in data["licenses"]}
    assert scopes["data"] == "MIT"  # untouched
    assert scopes["media"] == "CC-BY-4.0"  # patched


def test_fix_datapackage_license_no_op_when_all_scopes_real(tmp_path):
    original = {"licenses": [{"name": "MIT", "scope": "data"}, {"name": "MIT", "scope": "media"}]}
    path = _write_datapackage(tmp_path, original)
    before = path.read_text(encoding="utf-8")

    fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="CC BY 4.0", license_url="https://example.org")

    assert path.read_text(encoding="utf-8") == before


def test_fix_datapackage_license_no_op_when_datapackage_missing(tmp_path):
    fix_datapackage_license(tmp_path, license_id="CC-BY-4.0", license_name="CC BY 4.0", license_url="https://example.org")  # must not raise
    assert not (tmp_path / "datapackage.json").exists()
