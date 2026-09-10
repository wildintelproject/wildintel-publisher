"""Unit tests for wildintel_publisher.config (Settings/TrapperSettings/etc)."""
from pathlib import Path

from wildintel_publisher.config import (
    B2ShareSettings,
    CamtrapdpOrganization,
    GBIFInstallation,
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
    assert settings.TRAPPER.license_id == "CC-BY-NC-4.0"


def test_load_settings_round_trips_a_saved_value(tmp_path: Path):
    from dynaconf import loaders

    config_file = tmp_path / "settings.toml"
    settings = load_settings(config_file)
    settings.TRAPPER.project_id = 42
    loaders.toml_loader.write(str(config_file), settings.model_dump(mode="json"), merge=False)

    reloaded = load_settings(config_file)
    assert reloaded.TRAPPER.project_id == 42


def test_camtrapdp_organizations_default_list_has_no_email_set(tmp_path: Path):
    settings = load_settings(tmp_path / "settings.toml")

    assert settings.CAMTRAPDP.organizations[0].title == "Institute of Nature Conservation PAS"
    # None of the default entries carries an email (only the publisher role
    # ever reads one — see services.common.resolve_publisher) — a
    # deployment that wants one set for its own default publisher hand-edits
    # settings.toml's own [[CAMTRAPDP.organizations]] entry for it.
    assert all(o.email is None for o in settings.CAMTRAPDP.organizations)


def test_camtrapdp_organizations_round_trips_a_hand_edited_list(tmp_path: Path):
    """The whole point of moving this out of WizardPage.tsx: settings.toml
    is hand-editable — add/remove an [[CAMTRAPDP.organizations]] entry with
    no frontend code change."""
    from dynaconf import loaders

    config_file = tmp_path / "settings.toml"
    settings = load_settings(config_file)
    settings.CAMTRAPDP.organizations.append(
        CamtrapdpOrganization(title="A New Partner Institution", path="https://example.org/", email=None)
    )
    loaders.toml_loader.write(str(config_file), settings.model_dump(mode="json"), merge=False)

    reloaded = load_settings(config_file)
    titles = [o.title for o in reloaded.CAMTRAPDP.organizations]
    assert "A New Partner Institution" in titles


def test_camtrapdp_organization_gbif_keys_default_unset_and_round_trip_independently(tmp_path: Path):
    """Sandbox and production are separate GBIF Registry systems, each with
    its own UUID for the same real-world organization — never derived from
    one another, and each independently optional (an org may have neither,
    either, or both set)."""
    from dynaconf import loaders

    settings = load_settings(tmp_path / "settings.toml")
    # "Institute of Nature Conservation PAS" and "University of Huelva" ship
    # with real GBIF keys by default — every OTHER default organization has
    # neither set.
    orgs_with_real_keys = {
        "Institute of Nature Conservation PAS", "University of Huelva", "University of South-Eastern Norway",
        "German Centre for Integrative Biodiversity Research",
    }
    assert all(
        o.gbif_sandbox_organization_key is None and o.gbif_production_organization_key is None
        for o in settings.CAMTRAPDP.organizations if o.title not in orgs_with_real_keys
    )

    config_file = tmp_path / "settings2.toml"
    settings = load_settings(config_file)
    settings.CAMTRAPDP.organizations[0].gbif_sandbox_organization_key = "sandbox-uuid-1"
    settings.CAMTRAPDP.organizations[0].gbif_production_organization_key = "prod-uuid-1"
    loaders.toml_loader.write(str(config_file), settings.model_dump(mode="json"), merge=False)

    reloaded = load_settings(config_file)
    assert reloaded.CAMTRAPDP.organizations[0].gbif_sandbox_organization_key == "sandbox-uuid-1"
    assert reloaded.CAMTRAPDP.organizations[0].gbif_production_organization_key == "prod-uuid-1"


def test_camtrapdp_institute_of_nature_conservation_ships_with_its_real_gbif_keys(tmp_path: Path):
    """Same UUID in both environments for this organization — confirmed by
    the user, not a copy-paste artifact (see GBIFInstallation's own
    docstring for why sandbox/production are normally independent)."""
    settings = load_settings(tmp_path / "settings.toml")

    institute = next(o for o in settings.CAMTRAPDP.organizations if o.title == "Institute of Nature Conservation PAS")
    assert institute.gbif_sandbox_organization_key == "f121e450-78ba-11d8-a19c-b8a03c50a862"
    assert institute.gbif_production_organization_key == "f121e450-78ba-11d8-a19c-b8a03c50a862"


def test_camtrapdp_university_of_huelva_ships_with_its_real_gbif_production_key(tmp_path: Path):
    settings = load_settings(tmp_path / "settings.toml")

    uhu = next(o for o in settings.CAMTRAPDP.organizations if o.title == "University of Huelva")
    assert uhu.gbif_sandbox_organization_key is None
    assert uhu.gbif_production_organization_key == "37ec4ca1-fb42-4e11-939e-dafa4aa78e9e"


def test_camtrapdp_university_of_south_eastern_norway_ships_with_its_real_gbif_production_key(tmp_path: Path):
    settings = load_settings(tmp_path / "settings.toml")

    usn = next(o for o in settings.CAMTRAPDP.organizations if o.title == "University of South-Eastern Norway")
    assert usn.gbif_sandbox_organization_key is None
    assert usn.gbif_production_organization_key == "7f3b33d6-3864-4fd7-b6be-e4cbeba014b1"


def test_camtrapdp_german_centre_for_integrative_biodiversity_research_ships_with_its_real_gbif_keys(
    tmp_path: Path,
):
    """Same UUID in both environments for this organization — confirmed by
    the user, not a copy-paste artifact (mirrors the Polish institute's own
    entry — see GBIFInstallation's own docstring for why sandbox/production
    are normally independent)."""
    settings = load_settings(tmp_path / "settings.toml")

    idiv = next(
        o for o in settings.CAMTRAPDP.organizations
        if o.title == "German Centre for Integrative Biodiversity Research"
    )
    assert idiv.gbif_sandbox_organization_key == "b48dbd22-0452-4c31-a6b5-28f04e99d8cf"
    assert idiv.gbif_production_organization_key == "b48dbd22-0452-4c31-a6b5-28f04e99d8cf"


def test_gbif_installations_default_includes_wildintel_with_its_sandbox_key(tmp_path: Path):
    settings = load_settings(tmp_path / "settings.toml")

    assert len(settings.GBIF.installations) == 1
    wildintel = settings.GBIF.installations[0]
    assert wildintel.title == "WildINTEL"
    assert wildintel.sandbox_installation_key == "9970e64a-f762-11e1-a439-00145eb45e9a"
    assert wildintel.production_installation_key is None


def test_gbif_installations_round_trips_a_hand_edited_list(tmp_path: Path):
    from dynaconf import loaders

    config_file = tmp_path / "settings.toml"
    settings = load_settings(config_file)
    settings.GBIF.installations.append(
        GBIFInstallation(title="Another Installation", production_installation_key="prod-uuid-2")
    )
    loaders.toml_loader.write(str(config_file), settings.model_dump(mode="json"), merge=False)

    reloaded = load_settings(config_file)
    titles = [i.title for i in reloaded.GBIF.installations]
    assert "Another Installation" in titles
    another = next(i for i in reloaded.GBIF.installations if i.title == "Another Installation")
    assert another.production_installation_key == "prod-uuid-2"
    assert another.sandbox_installation_key is None
