"""Entry point when running as a bundled executable (PyInstaller)."""
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from main import app  # import directo: funciona con módulos congelados por PyInstaller
from settings import settings

PORT_SCAN_SPAN = 100  # nº de puertos a probar a partir de settings.port si está ocupado


def _find_free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No hay ningún puerto libre entre {start} y {end}")


def _open_browser(port: int) -> None:
    time.sleep(1.8)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    port = _find_free_port(settings.port, settings.port + PORT_SCAN_SPAN - 1)
    print(f"Directorio de trabajo: {Path.cwd()}", flush=True)
    print(f"Servidor en http://127.0.0.1:{port}", flush=True)
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
