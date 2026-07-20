"""Comandos CLI del grupo 'hfh' — preparación del export para HuggingFace Hub.

Gestiona únicamente los parámetros de entrada; la lógica vive en
wildintel_publisher.services.hfh. Título/descripción/versión/
licencia/autores salen siempre de datapackage.json (el propio camtrapdp) —
'hfh prepare' falla si no los trae. Solo lo que no existe en el estándar
Camtrap DP (message, repository_code, repo_id, token) sale de settings.toml
(sección HFH, ver 'wildintel-publisher hfh config').
"""
import logging
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from wildintel_publisher.commands.config_commands import build_section_config_app, print_section
from wildintel_publisher.config import HFHSettings, get_hfh_output_dir, get_trapper_output_dir, settings
from wildintel_publisher.services import hfh as hfh_service
from wildintel_publisher.services import product

console = Console()
app     = typer.Typer(help="Commands related to HuggingFace Hub.")
app.add_typer(build_section_config_app("HFH", HFHSettings), name="config")

HF_TOKEN_ENV_VAR = "HF_TOKEN"


def _require_repo_id(repo_id: Optional[str]) -> str:
    if repo_id:
        return repo_id
    console.print(
        "[red]✘  Missing the HuggingFace Hub repository.[/red]\n"
        "   --repo-id, or store it permanently: "
        "[bold]wildintel-publisher hfh config set repo_id=user_or_org/dataset[/bold]"
    )
    raise typer.Exit(1)


def _require_token() -> str:
    token = os.environ.get(HF_TOKEN_ENV_VAR) or settings.HFH.token
    if token:
        return token
    console.print(
        "[red]✘  No HuggingFace Hub token configured.[/red]\n"
        "   Get one at [bold]https://huggingface.co/settings/tokens[/bold] (write permission) and export it:\n"
        f"   [bold]export {HF_TOKEN_ENV_VAR}='hf_xxxxxxxxxxxxxxxxxxxxxxxxx'[/bold]\n"
        "   or store it permanently: "
        "[bold]wildintel-publisher hfh config set token[/bold]"
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
            "Directory where the HuggingFace Hub export is prepared. "
            "Defaults to $HOME/Documents/wildintel-publisher/hfh."
        ),
    ),
    version: str = typer.Option(
        hfh_service.DEFAULT_VERSION, "--version",
        help="Dataset version — written into README.md and CITATION.cff.",
    ),
    timeout: int = typer.Option(
        hfh_service.DEFAULT_IMAGE_TIMEOUT, "--timeout",
        help="Network timeout (seconds) to download each public image.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite",
        help="Allows reusing --output-dir even if it already exists and has content (overwriting it).",
    ),
    mirror_images: bool = typer.Option(
        True, "--mirror-images/--link-images",
        help=(
            "mirror (default): downloads the public images and bundles a local, self-contained zip. "
            "link: doesn't download any image — media.csv keeps its original filePath as-is."
        ),
    ),
) -> None:
    """Prepares the HuggingFace Hub export: copies the Camtrap DP from Trapper (public media only),
    downloads its images (unless --link-images), and generates README.md, CITATION.cff, LICENSE
    and checksums-sha256.txt."""
    resolved_input_dir = Path(input_dir) if input_dir else get_trapper_output_dir()
    resolved_output_dir = Path(output_dir) if output_dir else get_hfh_output_dir()
    try:
        hfh_service.prepare_hfh_export(
            input_dir=resolved_input_dir,
            output_dir=resolved_output_dir,
            metadata=settings.HFH,
            version=version,
            image_timeout=timeout,
            overwrite=overwrite,
            mirror_images=mirror_images,
        )
    except Exception as exc:
        logging.error("Could not prepare the HuggingFace Hub export: %s", exc)
        raise typer.Exit(1) from exc


@app.command("upload")
def upload(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory of the already-prepared export (the same one from 'hfh prepare'). "
            "Defaults to $HOME/Documents/wildintel-publisher/hfh."
        ),
    ),
    repo_id: Optional[str] = typer.Option(
        settings.HFH.repo_id, "--repo-id", help=HFHSettings.model_fields["repo_id"].description,
    ),
    private: bool = typer.Option(
        True, "--private/--public",
        help="Creates the repository as private (default) or public, only if it doesn't exist yet.",
    ),
    mirror_images: bool = typer.Option(
        True, "--mirror-images/--link-images",
        help=(
            "mirror (default): rewrites filePath in media.csv to point to the already-uploaded "
            "images. link: leaves media.csv untouched — must match the mode 'hfh prepare' used."
        ),
    ),
) -> None:
    """Uploads the already-prepared export to HuggingFace Hub, and (in mirror mode) rewrites
    filePath in media.csv to point to the already-uploaded images (instead of Trapper)."""
    resolved_output_dir = Path(output_dir) if output_dir else get_hfh_output_dir()
    repo_id = _require_repo_id(repo_id)
    token = _require_token()

    try:
        hfh_service.upload_to_huggingface(
            resolved_output_dir, repo_id=repo_id, token=token, private=private, mirror_images=mirror_images,
        )
    except Exception as exc:
        logging.error("Could not upload the export to HuggingFace Hub: %s", exc)
        raise typer.Exit(1) from exc


