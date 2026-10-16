"""One heavy inference at a time in the process: ASR, diarization or TTS (ADR-0010).

Runners take the slot around a job's heavy work. Waiters are served in arrival
order, and a waiter whose job is cancelled (or the server is stopping) leaves
the line without running. ``holder`` and ``waiting`` let the UI explain a wait
("waiting for the transcription to finish").

# ponytail: one slot for one process. Ceiling: a machine with several GPUs
# could run N jobs at once; then this becomes N slots (one per device) and
# ``holder`` a tuple. VOZ runs as one local process (ADR monolith).
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

_POLL_SECONDS = 0.05
"""How often a waiter re-checks its cancellation token."""


class ComputeKind(StrEnum):
    """What kind of heavy work holds (or waits for) the slot."""

    TRANSCRIPTION = "transcription"
    DIARIZATION = "diarization"
    SYNTHESIS = "synthesis"
    MODEL_VALIDATION = "model_validation"


@dataclass(frozen=True, slots=True)
class SlotUser:
    """A job that holds or waits for the slot."""

    kind: ComputeKind
    job_id: UUID


class SlotCancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...


class SlotWaitCancelled(Exception):
    """The job was cancelled (or the server stopped) while waiting for the slot."""


class ComputeSlot:
    """Fair (FIFO) process-wide mutex for heavy jobs; share ONE instance."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._holder: SlotUser | None = None
        self._waiting: deque[SlotUser] = deque()

    @contextmanager
    def hold(
        self,
        kind: ComputeKind,
        job_id: UUID,
        *,
        cancellation: SlotCancellationToken | None = None,
    ) -> Generator[None]:
        """Run the body holding the slot; ``SlotWaitCancelled`` if cancelled first."""
        me = SlotUser(kind, job_id)
        with self._condition:
            self._waiting.append(me)
            try:
                while self._holder is not None or self._waiting[0] is not me:
                    if cancellation is not None and cancellation.is_cancelled():
                        raise SlotWaitCancelled(str(job_id))
                    self._condition.wait(_POLL_SECONDS)
            except BaseException:
                self._waiting = deque(user for user in self._waiting if user is not me)
                self._condition.notify_all()  # the next in line may be first now
                raise
            self._waiting.popleft()
            self._holder = me
        try:
            yield
        finally:
            with self._condition:
                self._holder = None
                self._condition.notify_all()

    def holder(self) -> SlotUser | None:
        """Who runs heavy work now, or ``None`` when the slot is free."""
        with self._condition:
            return self._holder

    def waiting(self) -> tuple[SlotUser, ...]:
        """Jobs waiting for the slot, first in line first."""
        with self._condition:
            return tuple(self._waiting)


__all__ = [
    "ComputeKind",
    "ComputeSlot",
    "SlotCancellationToken",
    "SlotUser",
    "SlotWaitCancelled",
]
