"""Injectable HTTP transport (stdlib only) and multipart encoding for OpenAI."""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import urlsplit
from uuid import uuid4

from voz.infrastructure.cloud.http_body import (
    MAX_JSON_BYTES,
    Aborted,
    Body,
    ResponseTooLarge,
    read_bounded,
    run_abortable,
)


@dataclass(frozen=True, slots=True)
class HttpRequest:
    url: str
    headers: Mapping[str, str] = field(repr=False)  # carries the API key
    body: bytes = field(repr=False)  # carries the user's audio
    timeout_s: float = 600.0
    method: str = "POST"
    abort: Callable[[], bool] | None = field(default=None, repr=False, compare=False)
    """Polled while the request is in flight; ``True`` cuts the connection."""
    max_response_bytes: int = MAX_JSON_BYTES


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict[str, str], repr=False)


class TransportError(Exception):
    """No usable response (connect, TLS, reset, timeout, ``abort``, or too large)."""

    def __init__(
        self, *, timeout: bool = False, aborted: bool = False, oversized: bool = False
    ) -> None:
        self.timeout = timeout
        self.aborted = aborted
        self.oversized = oversized
        super().__init__(
            "aborted"
            if aborted
            else "response too large"
            if oversized
            else "timeout"
            if timeout
            else "network error"
        )


Transport = Callable[[HttpRequest], HttpResponse]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A 3xx is the answer: following it would resend the key to another origin."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


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
        with _OPENER.open(prepared, timeout=request.timeout_s) as reply:
            body = read_bounded(reply, request.max_response_bytes, request.timeout_s)
            return HttpResponse(reply.status, body, dict(reply.headers))
    except urllib.error.HTTPError as error:
        with error:
            try:
                body = read_bounded(
                    cast(Body, error), request.max_response_bytes, request.timeout_s
                )
            except ResponseTooLarge:
                raise TransportError(oversized=True) from None
            except TimeoutError as timeout:
                raise TransportError(timeout=True) from timeout
            except (OSError, http.client.HTTPException) as failure:
                raise TransportError from failure
            return HttpResponse(error.code, body, dict(error.headers))
    except ResponseTooLarge:
        raise TransportError(oversized=True) from None
    except TimeoutError as error:
        raise TransportError(timeout=True) from error
    except urllib.error.URLError as error:
        raise TransportError(timeout=isinstance(error.reason, TimeoutError)) from error
    except (OSError, http.client.HTTPException) as error:
        raise TransportError from error


def _abortable(request: HttpRequest, abort: Callable[[], bool]) -> HttpResponse:
    """``http.client`` request on a helper thread, dropped once ``abort`` is true.

    ponytail: no proxy support on this path (urllib's env proxies are skipped);
    it is used wherever a request must be cancellable while in flight.
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

    def exchange() -> HttpResponse:
        connection.request(
            request.method,
            path,
            body=request.body if request.body or request.method != "GET" else None,
            headers=dict(request.headers),
        )
        reply = connection.getresponse()
        body = read_bounded(reply, request.max_response_bytes, request.timeout_s, abort)
        return HttpResponse(reply.status, body, dict(reply.getheaders()))

    try:
        return run_abortable(exchange, connection, abort)
    except Aborted:
        raise TransportError(aborted=True) from None
    except ResponseTooLarge:
        raise TransportError(oversized=True) from None
    except TimeoutError as error:
        raise TransportError(timeout=True) from error
    except (OSError, http.client.HTTPException) as error:
        raise TransportError from error


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
    "MAX_JSON_BYTES",
    "HttpRequest",
    "HttpResponse",
    "Transport",
    "TransportError",
    "encode_multipart",
    "urllib_transport",
]
