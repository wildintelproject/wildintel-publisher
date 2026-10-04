"""
wildintel-publisher — CLI principal.

Uso:
    uv run wildintel-publisher --help
"""
from typing import Annotated

import typer

from wildintel_publisher.core import logging_setup
from wildintel_publisher.cli.commands import b2share as b2share_cmd
from wildintel_publisher.cli.commands import camtrapdp as camtrapdp_cmd
from wildintel_publisher.cli.commands import gbif as gbif_cmd
from wildintel_publisher.cli.commands import general as general_cmd
from wildintel_publisher.cli.commands import hfh as hfh_cmd
from wildintel_publisher.cli.commands import product as product_cmd
from wildintel_publisher.cli.commands import trapper as trapper_cmd
from wildintel_publisher.cli.commands import zenodo as zenodo_cmd

app = typer.Typer(help="wildintel-publisher — fetches products (Camtrap DP, YOLO datasets...) and publishes them to HuggingFace Hub, Zenodo, B2SHARE and GBIF.")
app.add_typer(general_cmd.app, name="general")
app.add_typer(trapper_cmd.app, name="trapper")
app.add_typer(camtrapdp_cmd.app, name="camtrapdp")
app.add_typer(product_cmd.app, name="product")
app.add_typer(hfh_cmd.app, name="hfh")
app.add_typer(zenodo_cmd.app, name="zenodo")
app.add_typer(b2share_cmd.app, name="b2share")
app.add_typer(gbif_cmd.app, name="gbif")


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show the log's messages on the terminal as it works.")] = False,
) -> None:
    # The log file gets the settings' level (see 'general config'); the
    # terminal only warnings, unless --verbose.
    logging_setup.configure(console_level="DEBUG" if verbose else "WARNING")


@app.command()
def version() -> None:
    """Shows the installed version."""
    from importlib.metadata import version as _version
    typer.echo(_version("wildintel-publisher"))


if __name__ == "__main__":
    app()
