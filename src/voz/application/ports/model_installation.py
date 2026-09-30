"""Application contract for explicit, reproducible local model installation."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from voz.domain.entities.model_descriptor import ModelDescriptor


class ModelInstallationFailureCode(StrEnum):
    """Stable failures for user-triggered model installation."""

    CONFIRMATION_REQUIRED = "model_installation_confirmation_required"
    PROVENANCE_REQUIRED = "model_installation_provenance_required"
    DOWNLOAD_FAILED = "model_installation_download_failed"
    INVALID_SNAPSHOT = "model_installation_invalid_snapshot"
    IO_ERROR = "model_installation_io_error"
    CANCELLED = "model_installation_cancelled"
    CHECKSUM_MISMATCH = "model_installation_checksum_mismatch"
    NETWORK_ERROR = "model_installation_network_error"
    HTTP_ERROR = "model_installation_http_error"
    NOT_INSTALLED = "model_installation_not_installed"
    # Same stable code as ``DiskSpaceFailureCode.INSUFFICIENT``.
    DISK_SPACE_INSUFFICIENT = "disk_space_insufficient"


class ModelInstallationError(RuntimeError):
    """Typed model-installation failure with a path-safe message.

    ``status`` carries the upstream HTTP status for ``HTTP_ERROR`` only.
    """

    def __init__(
        self,
        code: ModelInstallationFailureCode,
        user_message: str,
        *,
        status: int | None = None,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.status = status
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class ModelInstallation:
    """Path-free record proving which immutable upstream snapshot was installed."""

    descriptor: ModelDescriptor
    installed_at: datetime

    def __post_init__(self) -> None:
        if self.descriptor.provenance is None:
            raise ValueError("installed model must include source and revision")
        if self.installed_at.tzinfo is None or self.installed_at.utcoffset() is None:
            raise ValueError("installed_at must be timezone-aware")


_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_RESERVED_NAMES = frozenset({".voz-model.json"})


@dataclass(frozen=True, slots=True)
class ModelFile:
    """One file of a pinned upstream snapshot, with its expected size and digest."""

    name: str  # basename relative to the snapshot root
    size_bytes: int
    sha256: str | None  # lowercase hex for LFS files; None when upstream has none

    def __post_init__(self) -> None:
        name = self.name
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or name.startswith("..")
            or name in _RESERVED_NAMES
            or name.endswith(".part")
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or len(name) > 255
        ):
            raise ValueError("name must be a safe relative file basename")
        if (
            not isinstance(self.size_bytes, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(self.size_bytes, bool)
            or self.size_bytes <= 0
        ):
            raise ValueError("size_bytes must be a positive integer")
        if self.sha256 is not None and _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")


ProgressCallback = Callable[[int, int], None]
"""``(bytes_done, bytes_total)``; called from the installing thread."""

CancelCheck = Callable[[], bool]
"""Polled between blocks; ``True`` requests a cooperative stop."""


@runtime_checkable
class ModelInstallationPort(Protocol):
    """Install only after an explicit caller confirmation."""

    def install(
        self,
        descriptor: ModelDescriptor,
        *,
        confirmed: bool,
    ) -> ModelInstallation:
        """Download and publish the pinned snapshot after confirmation."""
        ...

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        """Return whether the exact provider/model/revision is available locally."""
        ...


@runtime_checkable
class ModelDownloadPort(Protocol):
    """Resumable, verified file-level download/import/removal of pinned models."""

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        base_url: str = "https://huggingface.co",
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        """Download, verify and atomically publish; resumes leftover partials."""
        ...

    def import_local_snapshot(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        snapshot_dir: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        """Adopt a foreign local snapshot without modifying it."""
        ...

    def remove(self, descriptor: ModelDescriptor) -> int:
        """Delete the VOZ copy and return the bytes freed."""
        ...

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        """Bytes used by the VOZ copy, or ``None`` when it is not installed."""
        ...


__all__ = [
    "CancelCheck",
    "ModelDownloadPort",
    "ModelFile",
    "ModelInstallation",
    "ModelInstallationError",
    "ModelInstallationFailureCode",
    "ModelInstallationPort",
    "ProgressCallback",
]
