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
    for env in ("sandbox", "production"):
        assert data["ZENODO"][f"has_{env}_token"] is False and f"{env}_token" not in data["ZENODO"]
        assert data["B2SHARE"][f"has_{env}_token"] is False and f"{env}_token" not in data["B2SHARE"]
        assert data["GBIF"][f"has_{env}_username"] is False and f"{env}_username" not in data["GBIF"]
        assert data["GBIF"][f"has_{env}_password"] is False and f"{env}_password" not in data["GBIF"]
    # Non-secret fields keep their real value.
    assert data["CAMTRAPDP"]["license_id"] == "CC-BY-NC-4.0"
    assert data["GENERAL"]["log_level"] == "INFO"
    assert len(data["PRODUCT"]["organizations"]) > 0
    assert len(data["PRODUCT"]["authors"]) > 0
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


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Points the config files (default, extra ones, active pointer) at a temp dir."""
    from dynaconf import loaders
    from wildintel_publisher.core import config
    from wildintel_publisher.core.config import Settings

    monkeypatch.setattr(config, "DEFAULT_CONFIG_FILE", tmp_path / "settings.toml")
    monkeypatch.setattr(config, "CONFIGS_DIR", tmp_path / "configs")
    monkeypatch.setattr(config, "ACTIVE_CONFIG_POINTER", tmp_path / "active-config")
    loaders.toml_loader.write(str(tmp_path / "settings.toml"), Settings().model_dump(mode="json"), merge=False)
    return tmp_path


def test_lists_the_default_config_as_the_active_one(config_dir):
    client = _client()

    assert client.get("/api/settings/configs").json() == [
        {"id": "default", "name": "Default config", "path": str(config_dir / "settings.toml"), "active": True},
    ]
    assert client.get("/api/settings").json()["GENERAL"]["config_file"] == str(config_dir / "settings.toml")


def test_a_new_config_has_the_default_values_and_is_not_activated(config_dir):
    client = _client()
    client.put("/api/settings", json={**client.get("/api/settings").json(), "GENERAL": {"log_level": "DEBUG"}})

    configs = client.post("/api/settings/configs", json={"name": "Project B"}).json()

    assert [(c["id"], c["active"]) for c in configs] == [("default", True), ("project-b", False)]
    assert (config_dir / "configs" / "project-b.toml").is_file()
    # the default config keeps its own edits; the new one starts from defaults
    assert client.get("/api/settings").json()["GENERAL"]["log_level"] == "DEBUG"
    client.post("/api/settings/configs/project-b/activate")
    assert client.get("/api/settings").json()["GENERAL"]["log_level"] == "INFO"


def test_saving_goes_to_the_active_config_only(config_dir):
    client = _client()
    client.post("/api/settings/configs", json={"name": "B"})
    client.post("/api/settings/configs/b/activate")

    client.put("/api/settings", json={**client.get("/api/settings").json(), "GENERAL": {"log_level": "ERROR"}})

    assert 'log_level = "ERROR"' in (config_dir / "configs" / "b.toml").read_text(encoding="utf-8")
    assert 'log_level = "ERROR"' not in (config_dir / "settings.toml").read_text(encoding="utf-8")
    assert client.get("/api/settings").json()["GENERAL"]["config_file"] == str(config_dir / "configs" / "b.toml")


def test_two_configs_with_the_same_name_get_different_ids(config_dir):
    client = _client()
    client.post("/api/settings/configs", json={"name": "Same"})
    configs = client.post("/api/settings/configs", json={"name": "Same"}).json()

    assert [c["id"] for c in configs] == ["default", "same", "same-2"]


def test_a_config_needs_a_usable_name_and_an_existing_id_to_activate(config_dir):
    client = _client()

    assert client.post("/api/settings/configs", json={"name": "  !! "}).status_code == 400
    assert client.post("/api/settings/configs/nope/activate").status_code == 404
    assert client.get("/api/settings/configs/nope/download").status_code == 404


def test_a_missing_active_config_falls_back_to_the_default_one(config_dir):
    client = _client()
    client.post("/api/settings/configs", json={"name": "B"})
    client.post("/api/settings/configs/b/activate")
    (config_dir / "configs" / "b.toml").unlink()

    assert [(c["id"], c["active"]) for c in client.get("/api/settings/configs").json()] == [("default", True)]


def test_a_config_can_be_downloaded_and_its_folder_opened(config_dir, monkeypatch):
    from wildintel_publisher.web.services import camtrapdp_service

    client = _client()
    client.post("/api/settings/configs", json={"name": "B"})

    response = client.get("/api/settings/configs/b/download")
    assert response.status_code == 200
    assert "b.toml" in response.headers["content-disposition"]
    assert response.text == (config_dir / "configs" / "b.toml").read_text(encoding="utf-8")

    opened = []
    monkeypatch.setattr(camtrapdp_service, "open_folder", opened.append)
    assert client.post("/api/settings/configs/default/open-folder").json() == {"ok": True}
    assert client.post("/api/settings/configs/b/open-folder").json() == {"ok": True}
    assert opened == [config_dir, config_dir / "configs"]
