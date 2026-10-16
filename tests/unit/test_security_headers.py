"""HTTP header policy and transparent ASGI stream forwarding."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from starlette.types import Message, Receive, Scope, Send

from voz.interfaces.api.host_guard import HostGuardMiddleware
from voz.interfaces.api.security_headers import SecurityHeadersMiddleware
from voz.interfaces.api.server_auth import ServerAuthMiddleware

EXPECTED = {
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


def _exercise(
    outgoing: Sequence[Message],
    *,
    kind: str = "http",
    incoming: Sequence[Message] = (),
) -> list[Message]:
    scope: Scope = {"type": kind}
    sent: list[Message] = []
    reads = 0

    async def receive() -> Message:
        nonlocal reads
        result = incoming[reads]
        reads += 1
        return result

    async def send(message: Message) -> None:
        sent.append(message)

    async def app(actual: Scope, recv: Receive, emit: Send) -> None:
        assert actual is scope
        assert recv is receive
        if kind != "http":
            assert emit is send
        assert reads == 0
        for expected in incoming:
            assert await recv() is expected
        for message in outgoing:
            await emit(message)
            assert len(sent) > 0
            if message["type"] != "http.response.start":
                assert sent[-1] is message

    asyncio.run(SecurityHeadersMiddleware(app)(scope, receive, send))
    assert reads == len(incoming)
    return sent


@pytest.mark.parametrize("status", [200, 400, 401, 500])
def test_headers_on_success_and_handled_errors(status: int) -> None:
    body = b'{"detail":"handled response"}'
    sent = _exercise(
        [
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-length", str(len(body)).encode())],
            },
            {"type": "http.response.body", "body": body},
        ]
    )
    assert sent[0]["status"] == status
    headers = dict(sent[0]["headers"])
    assert all(headers.get(name) == value for name, value in EXPECTED.items())
    assert b"strict-transport-security" not in headers
    assert b"cache-control" not in headers
    assert headers[b"content-length"] == str(len(body)).encode()
    assert sent[1]["body"] == body


def test_start_without_headers_and_extra_fields_is_supported() -> None:
    original: Message = {"type": "http.response.start", "status": 200, "trailers": True}
    sent = _exercise([original])
    assert dict(sent[0]["headers"]) == EXPECTED
    assert sent[0]["trailers"] is True
    assert "headers" not in original


def test_owned_duplicates_are_replaced_without_changing_other_headers() -> None:
    retained = [
        (b"Content-Type", b"audio/wav"),
        (b"cache-control", b"private, max-age=120"),
        (b"content-range", b"bytes 0-3/8"),
        (b"accept-ranges", b"bytes"),
        (b"set-cookie", b"first=one"),
        (b"set-cookie", b"second=two"),
        (b"www-authenticate", b'Basic realm="V"'),
        (b"www-authenticate", b'Bearer realm="V"'),
    ]
    duplicates = [
        pair
        for name in EXPECTED
        for pair in [(name.upper(), b"stale"), (name, b"stale-again")]
    ]
    original_headers = [*retained, *duplicates]
    start: Message = {
        "type": "http.response.start",
        "status": 206,
        "headers": original_headers,
    }
    sent = _exercise([start])
    updated = sent[0]["headers"]
    assert [pair for pair in updated if pair[0].lower() not in EXPECTED] == retained
    for name, value in EXPECTED.items():
        assert [pair for pair in updated if pair[0].lower() == name] == [(name, value)]
    assert start["headers"] is original_headers
    assert original_headers == [*retained, *duplicates]


@pytest.mark.parametrize(
    ("status", "content_type"), [(200, b"text/event-stream"), (206, b"audio/wav")]
)
def test_streamed_upload_sse_and_range_bodies_and_disconnect_preserved(
    status: int, content_type: bytes
) -> None:
    outgoing: list[Message] = [
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", content_type),
                (b"content-range", b"bytes 0-3/8"),
            ],
        },
        {"type": "http.response.body", "body": b"first", "more_body": True},
        {"type": "http.response.body", "body": b"last", "more_body": False},
        {"type": "http.response.trailers", "headers": [(b"x-checksum", b"synthetic")]},
    ]
    incoming: list[Message] = [
        {"type": "http.request", "body": b"upload-first", "more_body": True},
        {"type": "http.request", "body": b"upload-last", "more_body": False},
        {"type": "http.disconnect"},
    ]
    sent = _exercise(outgoing, incoming=incoming)
    assert len(sent) == len(outgoing)
    assert all(
        actual is expected
        for actual, expected in zip(sent[1:], outgoing[1:], strict=True)
    )
    assert dict(sent[0]["headers"])[b"content-type"] == content_type
    assert dict(sent[0]["headers"])[b"content-range"] == b"bytes 0-3/8"


@pytest.mark.parametrize("kind", ["lifespan", "websocket", "custom"])
def test_non_http_scopes_forward_without_wrapping(kind: str) -> None:
    event: Message = {"type": f"{kind}.event"}
    assert _exercise([event], kind=kind, incoming=[event])[0] is event


@pytest.mark.parametrize("denial", ["host", "auth"])
def test_outer_header_layer_protects_host_and_auth_denials(denial: str) -> None:
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        pytest.fail("denied requests must not reach the application")

    async def receive() -> Message:
        pytest.fail("denied requests must not consume request bodies")

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "headers": [(b"host", b"evil.example" if denial == "host" else b"localhost")],
    }
    protected = SecurityHeadersMiddleware(
        HostGuardMiddleware(
            ServerAuthMiddleware(app, token="synthetic_headers_token_0123456789abcdef"),
            allowed_hosts=("localhost",),
        )
    )
    asyncio.run(protected(scope, receive, send))
    assert sent[0]["status"] == (400 if denial == "host" else 401)
    headers = dict(sent[0]["headers"])
    assert all(headers.get(name) == value for name, value in EXPECTED.items())
