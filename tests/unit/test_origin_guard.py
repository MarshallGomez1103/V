"""Cross-origin refusal for state changes and websocket handshakes."""

from __future__ import annotations

import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from voz.interfaces.api.host_guard import HostGuardMiddleware, origin_allowed

HOST = (b"host", b"127.0.0.1:8765")


def _allowed(method: str, *extra: tuple[bytes, bytes], scheme: str = "http") -> bool:
    return origin_allowed(method, scheme, [HOST, *extra])


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "WEBSOCKET"])
@pytest.mark.parametrize(
    "headers",
    [
        [(b"origin", b"https://evil.example")],
        [(b"origin", b"null")],
        [(b"origin", b"http://127.0.0.1:9")],
        [(b"origin", b"https://127.0.0.1:8765")],
        [(b"origin", b"http://127.0.0.1:8765/path")],
        [(b"origin", b"http://127.0.0.1:8765"), (b"origin", b"http://evil.example")],
        [(b"sec-fetch-site", b"cross-site")],
        [(b"sec-fetch-site", b"same-site")],
        [(b"sec-fetch-site", b"bogus")],
        [(b"origin", b"http://127.0.0.1:8765"), (b"sec-fetch-site", b"cross-site")],
    ],
)
def test_unsafe_requests_from_other_origins_are_refused(
    method: str, headers: list[tuple[bytes, bytes]]
) -> None:
    assert not _allowed(method, *headers)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "WEBSOCKET"])
@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"origin", b"http://127.0.0.1:8765")],
        [(b"origin", b"HTTP://127.0.0.1:8765")],
        [(b"sec-fetch-site", b"same-origin")],
        [(b"sec-fetch-site", b"none")],
        [(b"origin", b"http://127.0.0.1:8765"), (b"sec-fetch-site", b"same-origin")],
    ],
)
def test_same_origin_and_non_browser_clients_pass(
    method: str, headers: list[tuple[bytes, bytes]]
) -> None:
    assert _allowed(method, *headers)


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_are_not_gated_by_origin(method: str) -> None:
    evil = [(b"origin", b"https://evil.example"), (b"sec-fetch-site", b"cross-site")]
    assert _allowed(method, *evil)


def test_origin_must_match_scheme_host_and_port_of_the_request() -> None:
    lan = [(b"host", b"10.0.0.5:8765"), (b"origin", b"http://10.0.0.5:8765")]
    assert origin_allowed("POST", "http", lan)
    assert not origin_allowed("POST", "https", lan)
    assert origin_allowed(
        "POST", "wss", [(b"host", b"[::1]:8765"), (b"origin", b"https://[::1]:8765")]
    )
    assert not origin_allowed("POST", "http", [(b"origin", b"http://127.0.0.1:8765")])


def _handshake(headers: list[tuple[bytes, bytes]]) -> list[Message]:
    sent: list[Message] = []
    reached: list[bool] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(True)

    async def receive() -> Message:
        raise AssertionError("handshake must not be read")

    async def send(message: Message) -> None:
        sent.append(message)

    guard = HostGuardMiddleware(app, allowed_hosts=("127.0.0.1",))
    scope: Scope = {"type": "websocket", "scheme": "ws", "headers": [HOST, *headers]}
    asyncio.run(guard(scope, receive, send))
    return [] if reached else sent


def test_websocket_handshake_from_another_origin_is_closed() -> None:
    assert _handshake([(b"origin", b"https://evil.example")]) == [
        {"type": "websocket.close", "code": 1008}
    ]
    assert _handshake([(b"origin", b"http://127.0.0.1:8765")]) == []
    assert _handshake([]) == []
