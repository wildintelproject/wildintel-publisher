"""Unit tests for the /api/camtrapdp/* endpoints — reading/serving an
already-obtained product directory via its generic metadata.json."""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
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
    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["product_type"] == "camtrapdp"
    assert body["title"] == "My Camtrap DP"
    assert body["publish_history"] == []
    assert (tmp_path / "metadata.json").is_file()


def test_generate_metadata_flips_the_session_to_preprocessed_when_given(tmp_path):
    from wildintel_publisher.web.services import session_store

    task_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="archive",
        fetch={"source_type": "archive", "params": {"url": "https://example.org/x.zip", "clear_cache": False}, "output_dir": str(tmp_path), "input_dir": str(tmp_path)},
        status="done", error=None,
    )
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp", "session_task_id": task_id,
            "randomize_media_ids": True, "media_id_domain": "example.org",
        })

    assert response.status_code == 200
    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "preprocessed"
    assert manifest["preprocessing"] == {
        "status": "done", "anonymize_coordinates": False, "coordinate_decimals": 2,
        "randomize_media_ids": True, "media_id_domain": "example.org",
    }
    # The fetch section this session started with survives untouched.
    assert manifest["fetch"]["params"]["url"] == "https://example.org/x.zip"


def test_generate_metadata_flips_the_session_to_error_on_failure(tmp_path):
    from wildintel_publisher.web.services import session_store

    task_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="archive",
        fetch={"source_type": "archive", "params": {"url": "https://example.org/x.zip", "clear_cache": False}, "output_dir": str(tmp_path), "input_dir": str(tmp_path)},
        status="done", error=None,
    )
    # No datapackage.json at all — generate_metadata will fail validation.

    response = _client().post("/api/camtrapdp/generate-metadata", json={
        "input_dir": str(tmp_path), "product_type": "camtrapdp", "session_task_id": task_id,
    })

    assert response.status_code == 400
    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "preprocessing"
    assert manifest["status"] == "error"
    assert manifest["error"]


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

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
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

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    assert "41.123456" in (tmp_path / "deployments.csv").read_text(encoding="utf-8")


def test_generate_metadata_randomizes_media_ids_when_requested(tmp_path):
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )
    (tmp_path / "media.csv").write_text("mediaID,fileName\nimg001,img001.jpg\n", encoding="utf-8")

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
            "randomize_media_ids": True,
        })

    assert response.status_code == 200
    assert "mediaID,fileName\nimg001,img001.jpg\n" not in (tmp_path / "media.csv").read_text(encoding="utf-8")
    assert ",img001.jpg" in (tmp_path / "media.csv").read_text(encoding="utf-8")  # fileName is untouched


def test_generate_metadata_derives_media_ids_from_the_given_domain(tmp_path):
    import uuid
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )
    (tmp_path / "media.csv").write_text("mediaID,fileName\nimg001,img001.jpg\n", encoding="utf-8")

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
            "randomize_media_ids": True, "media_id_domain": "trapper.example",
        })

    assert response.status_code == 200
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "trapper.example:img001"))
    assert expected_id in (tmp_path / "media.csv").read_text(encoding="utf-8")


def test_generate_metadata_leaves_media_ids_untouched_by_default(tmp_path):
    _write_datapackage(
        tmp_path,
        title="My Camtrap DP", description="A test package.", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )
    (tmp_path / "media.csv").write_text("mediaID,fileName\nimg001,img001.jpg\n", encoding="utf-8")

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    assert "img001" in (tmp_path / "media.csv").read_text(encoding="utf-8")


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

    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        response = _client().post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["title"] is None
    # Never null: CamtrapDPAdapter.extract_metadata always appends its own
    # WildINTEL attribution paragraph, even with no description of its own.
    assert body["description"] == "Camtrap DP camera-trap dataset, published via the WildINTEL project. https://wildintel.eu/"
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


def test_datapackage_fields_reads_straight_from_datapackage_json(tmp_path):
    _write_datapackage(
        tmp_path, name="my-dataset", title="My Camtrap DP", description="D", version="1.0",
        homepage="https://example.org", resources=[{"name": "media", "path": "media.csv"}],
    )

    response = _client().get(f"/api/camtrapdp/datapackage-fields?path={tmp_path}")

    assert response.status_code == 200
    assert response.json() == {
        "name": "my-dataset", "title": "My Camtrap DP", "description": "D", "version": "1.0",
        "homepage": "https://example.org", "contributors": [],
    }


def test_datapackage_fields_returns_the_full_contributors_array_unfiltered(tmp_path):
    _write_datapackage(tmp_path, contributors=[
        {"title": "Alice", "email": "alice@example.org", "organization": "Test Org", "role": "principalInvestigator"},
        {"title": "Bob", "role": "contributor"},
    ])

    response = _client().get(f"/api/camtrapdp/datapackage-fields?path={tmp_path}")

    assert response.status_code == 200
    assert response.json()["contributors"] == [
        {"title": "Alice", "email": "alice@example.org", "organization": "Test Org", "role": "principalInvestigator"},
        {"title": "Bob", "role": "contributor"},
    ]


