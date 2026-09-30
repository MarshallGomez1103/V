"""Application contract for checking free disk space by logical location."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

DEFAULT_DISK_MARGIN_BYTES = 64 * 1024**2
# Normalized derivatives are PCM s16le mono 16 kHz: 16_000 samples * 2 bytes.
PCM_BYTES_PER_MS = 32


class DiskLocation(StrEnum):
    """Logical storage areas; the adapter decides where they live."""

    ORIGINALS = "originals"
    DERIVATIVES = "derivatives"


class DiskSpaceFailureCode(StrEnum):
    """Stable failure code shared by the HTTP and job-failure translations."""

    INSUFFICIENT = "disk_space_insufficient"


class InsufficientDiskSpace(RuntimeError):
    """Not enough free space for an operation; safe to retry after freeing some."""

    code = DiskSpaceFailureCode.INSUFFICIENT
    retryable = True

    def __init__(self, user_message: str | None = None) -> None:
        self.user_message = (
            user_message or "There is not enough free disk space for this operation."
        )
        super().__init__(self.user_message)


@runtime_checkable
class DiskSpacePort(Protocol):
    """Report free bytes for a logical location without exposing its path."""

    def free_bytes(self, location: DiskLocation) -> int:
        """Return the bytes currently available to this process there."""
        ...


def require_free_space(
    disk_space: DiskSpacePort | None,
    location: DiskLocation,
    needed_bytes: int,
    *,
    margin_bytes: int = DEFAULT_DISK_MARGIN_BYTES,
) -> None:
    """Raise ``InsufficientDiskSpace`` unless ``needed_bytes + margin`` fits.

    A ``None`` checker skips the check (callers that predate the port).
    """
    if disk_space is None:
        return
    if disk_space.free_bytes(location) < needed_bytes + margin_bytes:
        raise InsufficientDiskSpace


__all__ = [
    "DEFAULT_DISK_MARGIN_BYTES",
    "PCM_BYTES_PER_MS",
    "DiskLocation",
    "DiskSpaceFailureCode",
    "DiskSpacePort",
    "InsufficientDiskSpace",
    "require_free_space",
]
