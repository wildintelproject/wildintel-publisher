"""Motor genérico para inspeccionar y editar una sección de settings.toml.

Usado por 'trapper config' (sección TRAPPER) y 'hfh config' (sección HFH) —
build_section_config_app() construye un sub-Typer show/get/set/wizard para
cualquier sección dada, en vez de duplicar la misma lógica en cada una.

Importante: _save() siempre reescribe el Settings COMPLETO (todas las
secciones), no solo la que se está editando — settings.toml se sobreescribe
entero en cada guardado (loaders.toml_loader.write(..., merge=False)), así
que guardar solo una sección borraría el resto.
"""
from typing import Any, Type, get_origin

import typer
from dynaconf import loaders
from pydantic import BaseModel, TypeAdapter, ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from wildintel_publisher.config import DEFAULT_CONFIG_FILE, Settings, load_settings

console = Console()

SECRET_MASK = "••••••••"


def print_section(title: str) -> None:
    """Cabecera de sección — mismo estilo que wildintel-tools (regla verde +
    título en negrita, ver src/wildintel_tools/ui/typer/commands/wizards/zooniverse.py).
    Compartida por todos los wizards (config y pipeline)."""
    rule = "━" * 67
    console.print()
    console.print(f"[green]{rule}[/green]")
    console.print(f"[bold green]{title}[/bold green]")
    console.print(f"[green]{rule}[/green]")


def _is_secret_field(model: Type[BaseModel], field: str) -> bool:
    """True para campos marcados con json_schema_extra={"secret": True} en
    config.py — nunca se muestran en claro por 'show', ni se piden con eco
    en pantalla."""
    extra = model.model_fields[field].json_schema_extra
    return bool(isinstance(extra, dict) and extra.get("secret"))


def _format_value(value: Any, secret: bool = False) -> str:
    if secret:
        return SECRET_MASK if value else "(not set)"
    return str(value)


def _parse_value(annotation: Any, raw: str) -> Any:
    origin = get_origin(annotation)
    if origin is list:
        items = [v.strip() for v in raw.split(",") if v.strip()]
        return TypeAdapter(annotation).validate_python(items)
    return TypeAdapter(annotation).validate_python(raw)


def _save(settings: Settings) -> None:
    loaders.toml_loader.write(str(DEFAULT_CONFIG_FILE), settings.model_dump(mode="json"), merge=False)


