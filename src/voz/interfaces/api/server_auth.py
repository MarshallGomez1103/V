"""Optional local server authentication at the ASGI boundary."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import re
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,512}", re.ASCII)
_AUTHORITY = re.compile(r"(?:[a-zA-Z0-9.-]+|\[[0-9a-fA-F:.]+\])(?::[0-9]{1,5})?")
_SECURITY_HEADERS = {b"authorization", b"origin", b"host", b"sec-fetch-site"}
_BODY = json.dumps(
    {
        "detail": {
            "code": "server_auth_required",
            "message": "Valid server credentials are required.",
        }
    }
).encode("ascii")


def _origin(raw: bytes) -> tuple[str, str, int] | None:
    """Parse an ASCII HTTP origin without accepting URL paths or user info."""
    if not raw or any(byte <= 32 or byte >= 127 for byte in raw):
        return None
    try:
        parsed = urlsplit(raw.decode("ascii"))
        if (
            parsed.scheme not in {"http", "https"}
            or _AUTHORITY.fullmatch(parsed.netloc) is None
            or parsed.path
            or b"?" in raw
            or b"#" in raw
            or parsed.hostname is None
        ):
            return None
        port = parsed.port
        return (
            parsed.scheme,
            parsed.hostname,
            (port if port is not None else (443 if parsed.scheme == "https" else 80)),
        )
    except ValueError:
        return None


class ServerAuthTokenError(ValueError):
    """Invalid server token configuration, safe to display."""

    code = "server_auth_token_invalid"


class ServerAuthMiddleware:
    """Bearer for API clients; Basic ``v:token`` for the browser.

    Basic state changes require a same-origin Origin. HostGuard must still
    restrict allowed host names; forwarded headers are not trusted here.
    ``None`` preserves all scopes, including loopback requests without auth.
    """

    __slots__ = ("_token", "app")

    def __init__(self, app: ASGIApp, *, token: str | None = None) -> None:
        if token is not None and _TOKEN.fullmatch(token) is None:
            raise ServerAuthTokenError(
                "The server token must be 32-512 URL-safe ASCII characters."
            )
        self.app = app
        self._token = None if token is None else token.encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            self._token is None
            or scope["type"] not in {"http", "websocket"}
            or self._authorized(scope)
        ):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_BODY)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"www-authenticate", b'Basic realm="V", charset="UTF-8"'),
                    (b"www-authenticate", b'Bearer realm="V"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY})

    def _authorized(self, scope: Scope) -> bool:
        headers: dict[bytes, bytes] = {}
        for name, value in scope["headers"]:
            name = name.lower()
            if name in _SECURITY_HEADERS:
                if name in headers or len(value) > 1024:
                    return False
                headers[name] = value
        raw = headers.get(b"authorization", b"")
        if any(byte < 32 or byte >= 127 for byte in raw):
            return False
        scheme, separator, credential = raw.partition(b" ")
        if not separator or not credential or b" " in credential:
            return False
        basic = scheme.lower() == b"basic"
        if basic:
            try:
                decoded = base64.b64decode(credential, validate=True)
            except binascii.Error:
                return False
            username, separator, candidate = decoded.partition(b":")
            if username != b"v" or not separator:
                return False
        elif scheme.lower() == b"bearer":
            candidate = credential
        else:
            return False
        if self._token is None or not hmac.compare_digest(candidate, self._token):
            return False
        if basic and headers.get(b"sec-fetch-site", b"none") not in {
            b"same-origin",
            b"none",
        }:
            return False
        origin = headers.get(b"origin")
        if origin is None:
            return not basic or (
                scope["type"] == "http" and scope["method"] in {"GET", "HEAD"}
            )
        scheme = scope.get("scheme", "http")
        if scheme == "ws":
            scheme = "http"
        elif scheme == "wss":
            scheme = "https"
        expected = _origin(scheme.encode("ascii") + b"://" + headers.get(b"host", b""))
        return expected is not None and _origin(origin) == expected
