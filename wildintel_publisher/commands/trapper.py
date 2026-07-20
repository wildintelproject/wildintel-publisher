"""Comandos CLI del grupo 'trapper' — interacción con una instancia de Trapper.

Gestiona únicamente los parámetros de entrada; la lógica de conexión y
descarga vive en wildintel_publisher.services.trapper. Los valores
por defecto de conexión (URL/usuario/contraseña/proyecto) salen de
settings.toml (sección TRAPPER, ver wildintel_publisher.config y
'wildintel-publisher config set') — no hace falta volver a
escribirlos en cada ejecución.
"""
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from wildintel_publisher.commands.config_commands import build_section_config_app
from wildintel_publisher.config import TrapperSettings, get_trapper_output_dir, settings
from wildintel_publisher.services import trapper as trapper_service

console = Console()
app     = typer.Typer(help="Commands related to Trapper.")
app.add_typer(build_section_config_app("TRAPPER", TrapperSettings), name="config")

TRAPPER_DEFAULTS = settings.TRAPPER

# Igual que hfh_service.DEFAULT_VERSION — se repite en vez de importar
# services.hfh aquí, para no acoplar 'trapper download' a la sección hfh.
DEFAULT_VERSION = "1.0"


def _trapper_help(field: str) -> str:
    """Reutiliza la description de TrapperSettings como help= del flag equivalente."""
    return TrapperSettings.model_fields[field].description


def _require_connection_params(
    trapper_url: Optional[str], trapper_user: Optional[str], trapper_password: Optional[str], project_id: Optional[int],
) -> None:
    """Aviso claro y temprano si falta algún dato de conexión, antes de que
    TrapperClient falle más adentro con un mensaje menos explícito."""
    missing = []
    if not trapper_url:
        missing.append(("--trapper-url", "WILDINTEL_BASE_URL", "base_url"))
    if not trapper_user:
        missing.append(("--trapper-user", "WILDINTEL_USER_NAME", "user_name"))
    if not trapper_password:
        missing.append(("--trapper-password", "WILDINTEL_USER_PASSWORD", "user_password"))
    if project_id is None:
        missing.append(("--project-id", None, "project_id"))

    if not missing:
        return

    console.print("[red]✘  Missing Trapper connection details:[/red]")
    for flag, envvar, field in missing:
        via = f" (or environment variable {envvar})" if envvar else ""
        console.print(
            f"   {flag}{via} — or store it permanently: "
            f"[bold]wildintel-publisher config set {field}=...[/bold]"
        )
    raise typer.Exit(1)


@app.command("download")
def download(
    trapper_url: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.base_url, "--trapper-url", envvar="WILDINTEL_BASE_URL", help=_trapper_help("base_url"),
    ),
    trapper_user: Optional[str] = typer.Option(
        # Sin default= (a diferencia de --trapper-url/--project-id): user_name es un
        # campo "secret" en TrapperSettings — pasar TRAPPER_DEFAULTS.user_name aquí lo
        # mostraría en claro en --help. El fallback a settings.toml se resuelve abajo.
        None, "--trapper-user", envvar="WILDINTEL_USER_NAME", help=_trapper_help("user_name"),
    ),
    trapper_password: Optional[str] = typer.Option(
        None, "--trapper-password", envvar="WILDINTEL_USER_PASSWORD", help=_trapper_help("user_password"),
    ),
    project_id: Optional[int] = typer.Option(
        TRAPPER_DEFAULTS.project_id, "--project-id", help=_trapper_help("project_id"),
    ),
    deployment_id: str = typer.Option(
        ..., "--deployment-id",
        help=(
            "Limits the package to this deployment (e.g. r0007-dona_0018). The server "
            "filters by partial match against the deployment_id field, not a numeric "
            "PK — a single value, not a list."
        ),
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory where the Camtrap DP package is downloaded and extracted. "
            "Defaults to $HOME/Documents/wildintel-publisher/trapper."
        ),
    ),
    clear_cache: bool = typer.Option(
        False, "--clear-cache",
        help="Forces Trapper to regenerate the package instead of reusing an already cached one.",
    ),
    timeout: int = typer.Option(
        trapper_service.DEFAULT_TIMEOUT, "--timeout",
        help="Network timeout (seconds) to generate and download the package. Increase it for large projects.",
    ),
    title: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.dataset_name, "--title", help=_trapper_help("dataset_name"),
    ),
    description: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.description, "--description", help=_trapper_help("description"),
    ),
    version: str = typer.Option(
        DEFAULT_VERSION, "--version",
        help="Version written inside datapackage.json.",
    ),
    license_id: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.license_id, "--license-id", help=_trapper_help("license_id"),
    ),
    license_name: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.license_name, "--license-name", help=_trapper_help("license_name"),
    ),
    license_url: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.license_url, "--license-url", help=_trapper_help("license_url"),
    ),
) -> None:
    """Fetches (generates, downloads and extracts) the Camtrap DP package of a Trapper classification project."""
    trapper_user = trapper_user or TRAPPER_DEFAULTS.user_name
    trapper_password = trapper_password or TRAPPER_DEFAULTS.user_password
    _require_connection_params(trapper_url, trapper_user, trapper_password, project_id)
    resolved_output_dir = Path(output_dir) if output_dir else get_trapper_output_dir()
    try:
        trapper_service.fetch_camtrapdp_package(
            trapper_url=trapper_url,
            trapper_user=trapper_user,
            trapper_password=trapper_password,
            project_id=project_id,
            deployment_id=deployment_id,
            output_dir=resolved_output_dir,
            clear_cache=clear_cache,
            timeout=timeout,
            title=title,
            description=description,
            version=version,
            license_id=license_id,
            license_name=license_name,
            license_url=license_url,
        )
    except Exception as exc:
        logging.error("Could not fetch the Camtrap DP package: %s", exc)
        raise typer.Exit(1) from exc


@app.command("test-connection")
def test_connection(
    trapper_url: Optional[str] = typer.Option(
        TRAPPER_DEFAULTS.base_url, "--trapper-url", envvar="WILDINTEL_BASE_URL", help=_trapper_help("base_url"),
    ),
    trapper_user: Optional[str] = typer.Option(
        None, "--trapper-user", envvar="WILDINTEL_USER_NAME", help=_trapper_help("user_name"),
    ),
    trapper_password: Optional[str] = typer.Option(
        None, "--trapper-password", envvar="WILDINTEL_USER_PASSWORD", help=_trapper_help("user_password"),
    ),
    project_id: Optional[int] = typer.Option(
        TRAPPER_DEFAULTS.project_id, "--project-id", help=_trapper_help("project_id"),
    ),
) -> None:
    """Checks that Trapper can be reached and that there is access to the given classification project."""
    trapper_user = trapper_user or TRAPPER_DEFAULTS.user_name
    trapper_password = trapper_password or TRAPPER_DEFAULTS.user_password
    _require_connection_params(trapper_url, trapper_user, trapper_password, project_id)
    try:
        project = trapper_service.test_connection(
            trapper_url=trapper_url,
            trapper_user=trapper_user,
            trapper_password=trapper_password,
            project_id=project_id,
        )
    except Exception as exc:
        logging.error("Could not connect: %s", exc)
        raise typer.Exit(1) from exc

    console.print(
        f"[green]✔  Connected to {trapper_url} — access confirmed to project "
        f"'{project.name}' (pk={project.pk}, owner={project.owner}).[/green]"
    )
