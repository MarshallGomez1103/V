"""Cloud transports bound what they read: size, total time and cancellation."""

from __future__ import annotations

import dataclasses
import socket
import struct
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest

from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
)
from voz.infrastructure.cloud import elevenlabs_transport as eleven
from voz.infrastructure.cloud import openai_transport as openai
from voz.infrastructure.cloud.elevenlabs_scribe import (
    ElevenLabsScribeProvider,
    elevenlabs_scribe_descriptor,
)
from voz.infrastructure.cloud.http_body import Aborted, run_abortable
from voz.infrastructure.cloud.openai_limits import openai_descriptors
from voz.infrastructure.cloud.openai_transcription import OpenAITranscriptionProvider

BLOCK = b"x" * 65_536
SLACK = (
    24 * 1024 * 1024
)  # kernel socket buffers on both ends, far below an endless body


class _Flood:
    """Close-delimited body of ``total`` bytes; remembers how much was accepted."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.sent = 0


@contextmanager
def _serve(body: Callable[[BaseHTTPRequestHandler], None]) -> Generator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _answer(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with suppress(OSError):
                body(self)

        do_GET = do_POST = _answer

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/v1/x"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def _flood(flood: _Flood) -> Callable[[BaseHTTPRequestHandler], None]:
    def write(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.end_headers()
        while flood.sent < flood.total:
            handler.wfile.write(BLOCK)
            flood.sent += len(BLOCK)

    return write


def _drip(pause_s: float, seconds: float) -> Callable[[BaseHTTPRequestHandler], None]:
    def write(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.flush()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            handler.wfile.write(b"x")
            handler.wfile.flush()
            time.sleep(pause_s)

    return write


def _silent(seconds: float) -> Callable[[BaseHTTPRequestHandler], None]:
    return lambda handler: time.sleep(seconds)


FAILS = (openai.TransportError, eleven.TransportError)


def _openai_call(
    url: str,
    *,
    timeout_s: float = 5,
    abort: Callable[[], bool] | None = None,
    limit: int | None = None,
) -> bytes:
    request = openai.HttpRequest(
        url,
        {},
        b"a",
        timeout_s,
        abort=abort,
        max_response_bytes=limit or openai.MAX_JSON_BYTES,
    )
    return openai.urllib_transport(request).body


def _eleven_call(
    url: str,
    *,
    timeout_s: float = 5,
    abort: Callable[[], bool] | None = None,
    limit: int | None = None,
) -> bytes:
    request = eleven.HttpRequest(
        url,
        {},
        BytesIO(b"a"),
        1,
        timeout_s,
        abort=abort,
        max_response_bytes=limit or eleven.MAX_JSON_BYTES,
    )
    return eleven.http_transport(request).body


Call = Callable[..., bytes]
CALLS = pytest.mark.parametrize(
    "call", [_openai_call, _eleven_call], ids=["openai", "elevenlabs"]
)
ABORTS = pytest.mark.parametrize(
    "with_abort", [False, True], ids=["plain", "abortable"]
)


@CALLS
def test_an_endless_body_is_cut_at_the_default_limit(call: Call) -> None:
    flood = _Flood(160 * 1024 * 1024)
    with (
        _serve(_flood(flood)) as url,
        pytest.raises(FAILS) as raised,
    ):
        call(url)

    assert raised.value.oversized
    assert flood.sent < openai.MAX_JSON_BYTES + SLACK


@CALLS
@ABORTS
def test_a_body_over_the_request_limit_is_refused(call: Call, with_abort: bool) -> None:
    flood = _Flood(8 * 1024 * 1024)
    abort = (lambda: False) if with_abort else None
    with (
        _serve(_flood(flood)) as url,
        pytest.raises(FAILS) as raised,
    ):
        call(url, limit=100_000, abort=abort)

    assert raised.value.oversized
    assert "127.0.0.1" not in str(raised.value)


@CALLS
@ABORTS
def test_a_body_within_the_limit_is_returned_whole(
    call: Call, with_abort: bool
) -> None:
    flood = _Flood(3 * len(BLOCK))
    abort = (lambda: False) if with_abort else None
    with _serve(_flood(flood)) as url:
        assert call(url, limit=3 * len(BLOCK), abort=abort) == BLOCK * 3


def test_an_error_status_body_is_bounded_too() -> None:
    def refuse(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(BLOCK * 3)

    with _serve(refuse) as url:
        assert _openai_call(url, limit=4 * len(BLOCK)) == BLOCK * 3
        with pytest.raises(openai.TransportError) as raised:
            _openai_call(url, limit=100_000)

    assert raised.value.oversized


@CALLS
@ABORTS
def test_a_slow_endless_body_ends_by_timeout(call: Call, with_abort: bool) -> None:
    abort = (lambda: False) if with_abort else None
    started = time.monotonic()
    with (
        _serve(_drip(0.1, 8)) as url,
        pytest.raises(FAILS) as raised,
    ):
        call(url, timeout_s=1, abort=abort)

    assert raised.value.timeout
    assert time.monotonic() - started < 4


@CALLS
@pytest.mark.parametrize("silent", [False, True], ids=["dripping", "no-headers"])
def test_cancelling_during_the_read_cuts_in_under_a_second(
    call: Call, silent: bool
) -> None:
    cancel = threading.Event()
    cut_at: list[float] = []

    def fire() -> None:
        time.sleep(0.3)
        cut_at.append(time.monotonic())
        cancel.set()

    handler = _silent(5) if silent else _drip(0.05, 8)
    with (
        _serve(handler) as url,
        pytest.raises(FAILS) as raised,
    ):
        threading.Thread(target=fire, daemon=True).start()
        call(url, timeout_s=30, abort=cancel.is_set)

    assert raised.value.aborted
    assert time.monotonic() - cut_at[0] < 1.0


def _short_body(status: int) -> Callable[[BaseHTTPRequestHandler], None]:
    def write(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(status)
        handler.send_header("Content-Length", "100")
        handler.end_headers()
        handler.wfile.write(b"x" * 10)

    return write


@CALLS
@ABORTS
@pytest.mark.parametrize("status", [200, 500])
def test_a_body_shorter_than_declared_is_a_transport_error(
    call: Call, with_abort: bool, status: int
) -> None:
    abort = (lambda: False) if with_abort else None
    with _serve(_short_body(status)) as url, pytest.raises(FAILS) as raised:
        call(url, abort=abort)

    assert not raised.value.oversized
    assert not raised.value.timeout


def test_a_reset_while_reading_an_error_body_is_a_transport_error() -> None:
    def reset(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(500)
        handler.send_header("Content-Length", "100")
        handler.end_headers()
        handler.wfile.flush()
        time.sleep(0.2)
        handler.connection.setsockopt(
            socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
        )
        handler.connection.close()

    with _serve(reset) as url, pytest.raises(openai.TransportError):
        _openai_call(url)


class _Stuck:
    """An upload that stalls: ``read`` waits, as a dead source would."""

    def __init__(self, release: threading.Event) -> None:
        self.release = release

    def read(self, size: int = -1, /) -> bytes:
        self.release.wait(3)
        return b""


def test_cancelling_a_stalled_upload_cuts_in_under_a_second() -> None:
    release = threading.Event()
    cancel = threading.Event()
    cut_at: list[float] = []

    def fire() -> None:
        time.sleep(0.3)
        cut_at.append(time.monotonic())
        cancel.set()

    request = eleven.HttpRequest("", {}, _Stuck(release), 10, 30, abort=cancel.is_set)
    with _serve(_silent(5)) as url, pytest.raises(eleven.TransportError) as raised:
        threading.Thread(target=fire, daemon=True).start()
        eleven.http_transport(dataclasses.replace(request, url=url))
    release.set()

    assert raised.value.aborted
    assert time.monotonic() - cut_at[0] < 1.0


class _LateConnection:
    """Connects only once released, as a slow DNS or TCP handshake would."""

    def __init__(self) -> None:
        self.sock: object | None = None
        self.release = threading.Event()
        self.closed = threading.Event()

    def connect(self) -> None:
        self.release.wait(3)
        self.sock = object()

    def close(self) -> None:
        self.closed.set()


def test_an_abort_before_the_connection_exists_sends_nothing() -> None:
    connection = _LateConnection()
    sent: list[str] = []

    with pytest.raises(Aborted):
        run_abortable(
            lambda: sent.append("request"),
            connection,  # type: ignore[arg-type]
            lambda: True,
        )
    connection.release.set()  # the connect finishes only after the abort

    assert connection.closed.wait(2)
    time.sleep(0.2)
    assert sent == []


# --- adapters: stable, non-retried errors -------------------------------------


class _Secrets:
    def get(self, provider_id: str) -> str | None:
        return "k"

    def configured(self, provider_id: str) -> bool:
        return True

    def set(self, provider_id: str, key: str) -> None:
        raise AssertionError

    def delete(self, provider_id: str) -> None:
        raise AssertionError


class _Cancel:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


def _wav(seconds: float = 0.1) -> BytesIO:
    import wave

    out = BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * int(seconds * 16_000))
    out.seek(0)
    return out


@pytest.mark.parametrize("aborted", [False, True])
def test_openai_oversized_or_aborted_reply_maps_to_one_stable_error(
    aborted: bool,
) -> None:
    calls: list[openai.HttpRequest] = []
    cancel = _Cancel()

    def transport(request: openai.HttpRequest) -> openai.HttpResponse:
        calls.append(request)
        if aborted:
            cancel.cancelled = True
            raise openai.TransportError(aborted=True)
        raise openai.TransportError(oversized=True)

    provider = OpenAITranscriptionProvider(
        secrets=_Secrets(), transport=transport, sleep=lambda _: None, max_attempts=3
    )
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=_wav(),
            options=TranscriptionOptions(model=openai_descriptors()[0]),
            cancellation=cancel,
        )

    assert len(calls) == 1  # never retried
    assert calls[0].abort is not None  # the request itself can be cut
    if aborted:
        assert raised.value.code is TranscriptionFailureCode.CANCELLED
    else:
        assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
        assert not raised.value.retryable
        assert "127.0.0.1" not in str(raised.value)


@pytest.mark.parametrize("aborted", [False, True])
def test_elevenlabs_oversized_or_aborted_reply_maps_to_one_stable_error(
    aborted: bool,
) -> None:
    calls: list[eleven.HttpRequest] = []
    cancel = _Cancel()

    def transport(request: eleven.HttpRequest) -> eleven.HttpResponse:
        calls.append(request)
        cancel.cancelled = aborted
        raise eleven.TransportError(aborted=aborted, oversized=not aborted)

    provider = ElevenLabsScribeProvider(secrets=_Secrets(), transport=transport)
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=_wav(),
            options=TranscriptionOptions(model=elevenlabs_scribe_descriptor()),
            cancellation=cancel,
        )

    assert len(calls) == 1
    assert calls[0].abort is not None
    if aborted:
        assert raised.value.code is TranscriptionFailureCode.CANCELLED
    else:
        assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
        assert not raised.value.retryable
