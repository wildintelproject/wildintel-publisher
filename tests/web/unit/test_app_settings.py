"""Unit tests for GET/PUT /api/settings — settings.toml edited on the web
app's settings page (see api.routers.app_settings)."""
import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Each test starts from the default settings.toml — they all save."""
    from dynaconf import loaders
    from wildintel_publisher.core.config import DEFAULT_CONFIG_FILE, Settings
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), Settings().model_dump(mode="json"), merge=False)


def test_defaults_never_show_a_secret_value():
    data = _client().get("/api/settings").json()
    assert data["TRAPPER"]["has_user_name"] is False
    assert data["TRAPPER"]["has_user_password"] is False
    assert "user_name" not in data["TRAPPER"] and "user_password" not in data["TRAPPER"]
    assert data["HFH"]["has_token"] is False and "token" not in data["HFH"]
    assert data["ZENODO"]["has_token"] is False and "token" not in data["ZENODO"]
    assert data["B2SHARE"]["has_token"] is False and "token" not in data["B2SHARE"]
    assert data["GBIF"]["has_username"] is False and "username" not in data["GBIF"]
    assert data["GBIF"]["has_password"] is False and "password" not in data["GBIF"]
    # Non-secret fields keep their real value.
    assert data["CAMTRAPDP"]["license_id"] == "CC-BY-NC-4.0"
    assert data["GENERAL"]["log_level"] == "INFO"
    assert len(data["PRODUCT"]["organizations"]) > 0
    assert len(data["GBIF"]["installations"]) > 0


def test_saving_a_secret_shows_it_saved_but_never_its_value():
    client = _client()
    current = client.get("/api/settings").json()
    current["TRAPPER"]["user_name"] = "alice"
    current["TRAPPER"]["user_password"] = "s3cret"

    saved = client.put("/api/settings", json=current).json()
    assert saved["TRAPPER"]["has_user_name"] is True
    assert saved["TRAPPER"]["has_user_password"] is True
    assert "user_name" not in saved["TRAPPER"] and "user_password" not in saved["TRAPPER"]


def test_saving_a_blank_secret_keeps_the_one_already_saved():
    client = _client()
    current = client.get("/api/settings").json()
    current["HFH"]["token"] = "hf_abc123"
    client.put("/api/settings", json=current)

    again = client.get("/api/settings").json()
    again["HFH"]["token"] = ""
    saved = client.put("/api/settings", json=again).json()
    assert saved["HFH"]["has_token"] is True


def test_saving_replaces_non_secret_fields_including_lists():
    client = _client()
    current = client.get("/api/settings").json()
    current["TRAPPER"]["base_url"] = "https://trapper.example.org"
    current["PRODUCT"]["organizations"] = [{"title": "New Org", "path": None, "email": None,
                                             "gbif_sandbox_organization_key": None, "gbif_production_organization_key": None}]
    current["GBIF"]["installations"] = [{"title": "My install", "sandbox_installation_key": None,
                                         "production_installation_key": "abc-123"}]

    saved = client.put("/api/settings", json=current).json()
    assert saved["TRAPPER"]["base_url"] == "https://trapper.example.org"
    assert [o["title"] for o in saved["PRODUCT"]["organizations"]] == ["New Org"]
    assert [i["title"] for i in saved["GBIF"]["installations"]] == ["My install"]


def test_s3_remotes_keep_their_secrets_server_side_and_blank_keeps_the_saved_one():
    client = _client()
    current = client.get("/api/settings").json()
    [remote] = current["S3"]["remotes"]
    assert remote["has_access_key"] is False and "access_key" not in remote

    remote["access_key"], remote["secret_key"] = "AK", "SK"
    saved = client.put("/api/settings", json=current).json()
    [remote] = saved["S3"]["remotes"]
    assert remote["has_access_key"] is True and remote["has_secret_key"] is True
    assert "access_key" not in remote and "secret_key" not in remote

    # Renamed, keys left blank: still matched by id.
    remote["name"] = "Renamed"
    again = client.put("/api/settings", json=saved).json()
    [remote] = again["S3"]["remotes"]
    assert remote["name"] == "Renamed" and remote["has_secret_key"] is True


def test_s3_remotes_can_be_added_and_removed():
    client = _client()
    current = client.get("/api/settings").json()
    current["S3"]["remotes"].append({"id": "second", "name": "Second", "bucket": "b", "verify_ssl": True})
    assert [r["name"] for r in client.put("/api/settings", json=current).json()["S3"]["remotes"]] == ["WildINTEL", "Second"]

    current["S3"]["remotes"] = []
    assert client.put("/api/settings", json=current).json()["S3"]["remotes"] == []


def test_a_legacy_single_connection_s3_section_becomes_the_first_remote():
    from wildintel_publisher.core.config import Settings

    settings = Settings.model_validate({"S3": {"bucket": "old", "access_key": "AK", "retry_attempts": 5}})
    [remote] = settings.S3.remotes
    assert (remote.id, remote.bucket, remote.access_key) == ("default", "old", "AK")
    assert settings.S3.retry_attempts == 5
