"""Comandos CLI del grupo 'b2share' — registro en B2SHARE (EUDAT), con los
mismos tres modos que 'zenodo prepare' para el filePath de media.csv:

- --self-contained: igual que 'zenodo prepare' --self-contained (descarga
  las imágenes, las empaqueta DENTRO de camtrapdp.zip y borra los ficheros
  sueltos — 'b2share upload' solo sube ese zip, nunca las imágenes una a
  una: la API de B2SHARE limita cada record a 100 ficheros).
- --hfh-repo-id (sin --self-contained): no descarga nada, reescribe
  filePath a la URL predecible de HuggingFace Hub.
- Ninguno de los dos (por defecto): filePath tal cual.

Gestiona únicamente los parámetros de entrada; la lógica vive en
wildintel_publisher.services.b2share. Título/descripción/versión/
licencia/autores salen siempre de datapackage.json (el propio camtrapdp) —
'b2share prepare' falla si no los trae, igual que 'hfh prepare'/'zenodo
prepare'. Solo lo que no existe en el estándar Camtrap DP (environment,
community_id, token) sale de settings.toml (sección B2SHARE, ver
'wildintel-publisher b2share config').
"""
import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from wildintel_publisher.commands.config_commands import build_section_config_app
from wildintel_publisher.config import (
    B2ShareSettings,
    get_b2share_output_dir,
    get_hfh_output_dir,
    get_trapper_output_dir,
    settings,
)
from wildintel_publisher.services import b2share as b2share_service

console = Console()
app     = typer.Typer(help="Commands related to B2SHARE (EUDAT).")
app.add_typer(build_section_config_app("B2SHARE", B2ShareSettings), name="config")

B2SHARE_TOKEN_ENV_VAR = "B2SHARE_TOKEN"


def _require_token() -> str:
    token = os.environ.get(B2SHARE_TOKEN_ENV_VAR) or settings.B2SHARE.token
    if token:
        return token
    base_url = "https://trng-b2share.eudat.eu" if settings.B2SHARE.environment == "sandbox" else "https://b2share.eudat.eu"
    console.print(
        "[red]✘  No B2SHARE token configured.[/red]\n"
        f"   Get one at [bold]{base_url}/user/profile[/bold] (Applications -> Personal access tokens) "
        "and export it:\n"
        f"   [bold]export {B2SHARE_TOKEN_ENV_VAR}='...'[/bold]\n"
        "   or store it permanently: "
        "[bold]wildintel-publisher b2share config set token[/bold]"
    )
    raise typer.Exit(1)


def _require_community_id(community_id: Optional[str]) -> str:
    if community_id:
        return community_id
    console.print(
        "[red]✘  Missing the EUDAT B2SHARE community UUID.[/red]\n"
        "   Request one at https://b2share.eudat.eu if you don't have one yet, and pass it with "
        "--community-id, or store it permanently: "
        "[bold]wildintel-publisher b2share config set community_id=<uuid>[/bold]"
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
            "Directory where the B2SHARE record is prepared. "
            "Defaults to $HOME/Documents/wildintel-publisher/b2share."
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
    self_contained: bool = typer.Option(
        False, "--self-contained",
        help=(
            "Same as 'zenodo prepare' --self-contained: downloads the public images and bundles "
            "datapackage.json/CSVs plus images/ into a single camtrapdp.zip (filePath relative to "
            "images/ inside it), removing the loose files afterwards. Needed because B2SHARE caps "
            "each record at 100 files — uploading one file per image would exceed that for most "
            "datasets. Takes precedence over --hfh-repo-id for the filePath rewrite."
        ),
    ),
    version: str = typer.Option(
        b2share_service.DEFAULT_VERSION, "--version",
        help="Dataset version — written into README.md and CITATION.cff.",
    ),
    timeout: int = typer.Option(
        b2share_service.DEFAULT_IMAGE_TIMEOUT, "--timeout",
        help="Network timeout (seconds) to download each public image. Only applies with --self-contained.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite",
        help="Allows reusing --output-dir even if it already exists and has content (overwriting it).",
    ),
) -> None:
    """Prepares the B2SHARE record: copies the Camtrap DP from Trapper (public media only), and
    generates README.md, CITATION.cff, LICENSE and checksums-sha256.txt. By default media.csv's
    filePath is left untouched; use --hfh-repo-id to point it at HuggingFace Hub, or
    --self-contained to also host the images on B2SHARE itself (exactly like 'hfh prepare')."""
    resolved_input_dir = Path(input_dir) if input_dir else get_trapper_output_dir()
    resolved_output_dir = Path(output_dir) if output_dir else get_b2share_output_dir()
    try:
        b2share_service.prepare_b2share_export(
            input_dir=resolved_input_dir,
            output_dir=resolved_output_dir,
            metadata=settings.B2SHARE,
            hfh_repo_id=hfh_repo_id,
            self_contained=self_contained,
            version=version,
            image_timeout=timeout,
            overwrite=overwrite,
        )
    except Exception as exc:
        logging.error("Could not prepare the B2SHARE record: %s", exc)
        raise typer.Exit(1) from exc


