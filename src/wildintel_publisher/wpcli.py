"""
WildINTEL Publisher — CLI de gestión.

Se llama wpcli (y no cli) porque wildintel-trapper-sdk, instalado en el mismo
entorno, ya trae su propio módulo y comando "cli".

Uso:
    uv run wpcli dev [--backend-port 8767] [--frontend-port 5174]
    uv run wpcli backend serve [dev|prod|debug] [--port 8767]
    uv run wpcli backend test [-v] [-k filtro]
    uv run wpcli frontend dev|build|preview|test|lint
    uv run wpcli docs serve|build|pdf
    uv run wpcli test [unit|integration|web|all] [-v] [-k filtro]
    uv run wpcli package build [--format auto|appimage|windows|macos] [--version 0.1.0]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from wildintel_publisher.web.settings import settings

# ── Constantes ────────────────────────────────────────────────────────────────

# src/wildintel_publisher/wpcli.py → the repository's root.
ROOT_DIR      = Path(__file__).resolve().parents[2]
PACKAGE_DIR   = ROOT_DIR / "src" / "wildintel_publisher"
BUILD_DIR     = ROOT_DIR / "build"
FRONTEND_DIR  = ROOT_DIR / "frontend"
DIST_DIR      = ROOT_DIR / "dist"
MKDOCS_CFG    = ROOT_DIR / "mkdocs.yml"
SITE_DIR      = ROOT_DIR / "site"
SPEC_FILE     = ROOT_DIR / "wildintel-publisher.spec"
ICON          = ROOT_DIR / "docs" / "img" / "WildINTEL_onlyCircle_25.png"
APP_NAME      = "wildintel-publisher"
FRONTEND_PORT = 5174

# Tiene que coincidir con plugins.with-pdf.enabled_if_env y .output_path en
# mkdocs.yml — el plugin genera el PDF durante 'mkdocs build' solo si esta
# variable vale "1"; el resto de builds (docs serve/build normales) no pagan
# el coste de renderizar cada página con WeasyPrint.
PDF_ENV_VAR   = "ENABLE_PDF_EXPORT"
PDF_REL_PATH  = "pdf/wildintel-publisher.pdf"

console = Console()
app     = typer.Typer(help="WildINTEL Publisher — herramienta de gestión.")


# ── Enums ─────────────────────────────────────────────────────────────────────

class ServeMode(str, Enum):
    dev   = "dev"
    prod  = "prod"
    debug = "debug"


class TestSuite(str, Enum):
    unit        = "unit"
    integration = "integration"
    web         = "web"
    all         = "all"


class PackageFormat(str, Enum):
    auto     = "auto"
    appimage = "appimage"
    windows  = "windows"
    macos    = "macos"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(*args: str, cwd: Path | None = None, env: dict | None = None) -> None:
    result = subprocess.run(list(args), cwd=cwd or ROOT_DIR, env=env)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _require(tool: str, hint: str) -> None:
    if shutil.which(tool) is None:
        console.print(f"[red]✘  '{tool}' no encontrado.[/red]  {hint}")
        raise typer.Exit(1)


def _ensure_frontend_deps() -> None:
    """`npm install` es fácil de olvidar (no lo marca `_require`, que solo
    comprueba que el propio `npm` exista) — si falta, 'npm run dev' falla a
    medias con 'vite: orden no encontrada' en vez de un error claro. Se
    comprueba/instala aquí, antes de cualquier comando `npm` del frontend,
    para que este paso nunca dependa de que alguien haya leído el README."""
    if (FRONTEND_DIR / "node_modules").is_dir():
        return
    console.print("[yellow]No existe frontend/node_modules — instalando dependencias (npm install)...[/yellow]")
    _run("npm", "install", cwd=FRONTEND_DIR)


def _npm(*args: str) -> None:
    _require("npm", "Instala Node.js desde https://nodejs.org/ (v18+)")
    _ensure_frontend_deps()
    _run("npm", *args, cwd=FRONTEND_DIR)


def _uvicorn_args(port: int, *, reload: bool) -> list[str]:
    args = ["uvicorn", "wildintel_publisher.web.main:app", "--port", str(port)]
    if reload:
        # PACKAGE_DIR cubre core/, cli/ y web/: editar cualquiera recarga el backend.
        return [*args, "--reload", "--reload-dir", str(PACKAGE_DIR), "--log-level", settings.log_level.lower()]
    return [*args, "--log-level", "warning", "--workers", "2"]


# ── docs (manuales de usuario y desarrollador) ───────────────────────────────

docs_app = typer.Typer(help="Genera o sirve la documentación del proyecto.")
app.add_typer(docs_app, name="docs")


@docs_app.command("serve")
def docs_serve(
    port: int = typer.Option(8000, "--port", "-p", help="Puerto del servidor de documentación."),
) -> None:
    """Sirve la documentación en local con recarga automática (http://127.0.0.1:<port>)."""
    console.print(f"[green]Documentación en http://127.0.0.1:{port}[/green]\n")
    _run("mkdocs", "serve", "--config-file", str(MKDOCS_CFG), "--dev-addr", f"127.0.0.1:{port}")


@docs_app.command("build")
def docs_build() -> None:
    """Genera el sitio estático de la documentación en site/."""
    console.print("[green]Generando documentación...[/green]")
    _run("mkdocs", "build", "--config-file", str(MKDOCS_CFG))
    console.print(f"[green]✔  Sitio generado en {SITE_DIR}[/green]")


@docs_app.command("pdf")
def docs_pdf() -> None:
    """Genera un único PDF con toda la documentación (site/pdf/wildintel-publisher.pdf).

    Es el mismo 'mkdocs build' de siempre, con el plugin mkdocs-with-pdf
    activado solo para esta ejecución (vía la variable de entorno
    ENABLE_PDF_EXPORT) — recorre el nav de mkdocs.yml en orden y renderiza
    cada página con WeasyPrint, con portada e índice incluidos.
    """
    console.print("[green]Generando documentación en PDF (WeasyPrint)...[/green]")
    _run("mkdocs", "build", "--config-file", str(MKDOCS_CFG), env={**os.environ, PDF_ENV_VAR: "1"})

    pdf_path = SITE_DIR / PDF_REL_PATH
    if not pdf_path.is_file():
        console.print(f"[red]✘  mkdocs build terminó bien pero no encuentro {pdf_path}.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✔  PDF generado en {pdf_path}[/green]")


@docs_app.command("screenshots")
def docs_screenshots(
    build: bool = typer.Option(True, "--build/--no-build", help="Compilar antes el frontend."),
) -> None:
    """Regenera las capturas del manual web (docs/img/web/) con datos de ejemplo
    — el backend simulado en la página: sin Trapper, sin cuentas reales."""
    if build:
        _npm("run", "build")
    _npm("run", "screenshots")


# ── test ──────────────────────────────────────────────────────────────────────

def _pytest(suite: TestSuite, verbose: bool, keyword: str | None) -> None:
    paths = {
        TestSuite.unit: ["tests/unit/"],
        TestSuite.integration: ["tests/integration/"],
        TestSuite.web: ["tests/web/"],
        TestSuite.all: ["tests/"],
    }[suite]

    console.print(Panel(
        f"[bold]Suite:[/bold] {suite.value}   [bold]Paths:[/bold] {', '.join(paths)}",
        title="WildINTEL Publisher — tests",
    ))

    cmd = [sys.executable, "-m", "pytest", *paths]
    if verbose:
        cmd.append("-v")
    if keyword:
        cmd.extend(["-k", keyword])
    _run(*cmd)


@app.command("test")
def test(
    suite: TestSuite = typer.Argument(TestSuite.all, help="Suite a ejecutar."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Salida detallada (-v de pytest)."),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Filtro de tests por nombre (-k de pytest)."),
) -> None:
    """Ejecuta los tests del proyecto con pytest (CLI y backend web)."""
    _pytest(suite, verbose, keyword)


# ── backend ───────────────────────────────────────────────────────────────────

backend_app = typer.Typer(help="Gestiona el backend FastAPI.")
app.add_typer(backend_app, name="backend")


@backend_app.command("serve")
def backend_serve(
    mode: ServeMode = typer.Argument(ServeMode.dev, help="Modo de ejecución."),
    port: int       = typer.Option(None, "--port", "-p", help="Puerto (por defecto: WILDINTEL_PUBLISHER_WEB_PORT o 8767)."),
) -> None:
    """Arranca el servidor FastAPI en el modo indicado."""
    effective_port = port or settings.port
    console.print(Panel(
        f"[bold]Modo:[/bold] {mode.value}   [bold]Puerto:[/bold] {effective_port}",
        title="WildINTEL Publisher — backend",
    ))

    if mode == ServeMode.debug:
        _require("debugpy", "Instala las dependencias de desarrollo: uv sync --group dev")
        console.print(f"  API:      http://localhost:{effective_port}")
        console.print(f"  Swagger:  http://localhost:{effective_port}/docs")
        console.print("  Debugger: localhost:5678\n")
        _run(
            sys.executable, "-m", "debugpy", "--listen", "5678",
            "-m", "uvicorn", "wildintel_publisher.web.main:app", "--port", str(effective_port),
            "--log-level", "debug",
        )
        return

    console.print(f"  API:     http://localhost:{effective_port}")
    console.print(f"  Swagger: http://localhost:{effective_port}/docs\n")
    _run(*_uvicorn_args(effective_port, reload=mode == ServeMode.dev))


@backend_app.command("test")
def backend_test(
    verbose: bool       = typer.Option(False, "--verbose", "-v", help="Salida detallada (-v de pytest)."),
    keyword: str | None = typer.Option(None, "--keyword", "-k", help="Filtro de tests por nombre (-k de pytest)."),
) -> None:
    """Ejecuta todos los tests de Python (core, CLI y backend web) con pytest."""
    _pytest(TestSuite.all, verbose, keyword)


# ── frontend ──────────────────────────────────────────────────────────────────

frontend_app = typer.Typer(help="Gestiona el frontend React (npm).")
app.add_typer(frontend_app, name="frontend")


@frontend_app.command("dev")
def frontend_dev(
    port: int = typer.Option(FRONTEND_PORT, "--port", "-p", help="Puerto del servidor de desarrollo."),
) -> None:
    """Arranca el servidor de desarrollo Vite (hot-reload)."""
    console.print(Panel(f"[bold]Frontend:[/bold] http://localhost:{port}", title="WildINTEL Publisher — frontend dev"))
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
    console.print(Panel(f"[bold]Preview:[/bold] http://localhost:{port}", title="WildINTEL Publisher — frontend preview"))
    _npm("run", "preview", "--", "--port", str(port))


@frontend_app.command("test")
def frontend_test() -> None:
    """Ejecuta los tests del frontend (Vitest)."""
    console.print(Panel("Ejecutando tests del frontend...", title="WildINTEL Publisher — frontend tests"))
    _npm("run", "test")


@frontend_app.command("lint")
def frontend_lint() -> None:
    """Ejecuta oxlint sobre el código fuente."""
    console.print("[green]Linting...[/green]")
    _npm("run", "lint")


# ── dev (backend + frontend juntos) ──────────────────────────────────────────

@app.command()
def dev(
    backend_port:  int = typer.Option(None, "--backend-port", "-b", help="Puerto del backend (por defecto: WILDINTEL_PUBLISHER_WEB_PORT o 8767)."),
    frontend_port: int = typer.Option(FRONTEND_PORT, "--frontend-port", "-f", help="Puerto del frontend Vite."),
) -> None:
    """Arranca backend y frontend simultáneamente en modo desarrollo."""
    _require("npm", "Instala Node.js desde https://nodejs.org/ (v18+)")
    _ensure_frontend_deps()
    effective_port = backend_port or settings.port

    console.print(Panel(
        f"  [bold]Backend:[/bold]  http://localhost:{effective_port}\n"
        f"  [bold]Frontend:[/bold] http://localhost:{frontend_port}\n"
        f"  [bold]API docs:[/bold] http://localhost:{effective_port}/docs\n\n"
        f"  Ctrl+C para detener ambos procesos.",
        title="WildINTEL Publisher — dev",
    ))

    backend_proc = subprocess.Popen(
        _uvicorn_args(effective_port, reload=True), cwd=ROOT_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(frontend_port)], cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    def _stream(proc: subprocess.Popen, label: str, color: str) -> None:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode(errors="replace").rstrip()
            if line:
                console.print(f"[{color}][{label}][/{color}] {line}")

    for proc, label, color in ((backend_proc, "backend", "cyan"), (frontend_proc, "frontend", "green")):
        threading.Thread(target=_stream, args=(proc, label, color), daemon=True).start()

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


# ── package ───────────────────────────────────────────────────────────────────

package_app = typer.Typer(help="Construye los paquetes de distribución (.AppImage / .exe / .dmg).")
app.add_typer(package_app, name="package")

# Cada formato se construye en su propio sistema: PyInstaller no hace
# compilación cruzada.
_NATIVE = {"linux": PackageFormat.appimage, "win32": PackageFormat.windows, "darwin": PackageFormat.macos}


def _get_version(version: str | None) -> str:
    if version:
        return version
    result = subprocess.run(
        ["git", "describe", "--tags", "--exact-match"], capture_output=True, text=True, cwd=ROOT_DIR,
    )
    if result.returncode == 0:
        return result.stdout.strip().lstrip("v")
    return "0.0.0-dev"


def _pyinstaller(*, onedir: bool) -> Path:
    """Compila el frontend y el ejecutable (un solo binario: sin argumentos
    arranca la web; con ellos, la CLI). Devuelve lo generado."""
    _npm("run", "build")
    env = {k: v for k, v in os.environ.items() if k != "WP_ONEDIR"}
    if onedir:
        env["WP_ONEDIR"] = "1"
    _run(sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm",
         "--distpath", str(BUILD_DIR / "dist"), "--workpath", str(BUILD_DIR / "work"), env=env)
    return BUILD_DIR / "dist" / (APP_NAME + (".exe" if sys.platform == "win32" and not onedir else ""))


def _report(path: Path) -> None:
    console.print(f"[green]✔  {path}  ({path.stat().st_size // (1024 * 1024)} MB)[/green]")


def _build_appimage(version: str) -> None:
    _require("appimagetool", "Descárgalo de https://github.com/AppImage/appimagetool/releases y ponlo en el PATH.")
    built = _pyinstaller(onedir=True)
    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp) / "AppDir"
        shutil.copytree(built, app_dir / APP_NAME)
        (app_dir / "AppRun").write_text(f'#!/bin/sh\nexec "$(dirname "$0")/{APP_NAME}/{APP_NAME}" "$@"\n')
        (app_dir / "AppRun").chmod(0o755)
        (app_dir / f"{APP_NAME}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName=WildINTEL Publisher\n"
            f"Exec={APP_NAME}\nIcon={APP_NAME}\nTerminal=true\nCategories=Science;\n"
        )
        shutil.copy(ICON, app_dir / f"{APP_NAME}.png")
        out = DIST_DIR / f"{APP_NAME}-{version}-linux-x86_64.AppImage"
        _run("appimagetool", str(app_dir), str(out), env={**os.environ, "ARCH": "x86_64"})
    _report(out)


