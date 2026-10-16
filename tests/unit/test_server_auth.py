"""Local server credentials and streaming boundaries, without runtime data."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
from collections.abc import Sequence

import pytest
from starlette.types import Message, Receive, Scope, Send

from voz.interfaces.api.server_auth import ServerAuthMiddleware, ServerAuthTokenError

TOKEN = "synthetic_test_token_0123456789abcdef"
BEARER = b"Bearer " + TOKEN.encode()
BASIC = b"Basic " + base64.b64encode(b"v:" + TOKEN.encode())
HOST = (b"host", b"localhost:8765")
ORIGIN = (b"origin", b"http://localhost:8765")
ERROR = {
    "detail": {
        "code": "server_auth_required",
        "message": "Valid server credentials are required.",
    }
}


def _request(
    headers: Sequence[tuple[bytes, bytes]],
    *,
    method: str = "GET",
    kind: str = "http",
    path: str = "/api/health",
    scheme: str = "http",
    token: str | None = TOKEN,
    incoming: Sequence[Message] = (),
    outgoing: Sequence[Message] = (),
) -> tuple[list[Message], int, int]:
    scope: Scope = {
        "type": kind,
        "headers": list(headers),
        "method": method,
        "path": path,
        "scheme": scheme,
    }
    sent: list[Message] = []
    calls = reads = 0

    async def receive() -> Message:
        nonlocal reads
        message = incoming[reads]
        reads += 1
        return message

    async def send(message: Message) -> None:
        sent.append(message)

    async def app(actual: Scope, recv: Receive, emit: Send) -> None:
        nonlocal calls
        calls += 1
        assert actual is scope
        assert recv is receive
        assert emit is send
        for expected in incoming:
            assert await recv() is expected
        for message in outgoing:
            await emit(message)

    asyncio.run(ServerAuthMiddleware(app, token=token)(scope, receive, send))
    return sent, calls, reads


@pytest.mark.parametrize("kind", ["http", "websocket", "lifespan", "custom"])
def test_none_preserves_every_scope(kind: str) -> None:
    event: Message = {"type": "unchanged"}
    sent, calls, reads = _request(
        [(b"authorization", b"malformed")],
        kind=kind,
        token=None,
        incoming=[event],
        outgoing=[event],
    )
    assert (calls, reads) == (1, 1)
    assert sent[0] is event


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        b"Bearer wrong",
        b"",
        b"Bearer",
        b"Bearer ",
        b" Bearer " + TOKEN.encode(),
        BEARER + b" ",
        BEARER + b",other",
        b"Bearer\t" + TOKEN.encode(),
        b"Bearer  " + TOKEN.encode(),
        BEARER + b"\r\n",
        b"Bearer \xff",
        b"Digest " + TOKEN.encode(),
        b"Bearer " + b"x" * 4096,
        b"Basic !!!!",
        b"Basic " + base64.b64encode(b"other:" + TOKEN.encode()),
        b"Basic " + base64.b64encode(b"v:wrong"),
        b"Basic " + base64.b64encode(TOKEN.encode()),
        b"Basic " + base64.b64encode(b"v:\xff"),
        BASIC + b" ",
    ],
)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_invalid_credentials_never_reach_app(
    authorization: bytes | None, method: str, caplog: pytest.LogCaptureFixture
) -> None:
    headers: list[tuple[bytes, bytes]] = [HOST]
    if authorization is not None:
        headers.append((b"authorization", authorization))
    sent, calls, reads = _request(headers, method=method)
    assert (calls, reads) == (0, 0)
    assert sent[0]["status"] == 401
    assert json.loads(sent[1]["body"]) == ERROR
    response_headers = dict(sent[0]["headers"])
    challenges = [
        value for name, value in sent[0]["headers"] if name == b"www-authenticate"
    ]
    assert challenges == [b'Basic realm="V", charset="UTF-8"', b'Bearer realm="V"']
    assert response_headers[b"cache-control"] == b"no-store"
    assert int(response_headers[b"content-length"]) == len(sent[1]["body"])
    assert TOKEN not in repr(sent) + caplog.text
    assert not caplog.records


@pytest.mark.parametrize(
    "authorization", [BEARER, BASIC, BEARER.lower()[:7] + TOKEN.encode()]
)
@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/assets/app.js",
        "/api/health",
        "/api/jobs/1/events",
        "/api/media/1/original",
    ],
)
def test_valid_authentication_protects_all_paths(
    authorization: bytes, path: str
) -> None:
    _, calls, reads = _request([HOST, (b"authorization", authorization)], path=path)
    assert (calls, reads) == (1, 0)


@pytest.mark.parametrize(
    "path", ["/", "/assets/app.js", "/api/jobs/1/events", "/api/media/1/original"]
)
def test_no_public_static_or_streaming_exceptions(path: str) -> None:
    sent, calls, _ = _request([HOST], path=path)
    assert calls == 0
    assert sent[0]["status"] == 401


@pytest.mark.parametrize("authorization", [BEARER, BASIC])
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "origin",
    [
        b"http://evil.example",
        b"http://localhost:8766",
        b"https://localhost:8765",
        b"http://localhost:8765.evil.example",
        b"http://localhost:8765/",
        b"http://localhost:8765?query",
        b"http://localhost:8765#fragment",
        b"http://v@localhost:8765",
        b"null",
        b"",
        b"http://localhost:99999",
        b"http://localhost:8765\n",
        b"http://local\xffhost:8765",
    ],
)
def test_origin_mismatch_is_denied(
    authorization: bytes, method: str, origin: bytes
) -> None:
    sent, calls, reads = _request(
        [HOST, (b"authorization", authorization), (b"origin", origin)], method=method
    )
    assert (calls, reads) == (0, 0)
    assert sent[0]["status"] == 401


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]
)
def test_basic_unsafe_requires_origin_but_bearer_does_not(method: str) -> None:
    assert _request([HOST, (b"authorization", BASIC)], method=method)[1] == 0
    assert _request([HOST, ORIGIN, (b"authorization", BASIC)], method=method)[1] == 1
    assert _request([HOST, (b"authorization", BEARER)], method=method)[1] == 1


@pytest.mark.parametrize("site", [b"cross-site", b"same-site", b"", b"garbage"])
def test_basic_rejects_cross_origin_fetch_metadata_even_without_origin(
    site: bytes,
) -> None:
    assert (
        _request([HOST, (b"authorization", BASIC), (b"sec-fetch-site", site)])[1] == 0
    )


@pytest.mark.parametrize("site", [b"none", b"same-origin"])
def test_basic_native_navigation_and_same_origin_fetch(site: bytes) -> None:
    assert (
        _request([HOST, (b"authorization", BASIC), (b"sec-fetch-site", site)])[1] == 1
    )


@pytest.mark.parametrize("authorization", [BEARER, BASIC])
@pytest.mark.parametrize(
    ("host", "origin", "scheme"),
    [
        (b"localhost:8765", b"http://LOCALHOST:8765", "http"),
        (b"localhost", b"http://localhost:80", "http"),
        (b"localhost:443", b"https://localhost", "https"),
        (b"[::1]:8765", b"http://[::1]:8765", "http"),
    ],
)
def test_origin_uses_scheme_host_and_effective_port(
    authorization: bytes, host: bytes, origin: bytes, scheme: str
) -> None:
    assert (
        _request(
            [(b"host", host), (b"origin", origin), (b"authorization", authorization)],
            method="POST",
            scheme=scheme,
        )[1]
        == 1
    )


@pytest.mark.parametrize("authorization", [BEARER, BASIC])
@pytest.mark.parametrize(
    "name", [b"authorization", b"Authorization", b"origin", b"host", b"sec-fetch-site"]
)
def test_duplicate_security_headers_are_rejected(
    authorization: bytes, name: bytes
) -> None:
    headers = [
        HOST,
        ORIGIN,
        (b"authorization", authorization),
        (b"sec-fetch-site", b"same-origin"),
    ]
    value = dict(headers)[name.lower()]
    sent, calls, _ = _request([*headers, (name, value)])
    assert calls == 0
    assert sent[0]["status"] == 401


@pytest.mark.parametrize("authorization", [BEARER, BASIC])
def test_streaming_upload_sse_and_range_messages_preserved(
    authorization: bytes,
) -> None:
    incoming: list[Message] = [
        {"type": "http.request", "body": b"first", "more_body": True},
        {"type": "http.request", "body": b"last", "more_body": False},
        {"type": "http.disconnect"},
    ]
    outgoing: list[Message] = [
        {
            "type": "http.response.start",
            "status": 206,
            "headers": [
                (b"content-type", b"text/event-stream"),
                (b"content-range", b"bytes 0-9/10"),
            ],
        },
        {"type": "http.response.body", "body": b"data: first\n\n", "more_body": True},
        {"type": "http.response.body", "body": b"data: last\n\n", "more_body": False},
    ]
    sent, calls, reads = _request(
        [HOST, ORIGIN, (b"authorization", authorization), (b"range", b"bytes=0-9")],
        method="POST",
        incoming=incoming,
        outgoing=outgoing,
    )
    assert (calls, reads) == (1, 3)
    assert len(sent) == len(outgoing)
    assert all(
        actual is expected for actual, expected in zip(sent, outgoing, strict=True)
    )


@pytest.mark.parametrize("kind", ["lifespan", "custom"])
def test_non_request_scopes_pass_with_auth_enabled(kind: str) -> None:
    assert _request([], kind=kind)[1] == 1


@pytest.mark.parametrize("authorization", [None, b"Bearer wrong", BASIC])
def test_websocket_denial_uses_policy_violation(authorization: bytes | None) -> None:
    headers = (
        [HOST] if authorization is None else [HOST, (b"authorization", authorization)]
    )
    sent, calls, reads = _request(headers, kind="websocket", scheme="ws")
    assert (sent, calls, reads) == ([{"type": "websocket.close", "code": 1008}], 0, 0)


@pytest.mark.parametrize("authorization", [BEARER, BASIC])
def test_authenticated_websocket_forwards_unchanged(authorization: bytes) -> None:
    message: Message = {"type": "websocket.accept"}
    sent, calls, _ = _request(
        [HOST, ORIGIN, (b"authorization", authorization)],
        kind="websocket",
        scheme="ws",
        outgoing=[message],
    )
    assert calls == 1
    assert sent[0] is message
    assert (
        _request(
            [
                HOST,
                (b"origin", b"http://evil.example"),
                (b"authorization", authorization),
            ],
            kind="websocket",
            scheme="ws",
        )[1]
        == 0
    )


@pytest.mark.parametrize(
    "token", ["", "short", "x" * 513, "é" * 32, "x" * 32 + "\n", "x" * 32 + ":"]
)
def test_bad_configuration_has_typed_safe_error(token: str) -> None:
    with pytest.raises(ServerAuthTokenError) as caught:
        _request([], token=token)
    assert caught.value.code == "server_auth_token_invalid"
    assert (
        str(caught.value)
        == "The server token must be 32-512 URL-safe ASCII characters."
    )


def test_secret_is_private_and_absent_from_representations() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        pass

    middleware = ServerAuthMiddleware(app, token=TOKEN)
    assert TOKEN not in repr(middleware) + str(middleware)
    assert not hasattr(middleware, "token")


@pytest.mark.parametrize("size", [32, 512])
@pytest.mark.parametrize("scheme", [b"bEaReR", b"bAsIc"])
def test_supported_token_bounds_and_case_insensitive_schemes(
    size: int, scheme: bytes
) -> None:
    token = "_" + "a" * (size - 2) + "-"
    credential = (
        token.encode()
        if scheme.lower() == b"bearer"
        else base64.b64encode(b"v:" + token.encode())
    )
    assert (
        _request([HOST, (b"authorization", scheme + b" " + credential)], token=token)[1]
        == 1
    )


@pytest.mark.parametrize("authorization", [BEARER, BASIC, b"Bearer wrong"])
def test_token_comparison_uses_constant_time_primitive(
    authorization: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    compare = hmac.compare_digest
    compared: list[tuple[bytes, bytes]] = []

    def record(left: bytes, right: bytes) -> bool:
        compared.append((left, right))
        return compare(left, right)

    monkeypatch.setattr(hmac, "compare_digest", record)
    _request([HOST, (b"authorization", authorization)])
    assert len(compared) == 1
    assert compared[0][1] == TOKEN.encode()


def test_websocket_bearer_client_can_omit_origin() -> None:
    assert (
        _request([HOST, (b"authorization", BEARER)], kind="websocket", scheme="ws")[1]
        == 1
    )


@pytest.mark.parametrize("header", [b"origin", b"host"])
def test_origin_validation_requires_one_bounded_authority(header: bytes) -> None:
    headers = [HOST, ORIGIN, (b"authorization", BASIC)]
    without = [pair for pair in headers if pair[0] != header]
    assert _request(without, method="POST")[1] == 0
    assert _request([*without, (header, b"x" * 1025)], method="POST")[1] == 0


@pytest.mark.parametrize("suffix", [b"=", b"===="])
def test_noncanonical_basic_base64_is_malformed(suffix: bytes) -> None:
    assert _request([HOST, (b"authorization", BASIC + suffix)])[1] == 0
