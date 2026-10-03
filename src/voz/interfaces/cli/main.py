"""The ``voz`` command that runs the local application server."""

from __future__ import annotations

import dataclasses
import json
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, cast

import typer
import uvicorn

from voz.bootstrap import create_app
from voz.infrastructure.audio.ffmpeg_tools import ensure_ffmpeg
from voz.infrastructure.paths import resolve_voz_paths
from voz.interfaces.cli.bench import bench_command
from voz.interfaces.cli.diagnostics_bundle import build_bundle, write_bundle
from voz.interfaces.cli.doctor import exit_code, render, run_doctor

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
    # A second double-click finds VOZ already serving: reuse it, don't crash.
    if is_server_ready(base_url):
        typer.echo(f"VOZ ya está abierto en {base_url}")
        if open_browser:
            webbrowser.open(base_url)
        return
    if open_browser:
        start_browser_opener(base_url)

    config = uvicorn.Config(
        app=create_app(),
        host=host,
        port=port,
        log_level="info",
    )
    uvicorn.Server(config).run()


HOST_OPTION = typer.Option(
    DEFAULT_HOST,
    "--host",
    help="Bind address. Use a LAN address only when exposure is intentional.",
    show_default=True,
)
PORT_OPTION = typer.Option(
    DEFAULT_PORT,
    "--port",
    min=1,
    max=65535,
    help="TCP port for the local server.",
    show_default=True,
)
NO_BROWSER_OPTION = typer.Option(
    False,
    "--no-browser",
    help="Do not open the web interface automatically.",
)


BUNDLE_OPTION = typer.Option(
    None,
    "--bundle",
    dir_okay=False,
    help="Write a redacted diagnostics zip (no media, names or transcripts).",
)


def prepare_ffmpeg() -> None:
    """Put FFmpeg/ffprobe on PATH, downloading a pinned build once if absent."""
    result = ensure_ffmpeg(announce=lambda message: typer.echo(message, err=True))
    if result.status in {"failed", "unsupported"}:
        typer.echo(result.message, err=True)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    host: str = HOST_OPTION,
    port: int = PORT_OPTION,
    no_browser: bool = NO_BROWSER_OPTION,
) -> None:
    """Start VOZ locally; ``voz`` without a subcommand behaves like ``voz serve``."""
    prepare_ffmpeg()
    if ctx.invoked_subcommand is None:
        run_server(host=host, port=port, open_browser=not no_browser)


@app.command()
def serve(
    host: str = HOST_OPTION,
    port: int = PORT_OPTION,
    no_browser: bool = NO_BROWSER_OPTION,
) -> None:
    """Start VOZ locally."""
    run_server(host=host, port=port, open_browser=not no_browser)


@app.command()
def doctor(
    host: str = HOST_OPTION,
    port: int = PORT_OPTION,
    json_output: bool = typer.Option(
        False, "--json", help="Emit the report as JSON instead of a table."
    ),
    redact: bool = typer.Option(
        False, "--redact", help="Hide absolute local paths from the report."
    ),
    bundle: Path | None = BUNDLE_OPTION,
) -> None:
    """Check FFmpeg, port, XDG paths, disk, models, ASR, GPU and optional API keys.

    Never loads a model or calls a provider.
    """
    paths = resolve_voz_paths()
    report = run_doctor(
        host=host, port=port, paths=paths, redact=redact or bool(bundle)
    )
    if json_output:
        typer.echo(json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2))
    else:
        typer.echo(render(report))
    if bundle is not None:
        try:
            write_bundle(bundle, build_bundle(report, paths=paths))
        except OSError as error:
            typer.echo(
                f"No se pudo escribir el bundle: {type(error).__name__}", err=True
            )
            raise typer.Exit(code=2) from error
        typer.echo(f"Bundle de diagnóstico escrito en {bundle}", err=json_output)
    raise typer.Exit(code=exit_code(report))


app.command(name="bench")(bench_command)


def main() -> None:
    """Console script entry point."""
    # Windows consoles may use a legacy code page: never crash on a character.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    app()


if __name__ == "__main__":
    main()
