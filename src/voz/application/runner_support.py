"""Small primitives shared by the transcription and synthesis runners."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AnyEventToken:
    """Cancelled when the user cancels *or* the server is shutting down."""

    events: tuple[threading.Event, ...]

    def is_cancelled(self) -> bool:
        return any(event.is_set() for event in self.events)


def not_before(now: datetime, floor: datetime) -> datetime:
    """``now``, but never earlier than ``floor``: job timestamps only move forward."""
    return floor if now < floor else now


__all__ = ["AnyEventToken", "not_before"]
