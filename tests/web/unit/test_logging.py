"""logging_setup, and the settings page's General section / log download."""
import logging

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    from wildintel_publisher.web.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    from wildintel_publisher.core import config, logging_setup

    monkeypatch.delenv("WILDINTEL_PUBLISHER_LOG_LEVEL", raising=False)
    # The CLI suites (same pytest process) leave the app's own handlers on
    # the root logger, the console one bound to a CliRunner stream that's
    # closed by now — start from none, so configure() makes fresh ones.
    root = logging.getLogger()
    for handler in [h for h in root.handlers if logging_setup._ours(h)]:
        root.removeHandler(handler)
    config.save_settings(config.Settings())
    root_level = logging.getLogger().level
    yield
    config.save_settings(config.Settings())
    logging.getLogger().setLevel(root_level)


def _flush():
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_the_log_goes_to_a_file_next_to_settings_toml():
    from wildintel_publisher.core import config, logging_setup

    logging_setup.configure()
    logging.getLogger("wildintel_publisher.web.services.test").warning("something to find later")
    _flush()

    assert logging_setup.log_file() == config.get_logs_dir() / "wildintel-publisher.log"
    assert config.get_logs_dir().parent == config.DEFAULT_CONFIG_FILE.parent
    assert "something to find later" in logging_setup.log_file().read_text(encoding="utf-8")


def test_configuring_twice_doesnt_log_twice():
    from wildintel_publisher.core import logging_setup

    logging_setup.configure()
    logging_setup.configure()
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_wildintel_publisher", False)]
    assert len(ours) == 2  # console + file


def test_saving_the_settings_changes_the_level_on_the_fly():
    from wildintel_publisher.core import logging_setup

    logging_setup.configure()
    assert logging.getLogger().level == logging.INFO

    settings = _client().get("/api/settings").json()
    settings["GENERAL"]["log_level"] = "DEBUG"
    assert _client().put("/api/settings", json=settings).status_code == 200
    assert logging.getLogger().level == logging.DEBUG
    # The libraries' byte-level chatter stays at INFO.
    assert logging.getLogger("botocore").level == logging.INFO

    settings["GENERAL"]["log_level"] = "WARNING"
    _client().put("/api/settings", json=settings)
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("botocore").level == logging.WARNING


def test_the_environment_overrides_the_settings_page(monkeypatch):
    from wildintel_publisher.core import logging_setup

    monkeypatch.setenv("WILDINTEL_PUBLISHER_LOG_LEVEL", "debug")
    assert logging_setup.effective_level() == "DEBUG"
    body = _client().get("/api/settings").json()
    assert body["GENERAL"]["log_level"] == "INFO"
    assert body["GENERAL"]["log_level_override"] == "DEBUG"


def test_the_settings_show_where_the_log_is():
    from wildintel_publisher.core import logging_setup

    body = _client().get("/api/settings").json()
    assert body["GENERAL"]["log_file"] == str(logging_setup.log_file())
    assert body["GENERAL"]["log_level_override"] is None


def test_the_log_can_be_downloaded_and_cleared():
    from wildintel_publisher.core import logging_setup

    logging_setup.configure()
    logging.getLogger("wildintel_publisher.web.services.test").warning("a line for the bug report")
    _flush()

    response = _client().get("/api/settings/log")
    assert response.status_code == 200
    assert "a line for the bug report" in response.text

    assert _client().delete("/api/settings/log").json()["deleted"] >= 1
    # Only what was logged after the clear is left (the clear's own line, and this one).
    logging.getLogger("wildintel_publisher.web.services.test").warning("after the clear")
    _flush()
    text = logging_setup.log_file().read_text(encoding="utf-8")
    assert "a line for the bug report" not in text
    assert "after the clear" in text


def test_an_unknown_level_falls_back_to_info():
    from wildintel_publisher.core import logging_setup

    logging_setup.apply_level("verbose")
    assert logging.getLogger().level == logging.INFO
