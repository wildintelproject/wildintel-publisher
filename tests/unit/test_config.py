"""Unit tests for wildintel_publisher.config (Settings/TrapperSettings/etc)."""
from pathlib import Path

from wildintel_publisher.config import (
    B2ShareSettings,
    HFHSettings,
    Settings,
    TrapperSettings,
    ZenodoSettings,
    _slug_to_dataset_name,
    get_b2share_output_dir,
    get_hfh_output_dir,
    get_trapper_output_dir,
    get_zenodo_output_dir,
    load_settings,
)


def test_slug_to_dataset_name_title_cases_and_replaces_separators():
    assert _slug_to_dataset_name("wildintel-camtrapdp") == "Wildintel Camtrapdp"
    assert _slug_to_dataset_name("some_slug_name") == "Some Slug Name"


def test_trapper_settings_derives_dataset_name_from_slug_when_unset():
    settings = TrapperSettings(dataset_slug="my-dataset")
    assert settings.dataset_name == "My Dataset"


def test_trapper_settings_keeps_explicit_dataset_name():
    settings = TrapperSettings(dataset_slug="my-dataset", dataset_name="Custom Title")
    assert settings.dataset_name == "Custom Title"


def test_trapper_settings_secret_fields_are_marked():
    assert TrapperSettings.model_fields["user_name"].json_schema_extra == {"secret": True}
    assert TrapperSettings.model_fields["user_password"].json_schema_extra == {"secret": True}
    assert TrapperSettings.model_fields["base_url"].json_schema_extra is None


def test_hfh_settings_token_is_marked_secret():
    assert HFHSettings.model_fields["token"].json_schema_extra == {"secret": True}


def test_zenodo_settings_defaults():
    settings = ZenodoSettings()
    assert settings.environment == "sandbox"
    assert settings.communities is None
    assert settings.token is None


def test_b2share_settings_defaults():
    settings = B2ShareSettings()
    assert settings.environment == "sandbox"
    assert settings.community_id is None


def test_settings_has_all_four_sections():
    settings = Settings()
    assert isinstance(settings.TRAPPER, TrapperSettings)
    assert isinstance(settings.HFH, HFHSettings)
    assert isinstance(settings.ZENODO, ZenodoSettings)
    assert isinstance(settings.B2SHARE, B2ShareSettings)


def test_output_dir_helpers_are_distinct_siblings():
    dirs = {get_trapper_output_dir(), get_hfh_output_dir(), get_zenodo_output_dir(), get_b2share_output_dir()}
    assert len(dirs) == 4
    parents = {d.parent for d in dirs}
    assert len(parents) == 1  # all siblings under the same app documents dir


def test_load_settings_creates_file_with_defaults_if_missing(tmp_path: Path):
    config_file = tmp_path / "settings.toml"
    assert not config_file.exists()

    settings = load_settings(config_file)

    assert config_file.is_file()
    assert settings.TRAPPER.license_id == "CC-BY-4.0"


def test_load_settings_round_trips_a_saved_value(tmp_path: Path):
    from dynaconf import loaders

    config_file = tmp_path / "settings.toml"
    settings = load_settings(config_file)
    settings.TRAPPER.project_id = 42
    loaders.toml_loader.write(str(config_file), settings.model_dump(mode="json"), merge=False)

    reloaded = load_settings(config_file)
    assert reloaded.TRAPPER.project_id == 42
