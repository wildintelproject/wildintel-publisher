# PyInstaller spec — the one every platform builds with (see `wpcli package build`).
# Run from the repository's root, after building the frontend (frontend/dist):
#
#   uv run pyinstaller wildintel-publisher.spec               # one file (.exe, .dmg)
#   WP_ONEDIR=1 uv run pyinstaller wildintel-publisher.spec   # a folder (AppImage)
#
# One executable for both apps: with no arguments, the web app; with any, the
# command-line one (see web/app_entry.py). The frontend is bundled as "static"
# (see web.main._static_dir), the Jinja templates as "templates"
# (see core.config.REPO_ROOT).
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

ONEDIR = os.environ.get("WP_ONEDIR") == "1"
NAME = "wildintel-publisher"
ROOT = Path(SPECPATH)
FRONTEND_DIST = ROOT / "frontend" / "dist"
if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit(f"{FRONTEND_DIST} has no build — run `npm run build` in frontend/ first.")

datas = [(str(FRONTEND_DIST), "static"), (str(ROOT / "templates"), "templates")]
binaries = []
hiddenimports = [
    *collect_submodules("uvicorn"),
    *collect_submodules("fastapi"),
    *collect_submodules("starlette"),
    *collect_submodules("trapper_client"),
    *collect_submodules("wildintel_publisher"),
    "anyio._backends._asyncio",
    "jinja2",
    "pydantic_settings",
    "typer",
    "yaml",
]

# Packages that carry data files / lazy imports of their own.
for package in ("frictionless", "huggingface_hub", "dynaconf"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
# boto3 (the S3 image upload) reads botocore's service definitions at runtime.
datas += collect_data_files("botocore")

for dist in ("wildintel-publisher", "wildintel-trapper-sdk"):
    try:
        datas += copy_metadata(dist)
    except Exception:  # not installed as a distribution — nothing to copy
        pass

a = Analysis(
    ["src/wildintel_publisher/web/app_entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter"],
)
pyz = PYZ(a.pure)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=True)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=True)
