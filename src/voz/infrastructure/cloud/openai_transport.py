"""Injectable HTTP transport (stdlib only) and multipart encoding for OpenAI."""

from __future__ import annotations

import contextlib
import http.client
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import uuid4

_ABORT_POLL_S = 0.05


@dataclass(frozen=True, slots=True)
class HttpRequest:
    url: str
    headers: Mapping[str, str] = field(repr=False)  # carries the API key
    body: bytes = field(repr=False)  # carries the user's audio
    timeout_s: float = 600.0
    method: str = "POST"
    abort: Callable[[], bool] | None = field(default=None, repr=False, compare=False)
    """Polled while the request is in flight; ``True`` cuts the connection."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict[str, str], repr=False)


class TransportError(Exception):
    """No response at all (connect, TLS, reset, timeout, or cut by ``abort``)."""

    def __init__(self, *, timeout: bool = False, aborted: bool = False) -> None:
        self.timeout = timeout
        self.aborted = aborted
        super().__init__(
            "aborted" if aborted else "timeout" if timeout else "network error"
        )


Transport = Callable[[HttpRequest], HttpResponse]


def urllib_transport(request: HttpRequest) -> HttpResponse:
    """Real network transport. Only the composition root may inject it."""
    if request.abort is not None:
        return _abortable(request, request.abort)
    prepared = urllib.request.Request(
        request.url,
        data=request.body if request.body or request.method != "GET" else None,
        headers=dict(request.headers),
        method=request.method,
    )
    try:
        with urllib.request.urlopen(prepared, timeout=request.timeout_s) as reply:
            return HttpResponse(reply.status, reply.read(), dict(reply.headers))
    except urllib.error.HTTPError as error:
        with error:
            return HttpResponse(error.code, error.read(), dict(error.headers))
    except TimeoutError as error:
        raise TransportError(timeout=True) from error
    except urllib.error.URLError as error:
        raise TransportError(timeout=isinstance(error.reason, TimeoutError)) from error
    except OSError as error:
        raise TransportError from error


def _abortable(request: HttpRequest, abort: Callable[[], bool]) -> HttpResponse:
    """``http.client`` request on a helper thread, dropped once ``abort`` is true.

    ponytail: no proxy support on this path (urllib's env proxies are skipped);
    it is only used by engines that need cancellation mid-request.
    """
    parts = urlsplit(request.url)
    factory = (
        http.client.HTTPSConnection
        if parts.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = factory(parts.hostname or "", parts.port, timeout=request.timeout_s)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    done = threading.Event()
    outcome: list[HttpResponse | Exception] = []

    def exchange() -> None:
        try:
            connection.request(
                request.method,
                path,
                body=request.body if request.body or request.method != "GET" else None,
                headers=dict(request.headers),
            )
            reply = connection.getresponse()
            outcome.append(
                HttpResponse(reply.status, reply.read(), dict(reply.getheaders()))
            )
        except Exception as error:  # re-raised below, on the caller's thread
            outcome.append(error)
        finally:
            done.set()

    # The exchange runs on its own thread and the caller polls ``abort``: on
    # Windows a local ``shutdown`` does not wake a socket blocked in recv, so
    # waiting for the socket to fail would delay the cancellation until the
    # server answers.
    threading.Thread(target=exchange, name="voz-http-exchange", daemon=True).start()
    try:
        while not done.wait(_ABORT_POLL_S):
            if abort():
                sock = connection.sock
                if sock is not None:  # frees the thread at once where shutdown wakes it
                    with contextlib.suppress(OSError):
                        sock.shutdown(socket.SHUT_RDWR)
                raise TransportError(aborted=True)
    finally:
        connection.close()
    error = outcome[0]
    if isinstance(error, HttpResponse):
        return error
    if isinstance(error, TimeoutError):
        raise TransportError(timeout=True) from error
    if isinstance(error, OSError | http.client.HTTPException):
        raise TransportError from error
    raise error


def encode_multipart(
    fields: list[tuple[str, str]],
    file_field: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> tuple[bytes, str]:
    """Return ``(body, content_type_header)``; field values must be plain ASCII."""
    boundary = f"voz-{uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("ascii")
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; "
        f'name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode("ascii")
    )
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


__all__ = [
    "HttpRequest",
    "HttpResponse",
    "Transport",
    "TransportError",
    "encode_multipart",
    "urllib_transport",
]
