"""Rate limit for progress writes: the database must not see every callback."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

MIN_SAVE_INTERVAL_S = 0.5
"""At most ~2 progress saves per second (state changes are never throttled)."""


@dataclass(slots=True)
class ProgressThrottle:
    """``ready()`` is true at most once per ``interval_s``; the first call is true."""

    interval_s: float = MIN_SAVE_INTERVAL_S
    monotonic: Callable[[], float] = time.monotonic
    _last: float | None = field(default=None, repr=False)

    def ready(self) -> bool:
        now = self.monotonic()
        if self._last is not None and now - self._last < self.interval_s:
            return False
        self._last = now
        return True


__all__ = ["MIN_SAVE_INTERVAL_S", "ProgressThrottle"]
