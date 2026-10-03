"""Whether speaker diarization can run right now (models and runtime present)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DiarizationAvailability(Protocol):
    """Cheap, side-effect-free probe; it never loads models or downloads them."""

    def runtime_available(self) -> bool:
        """Return whether the optional diarization runtime is importable."""
        ...

    def models_installed(self) -> bool:
        """Return whether the speaker models are installed (downloadable otherwise)."""
        ...

    def is_available(self) -> bool:
        """Return whether a job may request diarization (runtime and models)."""
        ...


__all__ = ["DiarizationAvailability"]
