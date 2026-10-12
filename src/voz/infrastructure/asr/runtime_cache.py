"""At most one local ASR runtime resident, dropped when the runner is idle."""

import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Protocol


class _Closeable(Protocol):
    def close(self) -> None: ...


class SingleRuntimeCache[K, R: _Closeable]:
    """Keep one runtime alive; asking for another key closes the first.

    A runtime in use (``use``) is never dropped by the idle timer. After the
    last use ends it is closed once ``idle_seconds`` pass without a new one.
    The cost is a reload (model weights back into RAM/VRAM) on the next job
    after a quiet spell, in exchange for returning that memory to the machine.

    # ponytail: un timer por cache y una sola ranura; N motores si alguna vez
    # hace falta transcribir en paralelo.
    """

    def __init__(self, *, idle_seconds: float) -> None:
        self._idle_seconds = idle_seconds
        self._lock = threading.RLock()
        self._key: K | None = None
        self._runtime: R | None = None
        self._busy = 0
        self._epoch = 0
        self._timer: threading.Timer | None = None

    @contextmanager
    def use(self, key: K, create: Callable[[], R]) -> Generator[R]:
        """Yield the runtime for ``key``, loading it (and closing any other)."""
        with self._lock:
            self._disarm()
            if self._runtime is None or self._key != key:
                self._drop()
                self._runtime = create()
                self._key = key
            self._busy += 1
            runtime = self._runtime
        try:
            yield runtime
        finally:
            with self._lock:
                self._busy -= 1
                if self._busy == 0:
                    self._arm()

    def release(self) -> None:
        """Close the resident runtime now (idempotent); loaded again on demand."""
        with self._lock:
            self._disarm()
            self._drop()

    close = release

    def _drop(self) -> None:
        runtime, self._runtime, self._key = self._runtime, None, None
        if runtime is not None:
            runtime.close()

    def _disarm(self) -> None:
        self._epoch += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _arm(self) -> None:
        self._disarm()
        epoch = self._epoch
        timer = threading.Timer(self._idle_seconds, self._expire, args=(epoch,))
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _expire(self, epoch: int) -> None:
        with self._lock:
            if epoch == self._epoch and self._busy == 0:
                self._timer = None
                self._drop()
