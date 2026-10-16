"""The ``voz`` command that runs the local application server."""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from contextlib import AbstractContextManager
from functools import partial
from pathlib import Path
from typing import Annotated, Protocol, cast

import typer
import uvicorn

from voz.bootstrap import create_app
from voz.infrastructure.audio.ffmpeg_tools import ensure_ffmpeg
from voz.infrastructure.paths import resolve_voz_paths
from voz.infrastructure.server_token import (
    ServerTokenError,
    create_server_token,
    read_server_token,
)
from voz.interfaces.api.host_guard import LOOPBACK_HOSTS
from voz.interfaces.cli.bench import bench_command
from voz.interfaces.cli.diagnostics_bundle import build_bundle, write_bundle
from voz.interfaces.cli.doctor import exit_code, render, run_doctor
from voz.interfaces.cli.lab import lab_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
READINESS_TIMEOUT_SECONDS = 15.0


class HttpResponse(Protocol):
    """Small response contract used by the readiness probe."""

    status: int

    def read(self) -> bytes: ...


HttpOpen = Callable[..., AbstractContextManager[HttpResponse]]


class _NoReadinessRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


_READINESS_OPEN = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _NoReadinessRedirect()
).open

app = typer.Typer(
    add_completion=False,
    help="Run the local-first VOZ transcription workspace.",
)

app.add_typer(lab_app, name="lab")


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


def is_loopback_host(host: str) -> bool:
    """Return whether binding ``host`` keeps VOZ reachable only from this machine."""
    name = host.strip().strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def is_wildcard_host(host: str) -> bool:
    """Return whether ``host`` binds every interface."""
    return host.strip().strip("[]") in {"0.0.0.0", "::"}


def local_addresses() -> tuple[str, ...]:
    """Best-effort host name and IPs of this machine; empty if the resolver fails."""
    try:
        name = socket.gethostname()
        found: set[str] = {name} if name else set()
        for info in socket.getaddrinfo(name, None):
            found.add(str(info[4][0]).partition("%")[0])
    except OSError:
        return ()
    return tuple(sorted(found))


def exposure_warning(host: str, port: int) -> str:
    """Explain what a non-loopback bind exposes (ADR-0006)."""
    return (
        f"WARNING: VOZ is listening on {host}:{port}, not only on this machine. "
        "Access requires the server token. HTTP does not encrypt credentials, "
        "media or transcripts; use a trusted network or encrypted transport. "
        "See ADR-0006."
    )


def allowed_hosts_for(host: str, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Host names the guard accepts; a wildcard bind adds this machine's own."""
    allowed = [host, *extra]
    if is_wildcard_host(host):
        allowed += [*LOOPBACK_HOSTS, *local_addresses()]
    return tuple(allowed)


def is_server_ready(
    base_url: str,
    *,
    http_open: HttpOpen = _READINESS_OPEN,
    auth_token: str | None = None,
) -> bool:
    """Return whether the VOZ health endpoint confirms readiness."""
    try:
        target: str | urllib.request.Request = f"{base_url}/api/health"
        if auth_token is not None:
            target = urllib.request.Request(
                target, headers={"Authorization": f"Bearer {auth_token}"}
            )
        with http_open(target, timeout=0.5) as response:
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


def start_browser_opener(
    base_url: str, *, auth_token: str | None = None
) -> threading.Thread:
    """Start a daemon that waits for readiness without blocking Uvicorn."""
    opener = threading.Thread(
        target=open_browser_after_ready,
        args=(base_url,),
        kwargs={
            "ready_wait": partial(
                wait_until_ready,
                ready_check=partial(is_server_ready, auth_token=auth_token),
            )
        }
        if auth_token is not None
        else {},
        name="voz-browser-opener",
        daemon=True,
    )
    opener.start()
    return opener


def run_server(
    *,
    host: str,
    port: int,
    open_browser: bool,
    allow_hosts: tuple[str, ...] = (),
    auth_token_file: Path | None = None,
) -> None:
    """Run Uvicorn in the foreground and stop cleanly on Ctrl+C."""
    if auth_token_file is None and not is_loopback_host(host):
        raise typer.BadParameter(
            "LAN exposure requires --auth-token-file.", param_hint="--auth-token-file"
        )
    try:
        auth_token = (
            None if auth_token_file is None else read_server_token(auth_token_file)
        )
    except ServerTokenError as error:
        raise typer.BadParameter(str(error), param_hint="--auth-token-file") from None
    base_url = server_url(host, port)
    # A second double-click finds VOZ already serving: reuse it, don't crash.
    if (
        is_server_ready(base_url)
        if auth_token is None
        else is_server_ready(base_url, auth_token=auth_token)
    ):
        typer.echo(f"VOZ ya está abierto en {base_url}")
        if open_browser:
            webbrowser.open(base_url)
        return
    if not is_loopback_host(host):
        typer.echo(exposure_warning(host, port), err=True)
    if open_browser:
        if auth_token is None:
            start_browser_opener(base_url)
        else:
            start_browser_opener(base_url, auth_token=auth_token)

    servers: list[uvicorn.Server] = []

    def stop_server() -> None:
        """``POST /api/shutdown``: same graceful path as Ctrl+C."""
        for server in servers:
            server.should_exit = True

    config = uvicorn.Config(
        app=create_app(
            request_shutdown=stop_server,
            allowed_hosts=allowed_hosts_for(host, allow_hosts),
            auth_token=auth_token,
        ),
        host=host,
        port=port,
        log_level="info",
    )
    servers.append(uvicorn.Server(config))
    servers[0].run()


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
ALLOW_HOST_OPTION = typer.Option(
    None,
    "--allow-host",
    help="Extra Host name to accept, e.g. mi-pc.local. Repeatable.",
)
NO_BROWSER_OPTION = typer.Option(
    False,
    "--no-browser",
    help="Do not open the web interface automatically.",
)

AUTH_TOKEN_OPTION = typer.Option(
    None,
    "--auth-token-file",
    help="Private token file; required for any non-loopback bind.",
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
    allow_host: list[str] | None = ALLOW_HOST_OPTION,
    auth_token_file: Path | None = AUTH_TOKEN_OPTION,
) -> None:
    """Start VOZ locally; ``voz`` without a subcommand behaves like ``voz serve``."""
    prepare_ffmpeg()
    if ctx.invoked_subcommand is None:
        run_server(
            host=host,
            port=port,
            open_browser=not no_browser,
            allow_hosts=tuple(allow_host or ()),
            **(
                {"auth_token_file": auth_token_file}
                if auth_token_file is not None
                else {}
            ),
        )


@app.command()
def serve(
    host: str = HOST_OPTION,
    port: int = PORT_OPTION,
    no_browser: bool = NO_BROWSER_OPTION,
    allow_host: list[str] | None = ALLOW_HOST_OPTION,
    auth_token_file: Path | None = AUTH_TOKEN_OPTION,
) -> None:
    """Start VOZ locally."""
    run_server(
        host=host,
        port=port,
        open_browser=not no_browser,
        allow_hosts=tuple(allow_host or ()),
        **({"auth_token_file": auth_token_file} if auth_token_file is not None else {}),
    )


@app.command("auth-token")
def auth_token_command(output: Annotated[Path, typer.Option("--output")]) -> None:
    """Create a new private server token file without displaying its contents."""
    try:
        create_server_token(output)
    except ServerTokenError as error:
        raise typer.BadParameter(str(error), param_hint="--output") from None
    typer.echo("Private server token file created.")


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
