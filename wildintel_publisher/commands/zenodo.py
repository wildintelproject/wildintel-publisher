"""Comandos CLI del grupo 'zenodo' — registro de metadatos en Zenodo (sin imágenes).

Gestiona únicamente los parámetros de entrada; la lógica vive en
wildintel_publisher.services.zenodo. Título/descripción/versión/
licencia/autores salen siempre de datapackage.json (el propio camtrapdp) —
'zenodo prepare' falla si no los trae, igual que 'hfh prepare'. Solo lo que
no existe en el estándar Camtrap DP (environment, communities, token) sale
de settings.toml (sección ZENODO, ver 'wildintel-publisher zenodo config').
"""
import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from wildintel_publisher.commands.config_commands import build_section_config_app
from wildintel_publisher.config import (
    ZenodoSettings,
    get_hfh_output_dir,
    get_trapper_output_dir,
    get_zenodo_output_dir,
    settings,
)
from wildintel_publisher.services import common
from wildintel_publisher.services import zenodo as zenodo_service

console = Console()
app     = typer.Typer(help="Commands related to Zenodo (metadata only, no images).")
app.add_typer(build_section_config_app("ZENODO", ZenodoSettings), name="config")

ZENODO_TOKEN_ENV_VAR = "ZENODO_TOKEN"


def _require_token() -> str:
    token = os.environ.get(ZENODO_TOKEN_ENV_VAR) or settings.ZENODO.token
    if token:
        return token
    base_url = "https://sandbox.zenodo.org" if settings.ZENODO.environment == "sandbox" else "https://zenodo.org"
    console.print(
        "[red]✘  No Zenodo token configured.[/red]\n"
        f"   Get one at [bold]{base_url}/account/settings/applications/tokens/new/[/bold] and export it:\n"
        f"   [bold]export {ZENODO_TOKEN_ENV_VAR}='...'[/bold]\n"
        "   or store it permanently: "
        "[bold]wildintel-publisher zenodo config set token[/bold]"
    )
    raise typer.Exit(1)


@app.command("prepare")
def prepare(
    input_dir: Optional[str] = typer.Option(
        None, "--input-dir",
        help=(
            "Directory with the already-downloaded Camtrap DP package (output of 'trapper "
            "download'). Defaults to $HOME/Documents/wildintel-publisher/trapper."
        ),
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory where the Zenodo record is prepared. "
            "Defaults to $HOME/Documents/wildintel-publisher/zenodo."
        ),
    ),
    hfh_repo_id: Optional[str] = typer.Option(
        settings.HFH.repo_id, "--hfh-repo-id",
        help=(
            "HuggingFace Hub repository where the images live — linked from README.md, and (unless "
            "--self-contained) used to rewrite media.csv's filePath to the predictable HuggingFace "
            "Hub URL of each file."
        ),
    ),
    self_contained: Optional[bool] = typer.Option(
        None, "--self-contained/--no-self-contained",
        help=(
            "Downloads the public images and bundles datapackage.json/CSVs + the images/ folder "
            "into a single self-contained camtrapdp.zip (filePath relative to images/), instead of "
            "linking to HuggingFace Hub. Takes precedence over --hfh-repo-id for the filePath rewrite. "
            "Defaults to enabled (mirror) for Camtrap DP when --hfh-repo-id isn't also given, disabled "
            "otherwise."
        ),
    ),
    version: str = typer.Option(
        zenodo_service.DEFAULT_VERSION, "--version",
        help="Dataset version — written into README.md and CITATION.cff.",
    ),
    timeout: int = typer.Option(
        common.DEFAULT_IMAGE_TIMEOUT, "--timeout",
        help="Network timeout (seconds) to download each public image. Only applies with --self-contained.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite",
        help="Allows reusing --output-dir even if it already exists and has content (overwriting it).",
    ),
) -> None:
    """Prepares the Zenodo record: copies the Camtrap DP from Trapper (public media only), and
    generates README.md, CITATION.cff, LICENSE and checksums-sha256.txt. Defaults to
    --self-contained (bundling the images into the record itself) for Camtrap DP, unless
    --hfh-repo-id is given (which points media.csv at HuggingFace Hub instead) — pass
    --no-self-contained to leave media.csv's filePath untouched instead."""
    resolved_input_dir = Path(input_dir) if input_dir else get_trapper_output_dir()
    resolved_output_dir = Path(output_dir) if output_dir else get_zenodo_output_dir()
    try:
        zenodo_service.prepare_zenodo_export(
            input_dir=resolved_input_dir,
            output_dir=resolved_output_dir,
            metadata=settings.ZENODO,
            hfh_repo_id=hfh_repo_id,
            self_contained=self_contained,
            version=version,
            image_timeout=timeout,
            overwrite=overwrite,
        )
    except Exception as exc:
        logging.error("Could not prepare the Zenodo record: %s", exc)
        raise typer.Exit(1) from exc