@app.command("upload")
def upload(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory of the already-prepared record (the same one from 'b2share prepare'). "
            "Defaults to $HOME/Documents/wildintel-publisher/b2share."
        ),
    ),
    environment: str = typer.Option(
        settings.B2SHARE.environment, "--environment",
        help="B2SHARE environment: 'sandbox' (testing) or 'production'. (B2SHARE.environment)",
    ),
    community_id: Optional[str] = typer.Option(
        settings.B2SHARE.community_id, "--community-id",
        help="UUID of the EUDAT B2SHARE community. (B2SHARE.community_id)",
    ),
    hfh_repo_id: Optional[str] = typer.Option(
        settings.HFH.repo_id, "--hfh-repo-id",
        help="HuggingFace Hub repository to link (only relevant if the record was prepared without --self-contained).",
    ),
) -> None:
    """Creates (or reuses) a B2SHARE draft and uploads the files of the already-prepared record (the
    single camtrapdp.zip in --self-contained mode, or the loose Camtrap DP files otherwise)."""
    resolved_output_dir = Path(output_dir) if output_dir else get_b2share_output_dir()
    token = _require_token()
    community_id = _require_community_id(community_id)

    try:
        b2share_service.upload_to_b2share(
            resolved_output_dir, token=token, environment=environment, community_id=community_id,
            hfh_repo_id=hfh_repo_id,
        )
    except Exception as exc:
        logging.error("Could not upload the record to B2SHARE: %s", exc)
        raise typer.Exit(1) from exc


@app.command("release")
def release(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory of the already-uploaded record (the same one from 'b2share upload'). "
            "Defaults to $HOME/Documents/wildintel-publisher/b2share."
        ),
    ),
) -> None:
    """Publishes (submits for publication) the B2SHARE draft. It may remain pending approval by
    a moderator of the EUDAT community — in that case, use 'b2share sync-pid' later."""
    resolved_output_dir = Path(output_dir) if output_dir else get_b2share_output_dir()
    token = _require_token()

    try:
        b2share_service.release_on_b2share(resolved_output_dir, token=token)
    except Exception as exc:
        logging.error("Could not publish the B2SHARE record: %s", exc)
        raise typer.Exit(1) from exc


@app.command("sync-pid")
def sync_pid(
    b2share_output_dir: Optional[str] = typer.Option(
        None, "--b2share-output-dir",
        help=(
            "Directory of the already-published B2SHARE record (the same one from 'b2share release'). "
            "Defaults to $HOME/Documents/wildintel-publisher/b2share."
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
    """Reads the PID/DOI already assigned on B2SHARE (if any) and reflects it in the CITATION.cff of the
    HuggingFace Hub export (regenerating its checksums). The recommended next step is 'hfh upload'."""
    resolved_b2share_output_dir = Path(b2share_output_dir) if b2share_output_dir else get_b2share_output_dir()
    resolved_hfh_output_dir = Path(hfh_output_dir) if hfh_output_dir else get_hfh_output_dir()

    try:
        b2share_service.sync_pid_to_hfh(
            b2share_output_dir=resolved_b2share_output_dir, hfh_output_dir=resolved_hfh_output_dir,
        )
    except Exception as exc:
        logging.error("Could not sync the PID/DOI with the HuggingFace Hub export: %s", exc)
        raise typer.Exit(1) from exc
