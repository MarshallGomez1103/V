"""One lock that makes "check for active jobs, then act" atomic.

Creating a job, reopening one for speakers, deleting a project and deleting a
model all read the set of active jobs and then write based on it. Run
concurrently (FastAPI serves ``def`` endpoints from a thread pool) they could
interleave; holding the same gate serialises them.

# ponytail: this protects a single process only. Several processes on one
# database would need a constraint in SQLite (e.g. a partial unique index on the
# active job of a media asset); VOZ runs as one local process (ADR monolith).
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager


class AdmissionGate:
    """Process-wide mutual exclusion; share ONE instance across the use cases."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @contextmanager
    def hold(self) -> Generator[None]:
        with self._lock:
            yield


__all__ = ["AdmissionGate"]
