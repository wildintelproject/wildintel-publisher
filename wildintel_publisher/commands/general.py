"""Comandos CLI del grupo 'general' — el log de la aplicación: su nivel
(GENERAL.log_level), dónde está, y borrarlo. Ver logging_setup."""
import typer
from rich.console import Console

from wildintel_publisher import logging_setup
from wildintel_publisher.commands.config_commands import build_section_config_app
from wildintel_publisher.config import GeneralSettings

console = Console()
app     = typer.Typer(help="General settings: the log level, the log file.")
app.add_typer(build_section_config_app("GENERAL", GeneralSettings), name="config")


@app.command("log-file")
def log_file() -> None:
    """Shows where the log file is."""
    console.print(str(logging_setup.log_file()), soft_wrap=True)


@app.command("clear-log")
def clear_log(
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation."),
) -> None:
    """Deletes the log file and its rotated copies."""
    if not yes and not typer.confirm("Delete the log file and its older copies? This can't be undone."):
        console.print("Cancelled.")
        return
    console.print(f"[green]✔ Log cleared[/green] ({logging_setup.clear_log()} file(s) deleted).")
