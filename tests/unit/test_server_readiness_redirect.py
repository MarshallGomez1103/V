"""Readiness must never forward credentials to a redirected HTTP origin."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from voz.interfaces.cli.main import is_server_ready


@contextmanager
def _server(handler: type[BaseHTTPRequestHandler]) -> Generator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
        assert not thread.is_alive()


def test_readiness_rejects_cross_origin_redirect_without_forwarding_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    token = "synthetic_readiness_token_0123456789abcdef"
    received: list[str | None] = []
    paths: list[str] = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            received.append(self.headers.get("Authorization"))
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    with _server(Destination) as destination:
        target = f"http://127.0.0.1:{destination.server_port}/api/health"

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                paths.append(self.path)
                self.send_response(302)
                self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass

        with _server(Redirect) as source:
            ready = is_server_ready(
                f"http://127.0.0.1:{source.server_port}", auth_token=token
            )

    assert paths == ["/api/health"]
    leaked = f"Bearer {token}" in received
    assert (ready, len(received), leaked) == (False, 0, False)
