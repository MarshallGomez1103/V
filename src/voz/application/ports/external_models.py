"""Application contract for reusing models already cached by other tools."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable


class ExternalModelFailureCode(StrEnum):
    """Stable failures when importing a model from an external cache."""

    UNKNOWN_MODEL = "external_model_unknown_model"
    NOT_FOUND = "external_model_not_found"


class ExternalModelError(RuntimeError):
    """Typed external-model failure with a path-safe message."""

    def __init__(self, code: ExternalModelFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class ExternalModelCandidate:
    """A complete, exactly pinned snapshot found in another tool's cache.

    ``snapshot_dir`` is a host path: infrastructure/application use only, never
    return it to the browser.
    """

    origin: str
    source: str
    revision: str
    snapshot_dir: Path
    total_bytes: int


@runtime_checkable
class ExternalModelSource(Protocol):
    """Read-only discovery; implementations must never modify the foreign cache."""

    def find_candidates(self) -> tuple[ExternalModelCandidate, ...]:
        """Return only snapshots whose identity and file sizes match the catalog."""
        ...


__all__ = [
    "ExternalModelCandidate",
    "ExternalModelError",
    "ExternalModelFailureCode",
    "ExternalModelSource",
]