def _build_windows(version: str) -> None:
    built = _pyinstaller(onedir=False)
    out = DIST_DIR / f"{APP_NAME}-{version}-windows-x64.exe"
    shutil.copy(built, out)
    _report(out)


def _build_macos(version: str) -> None:
    _require("hdiutil", "hdiutil solo existe en macOS.")
    built = _pyinstaller(onedir=False)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(built, Path(tmp) / APP_NAME)
        out = DIST_DIR / f"{APP_NAME}-{version}-macos-arm64.dmg"
        _run("hdiutil", "create", "-volname", f"WildINTEL Publisher {version}", "-srcfolder", tmp,
             "-ov", "-format", "UDZO", str(out))
    _report(out)


@package_app.command("build")
def package_build(
    fmt: PackageFormat = typer.Option(PackageFormat.auto, "--format", "-f",
                                      help="Formato: auto (el de este sistema), appimage, windows o macos."),
    version: str | None = typer.Option(None, "--version", "-v",
                                       help="Versión (por defecto: el tag de git, o 0.0.0-dev)."),
) -> None:
    """Construye el paquete de este sistema en dist/."""
    native = _NATIVE.get(sys.platform)
    target = native if fmt == PackageFormat.auto else fmt
    if target is None or target != native:
        console.print(f"[red]✘  {fmt.value} no se puede construir en este sistema ({sys.platform}).[/red]  "
                      "Cada paquete se construye en su propio sistema.")
        raise typer.Exit(1)

    v = _get_version(version)
    console.print(Panel(f"[bold]Versión:[/bold] {v}   [bold]Formato:[/bold] {target.value}",
                        title="WildINTEL Publisher — package"))
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    {PackageFormat.appimage: _build_appimage, PackageFormat.windows: _build_windows,
     PackageFormat.macos: _build_macos}[target](v)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
