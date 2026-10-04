"""The operating system's own "choose a folder" dialog, for the directory
pickers of the web app — it runs on the same machine as the browser, so the
backend can open it (a web page can't: a browser never reveals the real path
of a folder the user picks). Each OS gets its own tool, none of them a
dependency of this project: zenity/kdialog on Linux, osascript on macOS,
PowerShell on Windows.

pick_directory returns None when the user cancels, and raises
NativeDialogUnavailable when there's nothing to open it with (a headless
server, a Linux without zenity/kdialog...) — the caller falls back to the
app's own in-page browser."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class NativeDialogUnavailable(RuntimeError):
    pass


def _start_dir(initial_path: str | None) -> Path:
    p = Path(initial_path).expanduser() if initial_path else Path.home()
    while not p.is_dir():
        if p.parent == p:
            return Path.home()
        p = p.parent
    return p


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _command(title: str, start: Path) -> list[str]:
    if sys.platform == "darwin":
        script = (
            f"POSIX path of (choose folder with prompt {_applescript_string(title)} "
            f"default location (POSIX file {_applescript_string(str(start))}))"
        )
        return ["osascript", "-e", script]
    if sys.platform == "win32":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description = '{title.replace(chr(39), chr(39) * 2)}'; "
            f"$d.SelectedPath = '{str(start).replace(chr(39), chr(39) * 2)}'; "
            "if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write($d.SelectedPath) }"
        )
        return ["powershell", "-NoProfile", "-STA", "-Command", script]
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", f"--title={title}", f"--filename={start}/"]
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", str(start), "--title", title]
    raise NativeDialogUnavailable("Neither zenity nor kdialog is installed.")


def pick_directory(initial_path: str | None = None, title: str = "Select the directory") -> str | None:
    """Blocks until the user chooses a folder or cancels."""
    command = _command(title, _start_dir(initial_path))
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise NativeDialogUnavailable(str(exc)) from exc
    chosen = result.stdout.strip()
    if result.returncode != 0 or not chosen:
        return None  # cancelled
    # osascript ends a folder's path with "/".
    return chosen[:-1] if len(chosen) > 1 and chosen.endswith("/") else chosen