@app.command("upload")
def upload(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory of the already-prepared record (the same one from 'zenodo prepare'). "
            "Defaults to $HOME/Documents/wildintel-publisher/zenodo."
        ),
    ),
    environment: str = typer.Option(
        settings.ZENODO.environment, "--environment",
        help="Zenodo environment: 'sandbox' (testing, no real DOI) or 'production'. (ZENODO.environment)",
    ),
    communities: Optional[str] = typer.Option(
        settings.ZENODO.communities, "--communities",
        help="Zenodo communities, comma-separated. (ZENODO.communities)",
    ),
    hfh_repo_id: Optional[str] = typer.Option(
        settings.HFH.repo_id, "--hfh-repo-id",
        help="HuggingFace Hub repository to link via related_identifiers.",
    ),
) -> None:
    """Creates (or reuses) a Zenodo deposition and uploads the files of the already-prepared record."""
    resolved_output_dir = Path(output_dir) if output_dir else get_zenodo_output_dir()
    token = _require_token()

    try:
        zenodo_service.upload_to_zenodo(
            resolved_output_dir, token=token, environment=environment,
            communities=communities, hfh_repo_id=hfh_repo_id,
        )
    except Exception as exc:
        logging.error("Could not upload the record to Zenodo: %s", exc)
        raise typer.Exit(1) from exc


@app.command("release")
def release(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory of the already-uploaded record (the same one from 'zenodo upload'). "
            "Defaults to $HOME/Documents/wildintel-publisher/zenodo."
        ),
    ),
) -> None:
    """Publishes the Zenodo deposition (assigns the final DOI) and reflects it in its own CITATION.cff."""
    resolved_output_dir = Path(output_dir) if output_dir else get_zenodo_output_dir()
    token = _require_token()

    try:
        zenodo_service.release_on_zenodo(resolved_output_dir, token=token)
    except Exception as exc:
        logging.error("Could not publish the Zenodo deposition: %s", exc)
        raise typer.Exit(1) from exc


@app.command("sync-doi")
def sync_doi(
    zenodo_output_dir: Optional[str] = typer.Option(
        None, "--zenodo-output-dir",
        help=(
            "Directory of the already-published Zenodo record (the same one from 'zenodo release'). "
            "Defaults to $HOME/Documents/wildintel-publisher/zenodo."
        ),
    ),
    hfh_output_dir: Optional[str] = typer.Option(
        None, "--hfh-output-dir",
        help=(
            "Directory of the already-prepared HuggingFace Hub export (the same one from 'hfh prepare'). "
            "Defaults to $HOME/Documents/wildintel-publisher/hfh."
        ),
    ),
) -> None:
    """Reads the DOI already published on Zenodo and reflects it in the CITATION.cff of the HuggingFace
    Hub export (regenerating its checksums). The recommended next step is 'hfh upload'."""
    resolved_zenodo_output_dir = Path(zenodo_output_dir) if zenodo_output_dir else get_zenodo_output_dir()
    resolved_hfh_output_dir = Path(hfh_output_dir) if hfh_output_dir else get_hfh_output_dir()

    try:
        zenodo_service.sync_doi_to_hfh(
            zenodo_output_dir=resolved_zenodo_output_dir, hfh_output_dir=resolved_hfh_output_dir,
        )
    except Exception as exc:
        logging.error("Could not sync the DOI with the HuggingFace Hub export: %s", exc)
        raise typer.Exit(1) from exc
