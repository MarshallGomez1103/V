"""Whether speaker diarization can run right now (models and runtime present)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DiarizationAvailability(Protocol):
    """Cheap, side-effect-free probe; it never loads models or downloads them."""

    def is_available(self) -> bool:
        """Return whether a job may request diarization."""
        ...


__all__ = ["DiarizationAvailability"]
