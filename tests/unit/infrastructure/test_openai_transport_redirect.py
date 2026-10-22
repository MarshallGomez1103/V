"""The default HTTP transport never follows a redirect (the key stays put)."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from voz.infrastructure.cloud.openai_transport import HttpRequest, urllib_transport


@contextmanager
def _serve(handler: type[BaseHTTPRequestHandler]) -> Generator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_a_redirect_is_returned_not_followed_and_sends_nothing_elsewhere(
    status: int, method: str
) -> None:
    seen: list[str | None] = []
    first: list[str | None] = []

    class Destination(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _record(self) -> None:
            seen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _record

    with _serve(Destination) as destination:

        class Bounce(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                del format, args

            def _bounce(self) -> None:
                first.append(self.headers.get("Authorization"))
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(status)
                self.send_header("Location", destination + "/stolen")
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = _bounce

        with _serve(Bounce) as origin:
            reply = urllib_transport(
                HttpRequest(
                    origin + "/v1/x",
                    {"Authorization": "Bearer K"},
                    b"" if method == "GET" else b"audio",
                    5,
                    method=method,
                )
            )

    assert reply.status == status
    assert first == ["Bearer K"]
    assert seen == []  # the second origin never saw a request
