"""Integration tests for 'trapper download'/'trapper test-connection' CLI wiring —
the underlying trapper_service calls are mocked out (no real network)."""
from unittest.mock import patch

from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def test_download_without_any_connection_params_reports_all_missing():
    result = runner.invoke(app, ["trapper", "download", "--deployment-id", "d1"])
    assert result.exit_code == 1
    assert "Missing Trapper connection details" in result.output
    assert "--trapper-url" in result.output
    assert "--trapper-user" in result.output
    assert "--trapper-password" in result.output
    assert "--project-id" in result.output


def test_download_missing_deployment_id_is_a_required_option():
    result = runner.invoke(app, ["trapper", "download", "--trapper-url", "https://t.example", "--trapper-user", "u", "--trapper-password", "p", "--project-id", "1"])
    assert result.exit_code != 0
    assert "deployment-id" in result.output.lower() or "Missing option" in result.output


def test_download_calls_service_with_resolved_params_when_all_present(tmp_path):
    with patch("wildintel_publisher.commands.trapper.trapper_service.fetch_camtrapdp_package") as mock_fetch:
        mock_fetch.return_value = tmp_path
        result = runner.invoke(app, [
            "trapper", "download",
            "--trapper-url", "https://t.example", "--trapper-user", "u", "--trapper-password", "p",
            "--project-id", "1", "--deployment-id", "r0007-dona_0018", "--output-dir", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output
    mock_fetch.assert_called_once()
    call_kwargs = mock_fetch.call_args.kwargs
    assert call_kwargs["trapper_url"] == "https://t.example"
    assert call_kwargs["project_id"] == 1
    assert call_kwargs["deployment_id"] == "r0007-dona_0018"
    assert call_kwargs["include_events"] is True  # default


def test_download_can_disable_include_events(tmp_path):
    with patch("wildintel_publisher.commands.trapper.trapper_service.fetch_camtrapdp_package") as mock_fetch:
        mock_fetch.return_value = tmp_path
        result = runner.invoke(app, [
            "trapper", "download",
            "--trapper-url", "https://t.example", "--trapper-user", "u", "--trapper-password", "p",
            "--project-id", "1", "--deployment-id", "r0007-dona_0018", "--output-dir", str(tmp_path),
            "--no-include-events",
        ])

    assert result.exit_code == 0, result.output
    assert mock_fetch.call_args.kwargs["include_events"] is False


def test_download_reports_service_errors_and_exits_nonzero():
    with patch("wildintel_publisher.commands.trapper.trapper_service.fetch_camtrapdp_package", side_effect=RuntimeError("boom")):
        result = runner.invoke(app, [
            "trapper", "download",
            "--trapper-url", "https://t.example", "--trapper-user", "u", "--trapper-password", "p",
            "--project-id", "1", "--deployment-id", "d1",
        ])
    assert result.exit_code == 1


def test_test_connection_without_params_reports_missing():
    result = runner.invoke(app, ["trapper", "test-connection"])
    assert result.exit_code == 1
    assert "Missing Trapper connection details" in result.output


def test_test_connection_success_prints_project_info():
    fake_project = type("P", (), {"name": "Test Project", "pk": 1, "owner": "someone"})()
    with patch("wildintel_publisher.commands.trapper.trapper_service.test_connection", return_value=fake_project):
        result = runner.invoke(app, [
            "trapper", "test-connection",
            "--trapper-url", "https://t.example", "--trapper-user", "u", "--trapper-password", "p", "--project-id", "1",
        ])
    assert result.exit_code == 0
    assert "Connected to https://t.example" in result.output
    assert "Test Project" in result.output


def test_test_connection_reports_service_error():
    with patch("wildintel_publisher.commands.trapper.trapper_service.test_connection", side_effect=RuntimeError("Incorrect Trapper username or password.")):
        result = runner.invoke(app, [
            "trapper", "test-connection",
            "--trapper-url", "https://t.example", "--trapper-user", "u", "--trapper-password", "wrong", "--project-id", "1",
        ])
    assert result.exit_code == 1
