"""Integration tests for '<section> config show/get/set/wizard' across the
TRAPPER, HFH, ZENODO and B2SHARE sections (commands/config_commands.py's
generic engine, shared by all four)."""
import pytest
from typer.testing import CliRunner

from wildintel_publisher.config import DEFAULT_CONFIG_FILE, load_settings
from wildintel_publisher.main import app

runner = CliRunner()

# Field counts (in model declaration order) — see config.py.
TRAPPER_FIELD_COUNT = 10
HFH_FIELD_COUNT = 5
ZENODO_FIELD_COUNT = 3
B2SHARE_FIELD_COUNT = 3


@pytest.fixture(autouse=True)
def _restore_config_file():
    """Snapshot settings.toml before each test and restore it after — all
    four config groups read/write the same single app-wide settings file, so
    tests that call 'config set'/'config wizard' must not leak state."""
    load_settings()  # make sure it exists before snapshotting
    original = DEFAULT_CONFIG_FILE.read_text(encoding="utf-8")
    yield
    DEFAULT_CONFIG_FILE.write_text(original, encoding="utf-8")


# ── show/get/set — parametrized across the 4 sections ────────────────────────

@pytest.mark.parametrize("group", ["trapper", "hfh", "zenodo", "b2share"])
def test_config_show_prints_file_path_and_section_header(group):
    result = runner.invoke(app, [group, "config", "show"])
    assert result.exit_code == 0
    # Rich wraps long lines (the config file's absolute path) at the console's
    # width, which CliRunner reports as narrow — strip hard line breaks before
    # checking substrings that might straddle a wrap point.
    unwrapped_output = result.output.replace("\n", "")
    assert str(DEFAULT_CONFIG_FILE) in unwrapped_output
    assert f"[{group.upper()}]" in unwrapped_output


def test_trapper_config_get_returns_scalar_value():
    result = runner.invoke(app, ["trapper", "config", "get", "license_id"])
    assert result.exit_code == 0
    assert result.output.strip() == "CC-BY-4.0"


def test_config_get_unknown_field_errors():
    result = runner.invoke(app, ["trapper", "config", "get", "bogus_field"])
    assert result.exit_code != 0
    assert "Unknown field" in result.output


def test_trapper_config_set_scalar_value_persists():
    set_result = runner.invoke(app, ["trapper", "config", "set", "dataset_slug=my-new-slug"])
    assert set_result.exit_code == 0

    get_result = runner.invoke(app, ["trapper", "config", "get", "dataset_slug"])
    assert get_result.output.strip() == "my-new-slug"


def test_trapper_config_set_int_value_persists():
    set_result = runner.invoke(app, ["trapper", "config", "set", "project_id=7"])
    assert set_result.exit_code == 0

    get_result = runner.invoke(app, ["trapper", "config", "get", "project_id"])
    assert get_result.output.strip() == "7"


def test_config_set_invalid_value_rejected_and_not_persisted():
    result = runner.invoke(app, ["trapper", "config", "set", "project_id=not-a-number"])
    assert result.exit_code == 1
    assert "Invalid value" in result.output

    get_result = runner.invoke(app, ["trapper", "config", "get", "project_id"])
    assert get_result.output.strip() == "None"


def test_config_set_missing_equals_sign_errors_for_non_secret_field():
    result = runner.invoke(app, ["trapper", "config", "set", "dataset_slug"])
    assert result.exit_code != 0
    assert "Expected format: FIELD=VALUE" in result.output


def test_config_set_unknown_field_errors():
    result = runner.invoke(app, ["trapper", "config", "set", "bogus_field=1"])
    assert result.exit_code != 0
    assert "Unknown field" in result.output


def test_config_set_secret_field_prompts_with_hidden_input():
    result = runner.invoke(app, ["hfh", "config", "set", "token"], input="hf_abc123\n")
    assert result.exit_code == 0
    assert "hf_abc123" not in result.output  # never echoed in plain text

    show_result = runner.invoke(app, ["hfh", "config", "show"])
    assert "••••••••" in show_result.output  # masked
    assert "hf_abc123" not in show_result.output


def test_config_get_does_not_leak_a_different_sections_field():
    result = runner.invoke(app, ["hfh", "config", "get", "license_id"])  # license_id belongs to TRAPPER, not HFH
    assert result.exit_code != 0
    assert "Unknown field" in result.output


# ── wizard — one representative test per section (blank keeps defaults) ─────

def _blank_wizard_input(field_count: int) -> str:
    return "y\n" + "\n" * field_count  # "y" answers the initial "Continue?"


@pytest.mark.parametrize("group,field_count", [
    ("trapper", TRAPPER_FIELD_COUNT), ("hfh", HFH_FIELD_COUNT),
    ("zenodo", ZENODO_FIELD_COUNT), ("b2share", B2SHARE_FIELD_COUNT),
])
def test_config_wizard_keeps_defaults_when_all_answers_blank(group, field_count):
    result = runner.invoke(app, [group, "config", "wizard"], input=_blank_wizard_input(field_count))
    assert result.exit_code == 0, result.output
    assert "No value was changed" in result.output


def test_config_wizard_cancelled_at_initial_prompt_changes_nothing():
    result = runner.invoke(app, ["trapper", "config", "wizard"], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output


def test_trapper_config_wizard_saves_a_changed_value():
    # blank through the first 8 fields (base_url..license_url), change dataset_slug (9th), blank
    # the last (description), then confirm save.
    answers = "y\n" + "\n" * 7 + "my-wizard-slug\n" + "\n" * 2 + "y\n"

    result = runner.invoke(app, ["trapper", "config", "wizard"], input=answers)

    assert result.exit_code == 0, result.output
    assert "dataset_slug" in result.output

    get_result = runner.invoke(app, ["trapper", "config", "get", "dataset_slug"])
    assert get_result.output.strip() == "my-wizard-slug"


def test_config_wizard_retries_after_invalid_value_and_cancel_does_not_persist():
    # project_id is TRAPPER's 4th field (index 3): base_url, user_name, user_password, project_id.
    answers = "y\n" + "\n" * 3 + "not-a-number\n" + "42\n" + "\n" * 6 + "n\n"

    result = runner.invoke(app, ["trapper", "config", "wizard"], input=answers)

    assert result.exit_code == 0, result.output
    assert "Invalid value" in result.output
    assert "Cancelled" in result.output

    get_result = runner.invoke(app, ["trapper", "config", "get", "project_id"])
    assert get_result.output.strip() == "None"