@app.command("release")
def release(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir",
        help=(
            "Directory of the already-uploaded export (the same one from 'hfh upload') — read only to "
            "know which version to tag. Defaults to $HOME/Documents/wildintel-publisher/hfh."
        ),
    ),
    repo_id: Optional[str] = typer.Option(
        settings.HFH.repo_id, "--repo-id", help=HFHSettings.model_fields["repo_id"].description,
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Shows whether it's already public/accessible, without changing anything.",
    ),
    verify_only: bool = typer.Option(
        False, "--verify-only",
        help="Only checks the current visibility/accessibility, without changing anything.",
    ),
) -> None:
    """Tags the uploaded version (locking it — see 'hfh upload') and makes the HuggingFace Hub
    repository public, verifying it's accessible without a token."""
    if dry_run and verify_only:
        console.print("[red]✘  Use --dry-run or --verify-only, not both.[/red]")
        raise typer.Exit(1)

    repo_id = _require_repo_id(repo_id)
    token = _require_token()

    if not dry_run and not verify_only:
        resolved_output_dir = Path(output_dir) if output_dir else get_hfh_output_dir()
        try:
            product_meta = product.read_metadata_json(resolved_output_dir)
            version = product_meta.get("version") or hfh_service.DEFAULT_VERSION
            hfh_service.tag_release_on_huggingface(repo_id=repo_id, token=token, version=version)
        except Exception as exc:
            logging.error("Could not tag the repository: %s", exc)
            raise typer.Exit(1) from exc

    try:
        hfh_service.release_on_huggingface(repo_id=repo_id, token=token, dry_run=dry_run, verify_only=verify_only)
    except Exception as exc:
        logging.error("Could not make the repository public: %s", exc)
        raise typer.Exit(1) from exc


def _wizard_prompt_pipeline_params(
    input_dir: Optional[str], output_dir: Optional[str], version: str, timeout: int,
    repo_id: Optional[str], private: bool, overwrite: bool, mirror_images: bool,
) -> Optional[tuple]:
    """Asks each pipeline parameter interactively, showing as the default
    value the same one non-interactive mode would already use (a passed
    flag, or otherwise the one in settings.toml/config.py). Returns None if
    the user doesn't want to continue after the initial notice."""
    console.print()
    console.print(Panel(
        "This assistant publishes the dataset to HuggingFace Hub in one go: "
        "[bold]prepare[/bold] -> [bold]upload[/bold] -> [bold]release[/bold].\n\n"
        "It will ask you, one by one, for the parameters of each step. Each question "
        "shows in brackets the value you already have configured — press "
        "[bold]Enter[/bold] to keep it.",
        title="🚀 HuggingFace Hub publishing assistant",
        border_style="cyan",
    ))
    if not typer.confirm("\nContinue?", default=True):
        return None

    print_section("Pipeline parameters")
    console.print()

    default_input_dir = str(Path(input_dir) if input_dir else get_trapper_output_dir())
    new_input_dir = typer.prompt("Directory with the already-downloaded Camtrap DP (--input-dir)", default=default_input_dir)
    console.print(f"[green]✓[/green] input-dir: [bold]{new_input_dir}[/bold]\n")

    default_output_dir = str(Path(output_dir) if output_dir else get_hfh_output_dir())
    new_output_dir = typer.prompt("Directory where the export will be prepared (--output-dir)", default=default_output_dir)
    console.print(f"[green]✓[/green] output-dir: [bold]{new_output_dir}[/bold]\n")

    new_version = typer.prompt("Dataset version (--version)", default=version)
    console.print(f"[green]✓[/green] version: [bold]{new_version}[/bold]\n")

    new_timeout = typer.prompt("Network timeout in seconds (--timeout)", default=timeout, type=int)
    console.print(f"[green]✓[/green] timeout: [bold]{new_timeout}[/bold]\n")

    new_repo_id = typer.prompt("HuggingFace Hub repository (--repo-id)", default=repo_id or "").strip() or None
    console.print(f"[green]✓[/green] repo-id: [bold]{new_repo_id or '(not set)'}[/bold]\n")

    new_private = typer.confirm("Create the repository as private if it doesn't exist yet? (--private/--public)", default=private)
    console.print(f"[green]✓[/green] private: [bold]{'yes' if new_private else 'no (public)'}[/bold]\n")

    new_overwrite = typer.confirm("Reuse --output-dir even if it already has content? (--overwrite)", default=overwrite)
    console.print(f"[green]✓[/green] overwrite: [bold]{'yes' if new_overwrite else 'no'}[/bold]\n")

    new_mirror_images = typer.confirm(
        "Mirror images to HuggingFace Hub? (yes = mirror, no = link, keeps the original filePath) "
        "(--mirror-images/--link-images)",
        default=mirror_images,
    )
    console.print(f"[green]✓[/green] mode: [bold]{'mirror' if new_mirror_images else 'link'}[/bold]")

    return (
        new_input_dir, new_output_dir, new_version, new_timeout, new_repo_id, new_private, new_overwrite,
        new_mirror_images,
    )


