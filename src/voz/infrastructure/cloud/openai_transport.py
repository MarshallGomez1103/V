"""Injectable HTTP transport (stdlib only) and multipart encoding for OpenAI."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class HttpRequest:
    url: str
    headers: Mapping[str, str] = field(repr=False)  # carries the API key
    body: bytes = field(repr=False)  # carries the user's audio
    timeout_s: float = 600.0


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict[str, str], repr=False)


class TransportError(Exception):
    """No response at all (connect, TLS, reset, timeout)."""

    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout
        super().__init__("timeout" if timeout else "network error")


Transport = Callable[[HttpRequest], HttpResponse]


def urllib_transport(request: HttpRequest) -> HttpResponse:
    """Real network transport. Only the composition root may inject it."""
    prepared = urllib.request.Request(
        request.url, data=request.body, headers=dict(request.headers), method="POST"
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