def build_section_config_app(section: str, model: Type[BaseModel]) -> typer.Typer:
    """Construye un sub-Typer con show/get/set/wizard para una única sección
    de settings.toml (ej. section="TRAPPER", model=TrapperSettings)."""
    app = typer.Typer(help=f"Inspect or edit the {section} section of settings.toml.")

    def _resolve_field(field: str):
        if field not in model.model_fields:
            fields = ", ".join(model.model_fields)
            raise typer.BadParameter(f"Unknown field: '{field}'. Use one of: {fields}.")
        return model.model_fields[field]

    def _apply_update(settings: Settings, field: str, value: Any) -> Settings:
        section_model = getattr(settings, section)
        new_section = model.model_validate(section_model.model_dump(mode="json") | {field: value})
        return settings.model_copy(update={section: new_section})

    def _prompt_field(section_model: BaseModel, field: str) -> Any:
        field_info = model.model_fields[field]
        current = getattr(section_model, field)
        label = field_info.description or field

        if _is_secret_field(model, field):
            console.print(f"\n[bold]{field}[/bold] — {label}")
            console.print(f"  Current value: {'set (hidden)' if current else 'not set'}")
            raw = typer.prompt(
                "  New value (Enter to keep it unchanged)", default="", show_default=False, hide_input=True,
            )
            return current if raw == "" else raw

        default_str = "" if current is None else str(current)
        while True:
            console.print(f"\n[bold]{field}[/bold] — {label}")
            raw = typer.prompt("  Value", default=default_str)
            if raw == "" and current is None:
                return None
            try:
                return _parse_value(field_info.annotation, raw)
            except ValidationError as e:
                console.print(f"  [red]Invalid value:[/red] {e}")

    @app.command("show")
    def config_show() -> None:
        """Shows the current values of the section in settings.toml (secrets are masked)."""
        section_model = getattr(load_settings(), section)
        console.print(f"[bold]{DEFAULT_CONFIG_FILE}[/bold]")
        table = Table(title=f"[{section}]")
        table.add_column("Field")
        table.add_column("Value")
        for field in model.model_fields:
            table.add_row(field, _format_value(getattr(section_model, field), _is_secret_field(model, field)))
        console.print(table)

    @app.command("get")
    def config_get(field: str = typer.Argument(..., help="Field name.")) -> None:
        """Shows the value of a single field."""
        section_model = getattr(load_settings(), section)
        _resolve_field(field)
        console.print(getattr(section_model, field))

    @app.command("set")
    def config_set(
        assignment: str = typer.Argument(
            ...,
            help=(
                "FIELD=VALUE assignment, or just FIELD for secret fields — prompts for "
                "the value with hidden input instead of writing it in plain text in the command."
            ),
        ),
    ) -> None:
        """Changes the value of a field and saves it to settings.toml."""
        settings = load_settings()

        if "=" in assignment:
            field, raw_value = assignment.split("=", 1)
            field_info = _resolve_field(field)
        else:
            field = assignment
            field_info = _resolve_field(field)
            if not _is_secret_field(model, field):
                raise typer.BadParameter("Expected format: FIELD=VALUE.")
            raw_value = typer.prompt(f"Value of {field}", hide_input=True)

        try:
            parsed_value = _parse_value(field_info.annotation, raw_value)
            new_settings = _apply_update(settings, field, parsed_value)
        except ValidationError as e:
            console.print(f"[red]✘  Invalid value for {field}:[/red]\n{e}")
            raise typer.Exit(1)

        _save(new_settings)
        secret = _is_secret_field(model, field)
        new_value = getattr(getattr(new_settings, section), field)
        console.print(f"[green]✔  {section}.{field} = {_format_value(new_value, secret)}[/green]")

    @app.command("wizard")
    def config_wizard() -> None:
        """Interactive assistant: asks for each field of the section and saves the changes."""
        settings = load_settings()
        original_section_model = getattr(settings, section)

        console.print()
        console.print(Panel(
            f"This assistant asks for each field of the [bold]{section}[/bold] section of "
            "settings.toml, and saves the changes at the end.\n\n"
            "Each question shows the current value in brackets — press [bold]Enter[/bold] "
            "to keep it.",
            title=f"⚙️  {section} configuration assistant",
            border_style="cyan",
        ))
        if not typer.confirm("\nContinue?", default=True):
            console.print("[yellow]⚠ Cancelled. Nothing was changed.[/yellow]")
            raise typer.Exit(0)

        print_section(f"{section} fields")

        new_settings = settings
        for field in model.model_fields:
            value = _prompt_field(getattr(new_settings, section), field)
            new_settings = _apply_update(new_settings, field, value)
            secret = _is_secret_field(model, field)
            console.print(f"[green]✓[/green] {field}: [bold]{_format_value(value, secret)}[/bold]\n")

        print_section("Summary of changes")
        table = Table(title="Changes")
        table.add_column("Field")
        table.add_column("Previous value")
        table.add_column("New value")
        changed = False
        new_section_model = getattr(new_settings, section)
        for field in model.model_fields:
            old_value = getattr(original_section_model, field)
            new_value = getattr(new_section_model, field)
            if old_value != new_value:
                changed = True
                secret = _is_secret_field(model, field)
                table.add_row(field, _format_value(old_value, secret), _format_value(new_value, secret))

        if not changed:
            console.print("[yellow]⚠ No value was changed.[/yellow]")
            raise typer.Exit(0)

        console.print(table)
        if not typer.confirm("\nSave this configuration?", default=True):
            console.print("[yellow]⚠ Cancelled. Nothing was saved.[/yellow]")
            raise typer.Exit(0)

        _save(new_settings)
        console.print(f"[green]✔  Configuration saved to {DEFAULT_CONFIG_FILE}[/green]")

    return app
