"""Reject requests whose ``Host`` header is not a name VOZ is served under.

A loopback bind alone does not stop DNS rebinding: a page on ``evil.example``
can re-resolve its own name to ``127.0.0.1`` and read the API same-origin. The
browser still sends ``Host: evil.example``, so checking it closes that door
(ADR-0006). Any port is accepted; only the host name matters.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_BODY = json.dumps(
    {
        "detail": {
            "code": "host_not_allowed",
            "message": "This server only answers requests addressed to its own host.",
        }
    }
).encode()


def normalize_host(value: str) -> str | None:
    """Return the lowercase host without port or IPv6 brackets, or ``None``."""
    host = value.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        rest = host[end + 1 :]
        if end < 0 or (rest and not rest.startswith(":")):
            return None
        return host[1:end] or None
    if host.count(":") == 1:
        host = host.partition(":")[0]
    return host or None


class HostGuardMiddleware:
    """Pure ASGI middleware, so SSE and file streaming pass through untouched."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: Iterable[str]) -> None:
        self.app = app
        self.allowed = {
            host for host in map(normalize_host, allowed_hosts) if host is not None
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        raw = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
        if normalize_host(raw) in self.allowed:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 400,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY})
