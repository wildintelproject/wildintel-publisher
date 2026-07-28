"""Comandos CLI del grupo 'gbif' — registro (no subida) de un dataset en el
Registry de GBIF, apuntando a un camtrapdp ya alojado en cualquier otra
parte (HuggingFace Hub, Zenodo, B2SHARE, un servidor propio...).

Gestiona únicamente los parámetros de entrada; la lógica vive en
wildintel_publisher.services.gbif. Título/descripción/licencia salen
siempre de metadata.json (ver services.product), igual que en hfh/zenodo/
b2share. Solo lo que la Registry API de GBIF exige y no existe en el
estándar Camtrap DP (environment, claves de organización/instalación,
credenciales) sale de settings.toml (sección GBIF, ver 'wildintel-publisher
gbif config').
"""
import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from wildintel_publisher.commands.config_commands import build_section_config_app
from wildintel_publisher.config import GBIFSettings, get_gbif_output_dir, get_hfh_output_dir, get_trapper_output_dir, settings
from wildintel_publisher.services import gbif as gbif_service
from wildintel_publisher.services import product

console = Console()
app     = typer.Typer(help="Commands related to GBIF (register a Camtrap DP already hosted elsewhere).")
app.add_typer(build_section_config_app("GBIF", GBIFSettings), name="config")

GBIF_USERNAME_ENV_VAR = "GBIF_USERNAME"
GBIF_PASSWORD_ENV_VAR = "GBIF_PASSWORD"


def _require_credentials() -> tuple:
    username = os.environ.get(GBIF_USERNAME_ENV_VAR) or settings.GBIF.username
    password = os.environ.get(GBIF_PASSWORD_ENV_VAR) or settings.GBIF.password
    if username and password:
        return username, password
    console.print(
        "[red]✘  No GBIF Registry API credentials configured.[/red]\n"
        "   Sign up for a free account at [bold]https://www.gbif.org/user/profile[/bold] "
        "(or https://www.gbif-test.org for the sandbox — a separate account) and export it:\n"
        f"   [bold]export {GBIF_USERNAME_ENV_VAR}='...'[/bold]\n"
        f"   [bold]export {GBIF_PASSWORD_ENV_VAR}='...'[/bold]\n"
        "   or store them permanently: "
        "[bold]wildintel-publisher gbif config set username[/bold] / "
        "[bold]set password[/bold]\n"
        "   Testing against --environment sandbox (gbif-test.org) only? GBIF publishes a "
        "shared demo login for exactly that — no signup needed: username "
        "[bold]ws_client_demo[/bold], password [bold]Demo123[/bold] (pairs with the demo "
        "organization/installation below)."
    )
    raise typer.Exit(1)


def _require_organization_and_installation(organization_key: Optional[str], installation_key: Optional[str]) -> tuple:
    if organization_key and installation_key:
        return organization_key, installation_key
    console.print(
        "[red]✘  Missing GBIF publishing organization/installation.[/red]\n"
        "   GBIF only accepts data from an [bold]organization[/bold] endorsed by a GBIF "
        "Participant Node — this is a manual review process (days, not instant) and cannot "
        "be automated via API:\n"
        "   1. Request endorsement at [bold]https://www.gbif.org/become-a-publisher[/bold] "
        "(see https://www.gbif.org/endorsement-guidelines for what the node looks at; "
        "sandbox equivalent requested separately via gbif-test.org).\n"
        "   2. Once endorsed, find your organization's UUID in its gbif.org page URL "
        "(https://www.gbif.org/publisher/<uuid>) and set it with:\n"
        "      [bold]wildintel-publisher gbif config set publishing_organization_key=<uuid>[/bold]\n"
        "   3. From that same organization's admin page, add an installation (any technical "
        "type works, e.g. a plain IPT) and set its UUID (found the same way) with:\n"
        "      [bold]wildintel-publisher gbif config set installation_key=<uuid>[/bold]\n"
        "   Just want to smoke-test --environment sandbox first, without registering "
        "anything of your own? GBIF's gbif-test.org demo login (username ws_client_demo / "
        "password Demo123) has permission to create datasets under a shared 'Test "
        "Organization #1' / 'Test HTTP installation' pair:\n"
        "      [bold]wildintel-publisher gbif config set publishing_organization_key="
        "0a16da09-7719-40de-8d4f-56a15ed52fb6[/bold]\n"
        "      [bold]wildintel-publisher gbif config set installation_key="
        "92d76df5-3de1-4c89-be03-7a17abad962a[/bold]\n"
        "   (shared/public — fine for a connectivity smoke test, not for anything you "
        "actually care about keeping)."
    )
    raise typer.Exit(1)


