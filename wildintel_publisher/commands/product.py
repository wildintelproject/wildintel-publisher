"""Comandos CLI del grupo 'product' — genera metadata.json a partir de
cualquier producto ya obtenido (una descarga de Trapper, un directorio local
con un dataset YOLO...), antes de arrancar el flujo de publicación (ver
services.product.generate_metadata_json). 'hfh prepare'/'zenodo prepare'/
'b2share prepare' requieren que este paso se haya ejecutado ya sobre
--input-dir."""
import logging
from pathlib import Path

import typer
from rich.console import Console

from wildintel_publisher.services import common
from wildintel_publisher.services import product as product_service

console = Console()
app     = typer.Typer(help="Commands to prepare metadata.json for any supported product type.")


@app.command("generate-metadata")
def generate_metadata(
    input_dir: str = typer.Option(..., "--input-dir", help="Directory with the already-obtained product."),
    product_type: str = typer.Option(
        ..., "--product-type",
        help=f"One of: {', '.join(product_service.registered_product_types())}.",
    ),
    anonymize_coordinates: bool = typer.Option(
        False, "--anonymize-coordinates/--no-anonymize-coordinates",
        help=(
            "Rounds deployments.csv's latitude/longitude to --coordinate-decimals places, in "
            "--input-dir itself (Camtrap DP only) — a privacy option for sensitive camera-trap "
            "locations. Applied once here, so every repo that later prepares its own export from "
            "this same --input-dir (directly, or chained from another repo's own output) inherits "
            "the same already-anonymized coordinates automatically."
        ),
    ),
    coordinate_decimals: int = typer.Option(
        common.DEFAULT_COORDINATE_DECIMALS, "--coordinate-decimals",
        help="Decimal places to round to when --anonymize-coordinates is set (2 ≈ 1.1 km).",
    ),
) -> None:
    """Validates the product and writes metadata.json into --input-dir —
    required once, before 'hfh prepare'/'zenodo prepare'/'b2share prepare'
    can use --input-dir."""
    try:
        metadata = product_service.generate_metadata_json(
            product_type, Path(input_dir),
            anonymize_coordinates=anonymize_coordinates, coordinate_decimals=coordinate_decimals,
        )
    except Exception as exc:
        logging.error("Could not generate metadata.json: %s", exc)
        raise typer.Exit(1) from exc

    console.print(f"[green]✔  metadata.json written to {input_dir} ({product_type}):[/green]")
    console.print(f"   title: {metadata.get('title')}")
    console.print(f"   license: {(metadata.get('license') or {}).get('id')}")
    authors = ", ".join(a.get("name") or "?" for a in metadata.get("authors") or [])
    console.print(f"   authors: {authors}")

    missing = product_service.missing_required_fields(metadata)
    if missing:
        console.print(
            f"[yellow]⚠  Missing required field(s): {', '.join(missing)} — "
            f"edit {input_dir}/metadata.json before publishing.[/yellow]"
        )