def test_datapackage_fields_works_before_any_metadata_json_exists(tmp_path):
    # No metadata.json written at all — unlike /summary, this doesn't need
    # generate-metadata to have run first.
    _write_datapackage(tmp_path, title="Raw Title")

    response = _client().get(f"/api/camtrapdp/datapackage-fields?path={tmp_path}")

    assert response.status_code == 200
    assert response.json()["title"] == "Raw Title"
    assert not (tmp_path / "metadata.json").exists()


def test_update_datapackage_can_change_just_a_contributors_role(tmp_path):
    # The wizard's "change role only" editor reads the full contributors
    # array, edits one entry's role client-side, and sends the whole array
    # back — everything else about each contributor must survive untouched.
    _write_datapackage(
        tmp_path, name="old-name", title="Old Title", contributors=[
            {"title": "Alice", "email": "alice@example.org", "organization": "Test Org", "role": "principalInvestigator"},
            {"title": "Bob", "role": "contributor"},
        ],
    )

    response = _client().post("/api/camtrapdp/update-datapackage", json={
        "input_dir": str(tmp_path),
        "contributors": [
            {"title": "Alice", "email": "alice@example.org", "organization": "Test Org", "role": "contact"},
            {"title": "Bob", "role": "contributor"},
        ],
    })

    assert response.status_code == 200
    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["contributors"] == [
        {"title": "Alice", "email": "alice@example.org", "organization": "Test Org", "role": "contact"},
        {"title": "Bob", "role": "contributor"},
    ]
    # Untouched top-level fields survive.
    assert data["name"] == "old-name"
    assert data["title"] == "Old Title"


def test_update_datapackage_patches_only_the_given_fields(tmp_path):
    _write_datapackage(
        tmp_path, name="old-name", title="Old Title", description="Old", version="1.0",
        resources=[{"name": "media", "path": "media.csv"}],
    )

    response = _client().post("/api/camtrapdp/update-datapackage", json={
        "input_dir": str(tmp_path), "title": "New Title", "version": "2.0",
    })

    assert response.status_code == 200
    data = json.loads((tmp_path / "datapackage.json").read_text(encoding="utf-8"))
    assert data["title"] == "New Title"
    assert data["version"] == "2.0"
    assert data["name"] == "old-name"  # untouched fields survive
    assert data["resources"] == [{"name": "media", "path": "media.csv"}]


def test_update_datapackage_then_generate_metadata_reflects_the_patched_fields(tmp_path):
    """The actual point of editing datapackage.json before generate-metadata
    runs: metadata.json (and everything generated from it) picks up the new
    title with no separate write of its own — see
    services.common.update_datapackage_fields's docstring."""
    _write_datapackage(
        tmp_path, title="Old Title", description="D", version="1.0",
        licenses=[{"name": "CC-BY-4.0", "title": "CC BY 4.0"}],
        contributors=[{"title": "Alice", "organization": "Test Org"}],
    )
    (tmp_path / "media.csv").write_text("mediaID,fileName\n", encoding="utf-8")

    client = _client()
    with patch("wildintel_publisher.core.services.common.validate_camtrap_dp", return_value=None):
        client.post("/api/camtrapdp/update-datapackage", json={
            "input_dir": str(tmp_path), "title": "Edited via the new screen",
        })
        response = client.post("/api/camtrapdp/generate-metadata", json={
            "input_dir": str(tmp_path), "product_type": "camtrapdp",
        })

    assert response.status_code == 200
    assert response.json()["title"] == "Edited via the new screen"


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


def test_organizations_returns_the_configured_list():
    response = _client().get("/api/product/organizations")

    assert response.status_code == 200
    titles = [org["title"] for org in response.json()]
    assert "Institute of Nature Conservation PAS" in titles
    institute = next(org for org in response.json() if org["title"] == "Institute of Nature Conservation PAS")
    assert institute["path"] == "https://www.iop.krakow.pl/"


def test_authors_returns_the_configured_list():
    response = _client().get("/api/product/authors")

    assert response.status_code == 200
    names = [author["name"] for author in response.json()]
    assert "Iñaki Fernández de Viana" in names
    assert all("affiliation" in author for author in response.json())


def test_open_folder_returns_404_when_directory_missing(tmp_path):
    response = _client().post("/api/camtrapdp/open-folder", json={"path": str(tmp_path / "missing")})
    assert response.status_code == 404


def test_open_folder_opens_the_directory(tmp_path):
    with patch("wildintel_publisher.web.services.camtrapdp_service.subprocess.Popen") as mock_popen:
        response = _client().post("/api/camtrapdp/open-folder", json={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_popen.assert_called_once()
    assert str(tmp_path) in mock_popen.call_args.args[0]
