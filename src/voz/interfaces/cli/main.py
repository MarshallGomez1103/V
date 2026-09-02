"""The ``voz`` command that runs the local application server."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, cast

import typer
import uvicorn

from voz.bootstrap import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
READINESS_TIMEOUT_SECONDS = 15.0


class HttpResponse(Protocol):
    """Small response contract used by the readiness probe."""

    status: int

    def read(self) -> bytes: ...


HttpOpen = Callable[..., AbstractContextManager[HttpResponse]]

app = typer.Typer(
    add_completion=False,
    help="Run the local-first VOZ transcription workspace.",
)


def browser_host(host: str) -> str:
    """Return a connectable host when Uvicorn binds a wildcard address."""
    normalized = host.strip()
    if normalized == "0.0.0.0":
        return "127.0.0.1"
    if normalized in {"::", "[::]"}:
        return "::1"
    return normalized


def server_url(host: str, port: int) -> str:
    """Build the URL used by the readiness check and browser."""
    connect_host = browser_host(host)
    if ":" in connect_host and not connect_host.startswith("["):
        connect_host = f"[{connect_host}]"
    return f"http://{connect_host}:{port}"


def is_server_ready(
    base_url: str,
    *,
    http_open: HttpOpen = urllib.request.urlopen,
) -> bool:
    """Return whether the VOZ health endpoint confirms readiness."""
    try:
        with http_open(f"{base_url}/api/health", timeout=0.5) as response:
            if response.status != 200:
                return False
            payload = cast(object, json.loads(response.read()))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    values = cast(dict[str, object], payload)
    return values.get("status") == "ok"


def wait_until_ready(
    base_url: str,
    *,
    timeout: float = READINESS_TIMEOUT_SECONDS,
    interval: float = 0.1,
    ready_check: Callable[[str], bool] = is_server_ready,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Poll readiness with a bounded wait."""
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if ready_check(base_url):
            return True
        sleep(interval)
    return False


def open_browser_after_ready(
    base_url: str,
    *,
    ready_wait: Callable[[str], bool] = wait_until_ready,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> bool:
    """Open the browser only after the local API reports itself ready."""
    if not ready_wait(base_url):
        return False
    return browser_open(base_url)


def start_browser_opener(base_url: str) -> threading.Thread:
    """Start a daemon that waits for readiness without blocking Uvicorn."""
    opener = threading.Thread(
        target=open_browser_after_ready,
        args=(base_url,),
        name="voz-browser-opener",
        daemon=True,
    )
    opener.start()
    return opener


def run_server(*, host: str, port: int, open_browser: bool) -> None:
    """Run Uvicorn in the foreground and stop cleanly on Ctrl+C."""
    base_url = server_url(host, port)
    if open_browser:
        start_browser_opener(base_url)

    config = uvicorn.Config(
        app=create_app(),
        host=host,
        port=port,
        log_level="info",
    )
    uvicorn.Server(config).run()


@app.command()
def serve(
    host: str = typer.Option(
        DEFAULT_HOST,
        "--host",
        help="Bind address. Use a LAN address only when exposure is intentional.",
        show_default=True,
    ),
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        min=1,
        max=65535,
        help="TCP port for the local server.",
        show_default=True,
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Do not open the web interface automatically.",
    ),
) -> None:
    """Start VOZ locally."""
    run_server(host=host, port=port, open_browser=not no_browser)


def main() -> None:
    """Console script entry point."""
    app()


if __name__ == "__main__":
    main()
