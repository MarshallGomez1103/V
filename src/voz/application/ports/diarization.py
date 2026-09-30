"""Provider-neutral application contract for speaker diarization.

A provider receives the same normalized derivative used by ASR (WAV PCM mono
16 kHz) and returns raw acoustic turns. Provider cluster labels are opaque and
are *not* ``Speaker`` identities: the application maps them to editable
speakers when it persists a transcript's diarization.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO, Protocol, cast, runtime_checkable

from voz.application.ports.transcription import TranscriptionCancellationToken


class DiarizationFailureCode(StrEnum):
    """Stable provider failures suitable for job and API translation."""

    CANCELLED = "diarization_cancelled"
    INVALID_AUDIO = "diarization_invalid_audio"
    MODEL_UNAVAILABLE = "diarization_model_unavailable"
    RUNTIME_UNAVAILABLE = "diarization_runtime_unavailable"
    PROVIDER_FAILED = "diarization_provider_failed"


class DiarizationError(RuntimeError):
    """Typed diarization failure with a path-safe user message."""

    def __init__(
        self,
        code: DiarizationFailureCode,
        user_message: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        super().__init__(user_message)


def _optional_positive(value: object, name: str) -> None:
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer or None")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")


@dataclass(frozen=True, slots=True)
class SpeakerCountHint:
    """Speaker-count constraint: automatic, exact, or a min/max range."""

    exact: int | None = None
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self) -> None:
        _optional_positive(self.exact, "exact")
        _optional_positive(self.minimum, "minimum")
        _optional_positive(self.maximum, "maximum")
        if self.exact is not None and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("exact excludes minimum and maximum")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum cannot exceed maximum")

    @property
    def is_automatic(self) -> bool:
        """Return whether the provider must estimate the speaker count."""

        return self.exact is None and self.minimum is None and self.maximum is None


@dataclass(frozen=True, slots=True)
class DiarizationOptions:
    """Canonical diarization request independent of engine-specific flags."""

    speakers: SpeakerCountHint = SpeakerCountHint()

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.speakers), SpeakerCountHint):
            raise TypeError("speakers must be a SpeakerCountHint")


@dataclass(frozen=True, slots=True)
class DiarizedTurn:
    """Raw acoustic interval; ``cluster`` is an opaque provider label."""

    start_ms: int
    end_ms: int
    cluster: str

    def __post_init__(self) -> None:
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("turn offsets must be integer milliseconds")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("turn offsets must be non-negative and increasing")
        raw_cluster = cast(object, self.cluster)
        if not isinstance(raw_cluster, str):
            raise TypeError("cluster must be a string")
        if not raw_cluster.strip():
            raise ValueError("cluster must not be blank")


@dataclass(frozen=True, slots=True)
class DiarizationResult:
    """Provider output; turns may be unordered and may overlap across clusters."""

    turns: tuple[DiarizedTurn, ...]

    def __post_init__(self) -> None:
        raw_turns = cast(object, self.turns)
        if not isinstance(raw_turns, tuple):
            raise TypeError("turns must be a tuple")
        for turn in cast(tuple[object, ...], raw_turns):
            if not isinstance(turn, DiarizedTurn):
                raise TypeError("turns must contain only DiarizedTurn instances")


@runtime_checkable
class DiarizationProvider(Protocol):
    """Diarize opened normalized audio without exposing host paths."""

    @property
    def provider_id(self) -> str:
        """Return the stable identifier of this provider."""
        ...

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> DiarizationResult:
        """Return acoustic turns; raise ``DiarizationError`` on typed failures."""
        ...


__all__ = [
    "DiarizationError",
    "DiarizationFailureCode",
    "DiarizationOptions",
    "DiarizationProvider",
    "DiarizationResult",
    "DiarizedTurn",
    "SpeakerCountHint",
]
