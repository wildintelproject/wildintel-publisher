"""Integration tests for the top-level CLI (main.py): --help wiring and the
'version' command."""
from typer.testing import CliRunner

from wildintel_publisher.main import app

runner = CliRunner()


def test_top_level_help_lists_all_command_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("trapper", "hfh", "zenodo", "b2share", "version"):
        assert group in result.output


def test_version_command_prints_a_version_string():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_each_group_help_exits_zero():
    for group in ("trapper", "hfh", "zenodo", "b2share"):
        result = runner.invoke(app, [group, "--help"])
        assert result.exit_code == 0, result.output


def test_each_subcommand_help_exits_zero():
    subcommands = {
        "trapper": ["download", "test-connection", "config"],
        "hfh": ["prepare", "upload", "release", "pipeline", "config"],
        "zenodo": ["prepare", "upload", "release", "sync-doi", "config"],
        "b2share": ["prepare", "upload", "release", "sync-pid", "config"],
    }
    for group, commands in subcommands.items():
        for command in commands:
            result = runner.invoke(app, [group, command, "--help"])
            assert result.exit_code == 0, f"{group} {command} --help failed:\n{result.output}"
