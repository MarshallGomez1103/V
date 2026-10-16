"""Response headers for the local HTTP application."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADERS = {
    b"content-security-policy": (
        b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        b"img-src 'self' data:; font-src 'self'; media-src 'self' blob:; "
        b"connect-src 'self'; worker-src 'self'; object-src 'none'; "
        b"base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"cross-origin-resource-policy": b"same-origin",
    b"permissions-policy": b"camera=(), microphone=(self)",
}


class SecurityHeadersMiddleware:
    """Add HTTP response headers without consuming or buffering streams."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in _HEADERS
                ]
                message = {
                    **message,
                    "headers": [*headers, *_HEADERS.items()],
                }
            await send(message)

        await self.app(scope, receive, send_with_headers)
