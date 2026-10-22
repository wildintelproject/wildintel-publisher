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


def _start_dir(initial_path: str | None) -> Path | None:
    """The nearest existing folder of `initial_path`; None when there's no
    path — the dialog then opens wherever the operating system decides."""
    if not initial_path:
        return None
    p = Path(initial_path).expanduser()
    while not p.is_dir():
        if p.parent == p:
            return None
        p = p.parent
    return p


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _command(title: str, start: Path | None) -> list[str]:
    if sys.platform == "darwin":
        location = f" default location (POSIX file {_applescript_string(str(start))})" if start else ""
        script = f"POSIX path of (choose folder with prompt {_applescript_string(title)}{location})"
        return ["osascript", "-e", script]
    if sys.platform == "win32":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description = '{title.replace(chr(39), chr(39) * 2)}'; "
            + (f"$d.SelectedPath = '{str(start).replace(chr(39), chr(39) * 2)}'; " if start else "")
            +
            "if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write($d.SelectedPath) }"
        )
        return ["powershell", "-NoProfile", "-STA", "-Command", script]
    if shutil.which("zenity"):
        command = ["zenity", "--file-selection", "--directory", f"--title={title}"]
        return command + [f"--filename={start}/"] if start else command
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", str(start or "."), "--title", title]
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


def open_directory(path: str) -> None:
    """Shows a folder in the operating system's file manager — the same machine as the browser, see the module docstring."""
    if sys.platform == "darwin":
        command = ["open", path]
    elif sys.platform.startswith("win"):
        command = ["explorer", path]
    else:
        command = ["xdg-open", path]
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise NativeDialogUnavailable(str(exc)) from exc
