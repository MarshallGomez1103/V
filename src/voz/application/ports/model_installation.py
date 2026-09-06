"""Application contract for explicit, reproducible local model installation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from voz.domain.entities.model_descriptor import ModelDescriptor


class ModelInstallationFailureCode(StrEnum):
    """Stable failures for user-triggered model installation."""

    CONFIRMATION_REQUIRED = "model_installation_confirmation_required"
    PROVENANCE_REQUIRED = "model_installation_provenance_required"
    DOWNLOAD_FAILED = "model_installation_download_failed"
    INVALID_SNAPSHOT = "model_installation_invalid_snapshot"
    IO_ERROR = "model_installation_io_error"


class ModelInstallationError(RuntimeError):
    """Typed model-installation failure with a path-safe message."""

    def __init__(
        self,
        code: ModelInstallationFailureCode,
        user_message: str,
    ) -> None:
        self.code = code
        self.user_message = user_message
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


__all__ = [
    "ModelInstallation",
    "ModelInstallationError",
    "ModelInstallationFailureCode",
    "ModelInstallationPort",
]
