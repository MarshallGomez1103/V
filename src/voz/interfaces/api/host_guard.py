"""Reject requests whose ``Host`` header is not a name VOZ is served under.

A loopback bind alone does not stop DNS rebinding: a page on ``evil.example``
can re-resolve its own name to ``127.0.0.1`` and read the API same-origin. The
browser still sends ``Host: evil.example``, so checking it closes that door
(ADR-0006). Any port is accepted; only the host name matters.

It also refuses state changes and websocket handshakes that a page on another
origin could send without a CORS preflight (form posts, ``text/plain`` or
multipart ``fetch``). Requests without ``Origin`` and ``Sec-Fetch-Site`` come
from non-browser clients and keep working.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

from voz.interfaces.api.server_auth import parse_origin

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _body(code: str, message: str) -> bytes:
    return json.dumps({"detail": {"code": code, "message": message}}).encode()


_HOST_BODY = _body(
    "host_not_allowed", "This server only answers requests addressed to its own host."
)
_ORIGIN_BODY = _body(
    "origin_not_allowed", "This request comes from another origin and was refused."
)


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


def origin_allowed(
    method: str, scheme: str, headers: Iterable[tuple[bytes, bytes]]
) -> bool:
    """Decide whether a request may act, given its method and raw headers.

    ``method`` is ``"WEBSOCKET"`` for a handshake. Reads are always allowed. For
    the rest, a present ``Origin`` must equal the scheme, host and port the
    request was addressed to (``null`` and duplicates fail), and a present
    ``Sec-Fetch-Site`` must be ``same-origin`` or ``none``.
    """
    if method in _SAFE_METHODS:
        return True
    seen: dict[bytes, bytes] = {}
    for name, value in headers:
        name = name.lower()
        if name in {b"origin", b"host", b"sec-fetch-site"}:
            if name in seen:
                return False
            seen[name] = value
    if seen.get(b"sec-fetch-site", b"none") not in {b"same-origin", b"none"}:
        return False
    origin = seen.get(b"origin")
    if origin is None:
        return True
    scheme = {"ws": "http", "wss": "https"}.get(scheme, scheme)
    expected = parse_origin(scheme.encode("ascii") + b"://" + seen.get(b"host", b""))
    return expected is not None and parse_origin(origin) == expected


async def _refuse(scope: Scope, send: Send, status: int, body: bytes) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


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
        if normalize_host(raw) not in self.allowed:
            await _refuse(scope, send, 400, _HOST_BODY)
            return
        method = (
            "WEBSOCKET" if scope["type"] == "websocket" else scope.get("method", "POST")
        )
        if not origin_allowed(method, scope.get("scheme", "http"), scope["headers"]):
            await _refuse(scope, send, 403, _ORIGIN_BODY)
            return
        await self.app(scope, receive, send)
