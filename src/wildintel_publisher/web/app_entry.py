"""Entry point when running as a bundled executable (PyInstaller): with no
arguments, the web app; with any, the command-line app — one executable for
both (`wildintel-publisher trapper --help`)."""
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

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


def _serve() -> None:
    # Imported here: the web app sets up the log for itself — the
    # command-line app, its own way.
    from wildintel_publisher.web.main import app
    from wildintel_publisher.web.settings import settings

    port = _find_free_port(settings.port, settings.port + PORT_SCAN_SPAN - 1)
    print(f"Servidor en http://127.0.0.1:{port}", flush=True)
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    # log_config=None: uvicorn's loggers go through the app's own handlers
    # (console + log file, see wildintel_publisher.core.logging_setup), at its level.
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None, log_level=None)


if __name__ == "__main__":
    if sys.argv[1:]:
        from wildintel_publisher.cli.app import app as cli_app

        cli_app()
    else:
        _serve()
