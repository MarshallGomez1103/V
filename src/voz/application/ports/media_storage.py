"""Application contract for immutable original-media storage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from voz.domain.entities.media_asset import MediaAsset


class MediaStorageErrorCode(StrEnum):
    """Stable failure categories callers can translate without parsing text."""

    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_NOT_REGULAR = "source_not_regular"
    SOURCE_IS_SYMLINK = "source_is_symlink"
    SOURCE_CHANGED = "source_changed"
    SOURCE_EQUALS_DESTINATION = "source_equals_destination"
    DESTINATION_EXISTS = "destination_exists"
    UNSAFE_DISPLAY_NAME = "unsafe_display_name"
    UNSAFE_STORAGE_PATH = "unsafe_storage_path"
    IO_ERROR = "io_error"


class MediaStorageError(RuntimeError):
    """Typed, path-safe error raised by a media storage adapter."""

    def __init__(self, code: MediaStorageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImportedOriginal:
    """Successful import ready for metadata persistence.

    The storage location remains an adapter concern. ``media_asset`` contains
    the digest and byte count that a caller can persist through the existing
    ``MediaAssetRepository``.
    """

    media_asset: MediaAsset
    bytes_copied: int

    def __post_init__(self) -> None:
        if self.bytes_copied != self.media_asset.size_bytes:
            raise ValueError("bytes_copied must match the media asset size")


@runtime_checkable
class MediaStoragePort(Protocol):
    """Store an original without modifying or replacing existing content."""

    def import_original(
        self,
        *,
        source: Path,
        project_id: UUID,
        media_asset_id: UUID,
        media_type: str | None = None,
    ) -> ImportedOriginal:
        """Copy one regular file and return its persistable metadata."""
        ...


__all__ = [
    "ImportedOriginal",
    "MediaStorageError",
    "MediaStorageErrorCode",
    "MediaStoragePort",
]
