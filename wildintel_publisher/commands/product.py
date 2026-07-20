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
) -> None:
    """Validates the product and writes metadata.json into --input-dir —
    required once, before 'hfh prepare'/'zenodo prepare'/'b2share prepare'
    can use --input-dir."""
    try:
        metadata = product_service.generate_metadata_json(product_type, Path(input_dir))
    except Exception as exc:
        logging.error("Could not generate metadata.json: %s", exc)
        raise typer.Exit(1) from exc

    console.print(f"[green]✔  metadata.json written to {input_dir} ({product_type}):[/green]")
    console.print(f"   title: {metadata['title']}")
    console.print(f"   license: {metadata['license']['id']}")
    console.print(f"   authors: {', '.join(a['name'] for a in metadata['authors'])}")
