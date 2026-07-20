"""
wildintel-publisher-web — CLI de gestión.

Uso:
    uv run cli backend serve [dev|prod]
    uv run cli backend test
    uv run cli frontend dev
    uv run cli frontend build
    uv run cli frontend preview
    uv run cli frontend lint
    uv run cli frontend test
    uv run cli dev
"""
import subprocess
import sys
import threading
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))
from settings import settings  # noqa: E402

# ── Constantes ────────────────────────────────────────────────────────────────

ROOT_DIR     = Path(__file__).parent
BACKEND_DIR  = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

console = Console()
app     = typer.Typer(help="wildintel-publisher-web — herramienta de gestión.")


class ServeMode(str, Enum):
    dev  = "dev"
    prod = "prod"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(*args: str, cwd: Path | None = None) -> None:
    result = subprocess.run(list(args), cwd=cwd)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _require(tool: str, hint: str) -> None:
    if subprocess.run(["which", tool], capture_output=True).returncode != 0:
        console.print(f"[red]✘  '{tool}' no encontrado.[/red]  {hint}")
        raise typer.Exit(1)


def _npm(*args: str) -> None:
    _require("npm", "Instala Node.js desde https://nodejs.org/ (v18+)")
    _run("npm", *args, cwd=FRONTEND_DIR)


# ── backend ───────────────────────────────────────────────────────────────────

backend_app = typer.Typer(help="Gestiona el backend FastAPI.")
app.add_typer(backend_app, name="backend")


@backend_app.command("serve")
def backend_serve(
    mode: ServeMode = typer.Argument(ServeMode.dev, help="Modo de ejecución."),
    port: int       = typer.Option(None, "--port", "-p", help="Puerto de escucha (por defecto: WILDINTEL_PUBLISHER_WEB_PORT o 8767)."),
) -> None:
    """Arranca el servidor FastAPI en el modo indicado."""
    effective_port = port or settings.port
    console.print(Panel(
        f"[bold]Modo:[/bold] {mode.value}   [bold]Puerto:[/bold] {effective_port}",
        title="wildintel-publisher-web — backend",
    ))

    if mode == ServeMode.dev:
        console.print(f"  API:     http://localhost:{effective_port}")
        console.print(f"  Swagger: http://localhost:{effective_port}/docs\n")
        _run("uvicorn", "main:app", "--reload", "--port", str(effective_port),
             "--log-level", settings.log_level.lower(), "--app-dir", "src",
             cwd=BACKEND_DIR)
    else:
        console.print(f"  API:     http://localhost:{effective_port}\n")
        _run("uvicorn", "main:app", "--port", str(effective_port),
             "--log-level", "warning", "--workers", "2", "--app-dir", "src",
             cwd=BACKEND_DIR)


@backend_app.command("test")
def backend_test(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Salida detallada (-v de pytest)."),
    keyword: str | None = typer.Option(None, "--keyword", "-k", help="Filtro de tests por nombre (-k de pytest)."),
) -> None:
    """Ejecuta los tests del backend con pytest."""
    console.print(Panel("Ejecutando tests del backend...", title="wildintel-publisher-web — backend tests"))
    cmd = [sys.executable, "-m", "pytest"]
    if verbose:
        cmd.append("-v")
    if keyword:
        cmd.extend(["-k", keyword])
    _run(*cmd, cwd=ROOT_DIR)


# ── frontend ──────────────────────────────────────────────────────────────────

frontend_app = typer.Typer(help="Gestiona el frontend React (npm).")
app.add_typer(frontend_app, name="frontend")


@frontend_app.command("dev")
def frontend_dev(
    port: int = typer.Option(5174, "--port", "-p", help="Puerto del servidor de desarrollo."),
) -> None:
    """Arranca el servidor de desarrollo Vite (hot-reload)."""
    console.print(Panel(
        f"[bold]Frontend:[/bold] http://localhost:{port}",
        title="wildintel-publisher-web — frontend dev",
    ))
    _npm("run", "dev", "--", "--port", str(port))


@frontend_app.command("build")
def frontend_build() -> None:
    """Compila el frontend para producción → frontend/dist/."""
    console.print("[green]Compilando frontend...[/green]")
    _npm("run", "build")
    console.print(f"[green]✔  Build en {FRONTEND_DIR / 'dist'}[/green]")


@frontend_app.command("preview")
def frontend_preview(
    port: int = typer.Option(4174, "--port", "-p", help="Puerto del servidor de preview."),
) -> None:
    """Sirve el build de producción localmente."""
    console.print(Panel(
        f"[bold]Preview:[/bold] http://localhost:{port}",
        title="wildintel-publisher-web — frontend preview",
    ))
    _npm("run", "preview", "--", "--port", str(port))


@frontend_app.command("test")
def frontend_test() -> None:
    """Ejecuta los tests del frontend (Vitest)."""
    console.print(Panel("Ejecutando tests del frontend...", title="wildintel-publisher-web — frontend tests"))
    _npm("run", "test")


@frontend_app.command("lint")
def frontend_lint() -> None:
    """Ejecuta oxlint sobre el código fuente."""
    console.print("[green]Linting...[/green]")
    _npm("run", "lint")


# ── dev (backend + frontend juntos) ──────────────────────────────────────────

@app.command()
def dev(
    backend_port:  int = typer.Option(None, "--backend-port",  "-b", help="Puerto del backend (por defecto: WILDINTEL_PUBLISHER_WEB_PORT o 8767)."),
    frontend_port: int = typer.Option(5174, "--frontend-port", "-f", help="Puerto del frontend Vite."),
) -> None:
    """Arranca backend y frontend simultáneamente en modo desarrollo."""
    _require("npm", "Instala Node.js desde https://nodejs.org/ (v18+)")
    effective_port = backend_port or settings.port

    console.print(Panel(
        f"  [bold]Backend:[/bold]  http://localhost:{effective_port}\n"
        f"  [bold]Frontend:[/bold] http://localhost:{frontend_port}\n"
        f"  [bold]API docs:[/bold] http://localhost:{effective_port}/docs\n\n"
        f"  Ctrl+C para detener ambos procesos.",
        title="wildintel-publisher-web — dev",
    ))

    backend_proc = subprocess.Popen(
        ["uvicorn", "main:app", "--reload", "--port", str(effective_port),
         "--log-level", settings.log_level.lower(), "--app-dir", "src"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(frontend_port)],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    def _stream(proc: subprocess.Popen, label: str, color: str) -> None:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode(errors="replace").rstrip()
            if line:
                console.print(f"[{color}][{label}][/{color}] {line}")

    threads = [
        threading.Thread(target=_stream, args=(backend_proc,  "backend",  "cyan"),  daemon=True),
        threading.Thread(target=_stream, args=(frontend_proc, "frontend", "green"), daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        console.print("\n[yellow]Deteniendo...[/yellow]")
        for proc in (backend_proc, frontend_proc):
            proc.terminate()
        for proc in (backend_proc, frontend_proc):
            proc.wait()
        console.print("[yellow]✔  Parado.[/yellow]")


if __name__ == "__main__":
    app()
