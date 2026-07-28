"""Unit tests for the /api/camtrapdp/* endpoints — reading/serving an
already-obtained product directory via its generic metadata.json."""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from main import app
    return TestClient(app)


def _write_datapackage(output_dir, **fields):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "datapackage.json").write_text(json.dumps(fields), encoding="utf-8")


def _write_metadata_json(directory, **fields):
    directory.mkdir(parents=True, exist_ok=True)
    data = {"product_type": "camtrapdp", "publish_history": [], **fields}
    (directory / "metadata.json").write_text(json.dumps(data), encoding="utf-8")


def test_generate_metadata_writes_the_file(tmp_path):
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )

    # validate_camtrap_dp calls frictionless, which fetches the official
    # schema from GitHub over the network — not what this test means to
    # exercise (see the CLI package's own conftest.py, which does the same
    # for every one of its own tests).
    with patch("wildintel_publisher.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["product_type"] == "camtrapdp"
    assert body["title"] == "My Camtrap DP"
    assert body["publish_history"] == []
    assert (tmp_path / "metadata.json").is_file()


def test_generate_metadata_anonymizes_coordinates_when_requested(tmp_path):
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )
    (tmp_path / "deployments.csv").write_text(
        "deploymentID,latitude,longitude\nd1,41.123456,-3.987654\n", encoding="utf-8",
    )

    with patch("wildintel_publisher.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
            "anonymize_coordinates": True, "coordinate_decimals": 1,
        })

    assert response.status_code == 200
    assert (tmp_path / "deployments.csv").read_text(encoding="utf-8") == (
        "deploymentID,latitude,longitude\nd1,41.1,-4.0\n"
    )


def test_generate_metadata_leaves_coordinates_untouched_by_default(tmp_path):
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )
    (tmp_path / "deployments.csv").write_text(
        "deploymentID,latitude,longitude\nd1,41.123456,-3.987654\n", encoding="utf-8",
    )

    with patch("wildintel_publisher.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    assert "41.123456" in (tmp_path / "deployments.csv").read_text(encoding="utf-8")


def test_generate_metadata_reports_400_when_validation_fails(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)  # no datapackage.json at all
    response = _client().post("/api/camtrapdp/generate-metadata", json={
        "input_dir": str(tmp_path), "product_type": "camtrapdp",
    })
    assert response.status_code == 400


def test_generate_metadata_returns_nulls_instead_of_failing_when_fields_are_missing(tmp_path):
    # No title/description/licenses/contributors at all — extract_metadata
    # is best-effort, so this should still succeed and let the wizard ask
    # the user to fill the gaps (see /complete-metadata below), rather than
    # failing outright.
    _write_datapackage(tmp_path)

    with patch("wildintel_publisher.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["title"] is None
    assert body["description"] is None
    assert body["license"] is None
    assert body["authors"] == []


def test_complete_metadata_fills_the_gaps_and_keeps_the_rest(tmp_path):
    _write_metadata_json(tmp_path, title="T", description=None, version=None, license=None, authors=[])

    response = _client().post("/api/camtrapdp/complete-metadata", json={
        "input_dir": str(tmp_path),
        "description": "D", "version": "1.0",
        "license": {"id": "CC-BY-4.0", "name": "CC BY 4.0", "url": ""},
        "authors": [{"name": "Alice", "affiliation": "Test Org"}],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "T"
    assert body["description"] == "D"
    assert body["version"] == "1.0"
    assert body["license"] == {"id": "CC-BY-4.0", "name": "CC BY 4.0", "url": ""}
    assert body["authors"] == [{"name": "Alice", "affiliation": "Test Org"}]
    assert json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8")) == body


def test_complete_metadata_reports_400_when_input_dir_has_no_metadata_json(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    response = _client().post("/api/camtrapdp/complete-metadata", json={
        "input_dir": str(tmp_path), "title": "T",
    })
    assert response.status_code == 400


def test_summary_returns_404_when_metadata_missing(tmp_path):
    response = _client().get("/api/camtrapdp/summary", params={"path": str(tmp_path)})
    assert response.status_code == 404


def test_summary_returns_headline_fields(tmp_path):
    _write_metadata_json(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        license={"id": "CC-BY-4.0", "name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
        authors=[{"name": "Alice", "affiliation": "Test Org"}],
    )

    response = _client().get("/api/camtrapdp/summary", params={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json() == {
        "product_type": "camtrapdp",
        "title": "My Camtrap DP",
        "description": "A test package.",
        "version": "1.0",
        "license": {"id": "CC-BY-4.0", "name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
        "authors": [{"name": "Alice", "affiliation": "Test Org"}],
        "homepage": None,
        "hfh_repo_id": None,
    }


def test_summary_detects_hfh_repo_id_from_metadata_homepage(tmp_path):
    """If a previous HFH publish step in mirror mode already set
    metadata.json's "homepage" to the HuggingFace Hub repo the images got
    uploaded to (see product.write_homepage), the Zenodo/B2SHARE forms
    should be able to prefill from it instead of asking the user to retype
    it."""
    _write_metadata_json(tmp_path, title="My Camtrap DP", homepage="https://huggingface.co/datasets/alice/dataset")

    response = _client().get("/api/camtrapdp/summary", params={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["hfh_repo_id"] == "alice/dataset"


def test_summary_reports_no_hfh_repo_id_when_homepage_points_elsewhere(tmp_path):
    _write_metadata_json(tmp_path, title="My Camtrap DP", homepage="https://wildintel-trap.uhu.es/")

    response = _client().get("/api/camtrapdp/summary", params={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["hfh_repo_id"] is None


def test_summary_reports_no_hfh_repo_id_when_homepage_missing(tmp_path):
    """Link mode never sets homepage — the media doesn't actually live in
    this HFH repo, so there's nothing reliable to detect."""
    _write_metadata_json(tmp_path, title="My Camtrap DP")

    response = _client().get("/api/camtrapdp/summary", params={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["hfh_repo_id"] is None


def test_download_returns_404_when_datapackage_missing(tmp_path):
    response = _client().get("/api/camtrapdp/download", params={"path": str(tmp_path)})
    assert response.status_code == 404


def test_download_serves_the_file(tmp_path):
    _write_datapackage(tmp_path, title="My Camtrap DP")

    response = _client().get("/api/camtrapdp/download", params={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json() == {"title": "My Camtrap DP"}
    assert "datapackage.json" in response.headers["content-disposition"]


def test_open_folder_returns_404_when_directory_missing(tmp_path):
    response = _client().post("/api/camtrapdp/open-folder", json={"path": str(tmp_path / "missing")})
    assert response.status_code == 404


def test_open_folder_opens_the_directory(tmp_path):
    with patch("services.camtrapdp_service.subprocess.Popen") as mock_popen:
        response = _client().post("/api/camtrapdp/open-folder", json={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_popen.assert_called_once()
    assert str(tmp_path) in mock_popen.call_args.args[0]