@app.command("register")
def register(
    archive_url: str = typer.Option(
        ..., "--archive-url",
        help=(
            "Public URL where the Camtrap DP package is already hosted (HuggingFace Hub, "
            "Zenodo, B2SHARE, your own server...) — GBIF will crawl it from there. No file "
            "is uploaded; this only registers that URL."
        ),
    ),
    input_dir: Optional[str] = typer.Option(
        None, "--input-dir",
        help=(
            "Directory carrying metadata.json (from 'product generate-metadata') — read for "
            "title/description/license. Defaults to $HOME/Documents/wildintel-publisher/trapper."
        ),
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory where gbif_linked_dataset_record.json is read/written, to tell a first "
            "'register' (creates the dataset) from a later one (updates it). Defaults to "
            "$HOME/Documents/wildintel-publisher/gbif."
        ),
    ),
    environment: str = typer.Option(
        settings.GBIF.environment, "--environment",
        help="GBIF environment: 'sandbox' (gbif-test.org, testing) or 'production' (gbif.org). (GBIF.environment)",
    ),
    publishing_organization_key: Optional[str] = typer.Option(
        settings.GBIF.publishing_organization_key, "--publishing-organization-key",
        help="UUID of your organization already registered on gbif.org. (GBIF.publishing_organization_key)",
    ),
    installation_key: Optional[str] = typer.Option(
        settings.GBIF.installation_key, "--installation-key",
        help="UUID of your installation already registered on gbif.org. (GBIF.installation_key)",
    ),
    registry_language: str = typer.Option(
        settings.GBIF.registry_language, "--registry-language",
        help="Language code (ISO 639-2/T) required by the Registry API. (GBIF.registry_language)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Shows what would be registered/updated, without calling the Registry API.",
    ),
) -> None:
    """Registers (or updates) the dataset in the GBIF Registry by API — no IPT involved.

    Requires that the Camtrap DP is already hosted somewhere public
    (--archive-url), and that GBIF.publishing_organization_key/
    installation_key are configured (create them once, by hand, on gbif.org
    or its sandbox gbif-test.org). Uses your gbif.org account credentials
    via the GBIF_USERNAME/GBIF_PASSWORD environment variables — the
    Registry API uses Basic Auth, not a token. The first run creates the
    dataset; later runs update its metadata and replace the CAMTRAP_DP
    endpoint with the current --archive-url.
    """
    resolved_input_dir = Path(input_dir) if input_dir else get_trapper_output_dir()
    resolved_output_dir = Path(output_dir) if output_dir else get_gbif_output_dir()

    username, password = _require_credentials()
    organization_key, installation = _require_organization_and_installation(
        publishing_organization_key, installation_key,
    )

    try:
        metadata = product.read_metadata_json(resolved_input_dir)
    except Exception as exc:
        logging.error("Could not read metadata.json: %s", exc)
        raise typer.Exit(1) from exc

    if metadata["product_type"] != product.CAMTRAPDP:
        console.print(
            f"[red]✘  GBIF only accepts Camtrap DP (biodiversity occurrence data) — "
            f"{resolved_input_dir} is a {metadata['product_type']!r} product.[/red]"
        )
        raise typer.Exit(1)

    license_info = metadata.get("license") or {}

    try:
        gbif_service.register_gbif_dataset(
            archive_url,
            resolved_output_dir,
            environment=environment,
            publishing_organization_key=organization_key,
            installation_key=installation,
            username=username,
            password=password,
            title=metadata["title"],
            description=metadata["description"],
            license_url=license_info.get("url") or "",
            registry_language=registry_language,
            homepage=metadata.get("homepage"),
            dry_run=dry_run,
        )
    except Exception as exc:
        logging.error("Could not register the dataset on GBIF: %s", exc)
        raise typer.Exit(1) from exc


@app.command("sync-doi")
def sync_doi(
    gbif_output_dir: Optional[str] = typer.Option(
        None, "--gbif-output-dir",
        help=(
            "Directory of the already-registered GBIF dataset (the same one from 'gbif register'). "
            "Defaults to $HOME/Documents/wildintel-publisher/gbif."
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
    """Reads the DOI GBIF assigned to the dataset (if any — only organizations with their own
    DataCite arrangement configured with GBIF get one automatically) and reflects it in the
    CITATION.cff of the HuggingFace Hub export (regenerating its checksums). The recommended
    next step is 'hfh upload'."""
    resolved_gbif_output_dir = Path(gbif_output_dir) if gbif_output_dir else get_gbif_output_dir()
    resolved_hfh_output_dir = Path(hfh_output_dir) if hfh_output_dir else get_hfh_output_dir()

    try:
        gbif_service.sync_doi_to_hfh(
            gbif_output_dir=resolved_gbif_output_dir, hfh_output_dir=resolved_hfh_output_dir,
        )
    except Exception as exc:
        logging.error("Could not sync the DOI with the HuggingFace Hub export: %s", exc)
        raise typer.Exit(1) from exc
