"""Injectable HTTP transport and streaming multipart body for ElevenLabs.

Only the standard library is used. The provider talks to a ``Transport``
callable, so tests inject a fake and never touch the network. The multipart body
is streamed (head + audio + tail) so a long recording is not copied into memory,
and every read reports upload progress and honors cancellation.
"""

from __future__ import annotations

import http.client
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import BinaryIO, Final, Protocol
from urllib.parse import urlsplit

from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
)

MAX_RESPONSE_BYTES: Final = 64 * 1024 * 1024
UploadProgress = Callable[[int, int], None]


class _Readable(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """One POST; ``body`` streams exactly ``content_length`` bytes."""

    url: str
    headers: Mapping[str, str]
    body: _Readable
    content_length: int
    timeout_s: float

    def __repr__(self) -> str:
        # Headers carry the API key: never render them.
        return f"HttpRequest(url={self.url!r}, content_length={self.content_length})"


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes


class TransportError(Exception):
    """Network-level failure (connect, TLS, reset, timeout) without a response."""

    def __init__(self, *, timeout: bool = False) -> None:
        self.timeout = timeout
        super().__init__("timeout" if timeout else "network error")


Transport = Callable[[HttpRequest], HttpResponse]


def http_transport(request: HttpRequest) -> HttpResponse:
    """Default transport: ``http.client`` with the body streamed from ``read``."""
    parts = urlsplit(request.url)
    host = parts.hostname
    if parts.scheme not in {"http", "https"} or host is None:
        raise ValueError("unsupported transport URL")
    connection_type = (
        http.client.HTTPSConnection
        if parts.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_type(host, parts.port, timeout=request.timeout_s)
    try:
        connection.request(
            "POST",
            parts.path + (f"?{parts.query}" if parts.query else ""),
            body=request.body,
            headers={
                **request.headers,
                "Content-Length": str(request.content_length),
            },
        )
        response = connection.getresponse()
        return HttpResponse(response.status, response.read(MAX_RESPONSE_BYTES))
    except TimeoutError as error:
        raise TransportError(timeout=True) from error
    except (OSError, http.client.HTTPException) as error:
        raise TransportError from error
    finally:
        connection.close()


class MultipartBody:
    """``head`` + audio stream + ``tail`` as one readable, length-known body."""

    def __init__(
        self,
        *,
        head: bytes,
        audio: BinaryIO,
        audio_length: int,
        tail: bytes,
        on_progress: UploadProgress | None = None,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> None:
        self._head = head
        self._audio = audio
        self._audio_left = audio_length
        self._tail = tail
        self._on_progress = on_progress
        self._cancellation = cancellation
        self.length = len(head) + audio_length + len(tail)
        self._sent = 0

    def read(self, size: int = -1, /) -> bytes:
        if self._cancellation is not None and self._cancellation.is_cancelled():
            raise TranscriptionError(
                TranscriptionFailureCode.CANCELLED,
                "Transcription was cancelled.",
            )
        size = 64 * 1024 if size < 0 else size
        chunk = b""
        if self._head:
            chunk, self._head = self._head[:size], self._head[size:]
        elif self._audio_left:
            chunk = self._audio.read(min(size, self._audio_left))
            if not chunk:
                raise TranscriptionError(
                    TranscriptionFailureCode.INVALID_AUDIO,
                    "The selected audio is invalid.",
                )
            self._audio_left -= len(chunk)
        elif self._tail:
            chunk, self._tail = self._tail[:size], self._tail[size:]
        self._sent += len(chunk)
        if chunk and self._on_progress is not None:
            self._on_progress(self._sent, self.length)
        return chunk


def multipart_parts(
    *,
    boundary: str,
    fields: Sequence[tuple[str, str]],
    file_field: str,
    filename: str,
    content_type: str,
) -> tuple[bytes, bytes]:
    """Return the bytes before and after the file payload."""
    head = "".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        f"\r\n\r\n{value}\r\n"
        for name, value in fields
    )
    head += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
    )
    return head.encode("utf-8"), f"\r\n--{boundary}--\r\n".encode("ascii")


__all__ = [
    "HttpRequest",
    "HttpResponse",
    "MultipartBody",
    "Transport",
    "TransportError",
    "UploadProgress",
    "http_transport",
    "multipart_parts",
]
