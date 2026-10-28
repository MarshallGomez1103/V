"""At most one server per data directory.

Two servers on the same data would both recover the same jobs and each would
discard the other's live temporaries. The lock is an OS advisory lock on a file
under the state directory: the kernel drops it when its holder dies, however it
dies, so there is no stale lock to clean up and no PID to trust.
"""

from __future__ import annotations

import contextlib
import errno
import os
import sys
from pathlib import Path


class InstanceLockError(Exception):
    """Another server holds the lock, or the lock cannot be taken."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InstanceLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._descriptor: int | None = None

    def acquire(self) -> None:
        """Take the lock without waiting; ``InstanceLockError`` if it is not free."""
        if self._descriptor is not None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                self._path, os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), 0o600
            )
        except OSError:
            raise InstanceLockError(
                "instance_lock_unavailable", "The instance lock could not be created."
            ) from None
        try:
            _lock(descriptor)
        except OSError as error:
            os.close(descriptor)
            if error.errno not in _BUSY:
                raise InstanceLockError(
                    "instance_lock_unavailable", "The instance lock could not be taken."
                ) from None
            raise InstanceLockError(
                "instance_already_running",
                "Another V server is already using this data directory.",
            ) from None
        self._descriptor = descriptor

    def release(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            _unlock(descriptor)
            os.close(descriptor)


# "Held by someone else" as each platform words it; any other errno is a real failure.
_BUSY = {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES}
if sys.platform == "win32":
    _BUSY.add(errno.EDEADLOCK)


def _lock(descriptor: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        # flock, not lockf: it conflicts between descriptors of the same process too.
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor: int) -> None:
    # POSIX drops the lock when the descriptor closes; Windows may keep a locked
    # region until the handle is really gone, so release it explicitly first.
    if sys.platform == "win32":
        import msvcrt

        with contextlib.suppress(OSError):
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