def _print_pipeline_summary(
    input_dir: Path, output_dir: Path, version: str, timeout: int, repo_id: Optional[str], private: bool,
    overwrite: bool, mirror_images: bool,
) -> None:
    print_section("Summary")
    table = Table(title="Pipeline parameters")
    table.add_column("Parameter")
    table.add_column("Value")
    table.add_row("input-dir", str(input_dir))
    table.add_row("output-dir", str(output_dir))
    table.add_row("version", version)
    table.add_row("timeout", str(timeout))
    table.add_row("repo-id", repo_id or "(not set)")
    table.add_row("private", "yes" if private else "no (public)")
    table.add_row("overwrite", "yes" if overwrite else "no")
    table.add_row("mode", "mirror" if mirror_images else "link")
    console.print(table)


@app.command("pipeline")
def pipeline(
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
            "Directory where the HuggingFace Hub export is prepared. "
            "Defaults to $HOME/Documents/wildintel-publisher/hfh."
        ),
    ),
    version: str = typer.Option(
        hfh_service.DEFAULT_VERSION, "--version",
        help="Dataset version — written into README.md and CITATION.cff.",
    ),
    timeout: int = typer.Option(
        hfh_service.DEFAULT_IMAGE_TIMEOUT, "--timeout",
        help="Network timeout (seconds) to download each public image.",
    ),
    repo_id: Optional[str] = typer.Option(
        settings.HFH.repo_id, "--repo-id", help=HFHSettings.model_fields["repo_id"].description,
    ),
    private: bool = typer.Option(
        True, "--private/--public",
        help="Creates the repository as private (default) or public, only if it doesn't exist yet.",
    ),
    wizard: bool = typer.Option(
        False, "--wizard",
        help="Asks each parameter interactively (with the configuration value as the "
             "default) and asks for confirmation with a summary before running.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite",
        help="Allows reusing --output-dir even if it already exists and has content (overwriting it).",
    ),
    mirror_images: bool = typer.Option(
        True, "--mirror-images/--link-images",
        help=(
            "mirror (default): downloads the public images, uploads them to HuggingFace Hub, and "
            "rewrites media.csv's filePath to point to them. link: doesn't touch any image — "
            "media.csv keeps its original filePath as-is."
        ),
    ),
) -> None:
    """Runs in one go: prepare -> upload -> release."""
    if wizard:
        result = _wizard_prompt_pipeline_params(
            input_dir, output_dir, version, timeout, repo_id, private, overwrite, mirror_images,
        )
        if result is None:
            console.print("[yellow]⚠ Cancelled. Nothing was run.[/yellow]")
            raise typer.Exit(0)
        input_dir, output_dir, version, timeout, repo_id, private, overwrite, mirror_images = result

    resolved_input_dir = Path(input_dir) if input_dir else get_trapper_output_dir()
    resolved_output_dir = Path(output_dir) if output_dir else get_hfh_output_dir()

    if wizard:
        _print_pipeline_summary(
            resolved_input_dir, resolved_output_dir, version, timeout, repo_id, private, overwrite, mirror_images,
        )
        if not typer.confirm("\nContinue with these parameters?", default=True):
            console.print("[yellow]⚠ Cancelled. Nothing was run.[/yellow]")
            raise typer.Exit(0)

    repo_id = _require_repo_id(repo_id)
    token = _require_token()

    console.print("[bold cyan]── Step 1/3: prepare ──[/bold cyan]")
    try:
        hfh_service.prepare_hfh_export(
            input_dir=resolved_input_dir,
            output_dir=resolved_output_dir,
            metadata=settings.HFH,
            version=version,
            image_timeout=timeout,
            overwrite=overwrite,
            mirror_images=mirror_images,
        )
    except Exception as exc:
        logging.error("prepare failed: %s", exc)
        raise typer.Exit(1) from exc

    console.print("\n[bold cyan]── Step 2/3: upload ──[/bold cyan]")
    try:
        hfh_service.upload_to_huggingface(
            resolved_output_dir, repo_id=repo_id, token=token, private=private, mirror_images=mirror_images,
        )
    except Exception as exc:
        logging.error("upload failed: %s", exc)
        raise typer.Exit(1) from exc

    console.print("\n[bold cyan]── Step 3/3: release ──[/bold cyan]")
    try:
        product_meta = product.read_metadata_json(resolved_output_dir)
        release_version = product_meta.get("version") or hfh_service.DEFAULT_VERSION
        hfh_service.tag_release_on_huggingface(repo_id=repo_id, token=token, version=release_version)
        hfh_service.release_on_huggingface(repo_id=repo_id, token=token, dry_run=False, verify_only=False)
    except Exception as exc:
        logging.error("release failed: %s", exc)
        raise typer.Exit(1) from exc

    console.print("\n[bold green]✔  Pipeline completed.[/bold green]")
