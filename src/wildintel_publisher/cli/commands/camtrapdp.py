"""Comandos CLI del grupo 'camtrapdp' — los valores por defecto de cualquier
Camtrap DP (título, descripción, licencia), venga de Trapper, de un directorio
local o de una URL pública. Ver config.CamtrapDPSettings."""
import typer

from wildintel_publisher.cli.commands.config_commands import build_section_config_app
from wildintel_publisher.core.config import CamtrapDPSettings

app = typer.Typer(help="Defaults for any Camtrap DP (title, description, license).")
app.add_typer(build_section_config_app("CAMTRAPDP", CamtrapDPSettings), name="config")
