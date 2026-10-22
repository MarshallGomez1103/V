"""Bounded, cancellable reading of HTTP responses (stdlib only).

A cloud or user-configured server decides what it sends back: the body is read
in blocks against a size limit and a total deadline, and a cancellation cuts the
exchange instead of waiting for the server.
"""

from __future__ import annotations

import contextlib
import http.client
import socket
import threading
import time
from collections.abc import Callable
from typing import Final, Protocol

BLOCK_BYTES: Final = 64 * 1024
MAX_JSON_BYTES: Final = 16 * 1024 * 1024
"""Transcriptions, model lists and error bodies."""
MAX_AUDIO_BYTES: Final = 64 * 1024 * 1024
"""One synthesized chunk of speech."""
_ABORT_POLL_S: Final = 0.05


class ResponseTooLarge(Exception):
    """The body went past its limit; nothing of it is kept."""


class Aborted(Exception):
    """Cancellation cut the exchange."""


class Body(Protocol):
    def read1(self, size: int = -1, /) -> bytes: ...


def read_bounded(
    reply: Body,
    limit: int,
    timeout_s: float,
    abort: Callable[[], bool] | None = None,
) -> bytes:
    """Read ``reply`` to its end: at most ``limit + BLOCK_BYTES`` bytes are held.

    ``timeout_s`` is the total time for the body (a socket timeout alone never
    trips on a server that drips one byte at a time).
    """
    deadline = time.monotonic() + timeout_s
    body = bytearray()
    while True:
        if abort is not None and abort():
            raise Aborted
        if time.monotonic() > deadline:
            raise TimeoutError
        block = reply.read1(BLOCK_BYTES)
        if not block:
            remaining = getattr(reply, "length", None)  # declared but never sent
            if remaining:
                raise http.client.IncompleteRead(bytes(body), remaining)
            return bytes(body)
        body += block
        if len(body) > limit:
            raise ResponseTooLarge


def run_abortable[T](
    exchange: Callable[[], T],
    connection: http.client.HTTPConnection,
    abort: Callable[[], bool],
) -> T:
    """Run ``exchange`` on a helper thread, dropped once ``abort`` is true.

    The caller polls ``abort``: on Windows a local ``shutdown`` does not wake a
    socket blocked in recv, so waiting for the socket to fail would delay the
    cancellation until the server answers. Raises ``Aborted`` on cancellation
    and re-raises what ``exchange`` raised, on the caller's thread.
    """
    done = threading.Event()
    stopped = threading.Event()
    result: list[T] = []
    failure: list[Exception] = []

    def run() -> None:
        try:
            connection.connect()
            if stopped.is_set():  # cancelled while connecting: send nothing
                return
            result.append(exchange())
        except Exception as error:  # re-raised below, on the caller's thread
            failure.append(error)
        finally:
            connection.close()
            done.set()

    threading.Thread(target=run, name="voz-http-exchange", daemon=True).start()
    try:
        while not done.wait(_ABORT_POLL_S):
            if abort():
                stopped.set()  # before reading ``sock``: see ``run``
                sock = connection.sock
                if sock is not None:  # frees the thread at once where shutdown wakes it
                    with contextlib.suppress(OSError):
                        sock.shutdown(socket.SHUT_RDWR)
                raise Aborted
    finally:
        connection.close()
    if failure:
        raise failure[0]
    if not result:  # cancelled while connecting, and the poll never saw it
        raise Aborted
    return result[0]
