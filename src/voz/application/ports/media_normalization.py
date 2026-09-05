"""Application contract for producing inference-ready audio derivatives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO, Protocol, runtime_checkable
from uuid import UUID


class MediaNormalizationFailureCode(StrEnum):
    """Stable failure categories suitable for use-case and API translation."""

    TOOL_UNAVAILABLE = "media_normalization_tool_unavailable"
    INVALID_SOURCE = "media_normalization_invalid_source"
    UNSAFE_DESTINATION = "media_normalization_unsafe_destination"
    DESTINATION_EXISTS = "media_normalization_destination_exists"
    PROCESS_FAILED = "media_normalization_process_failed"
    CORRUPTED_MEDIA = "media_normalization_corrupted_media"
    CANCELLED = "media_normalization_cancelled"
    IO_ERROR = "media_normalization_io_error"


class MediaNormalizationError(RuntimeError):
    """Typed normalization failure with a path-safe user message."""

    def __init__(
        self,
        code: MediaNormalizationFailureCode,
        user_message: str,
    ) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class MediaNormalizationProgress:
    """Monotonic progress sample for one normalization operation."""

    processed_ms: int
    total_ms: int

    def __post_init__(self) -> None:
        if type(self.total_ms) is not int or self.total_ms <= 0:
            raise ValueError("total_ms must be a positive integer")
        if (
            type(self.processed_ms) is not int
            or self.processed_ms < 0
            or self.processed_ms > self.total_ms
        ):
            raise ValueError("processed_ms must be between zero and total_ms")

    @property
    def fraction(self) -> float:
        """Return normalized progress in the inclusive range zero to one."""

        return self.processed_ms / self.total_ms


@dataclass(frozen=True, slots=True)
class NormalizedAudio:
    """Metadata for a successfully published inference derivative."""

    bytes_written: int
    sample_rate_hz: int = 16_000
    channels: int = 1

    def __post_init__(self) -> None:
        if type(self.bytes_written) is not int or self.bytes_written <= 0:
            raise ValueError("bytes_written must be a positive integer")
        if self.sample_rate_hz != 16_000:
            raise ValueError("normalized audio must use a 16 kHz sample rate")
        if self.channels != 1:
            raise ValueError("normalized audio must be mono")


@runtime_checkable
class MediaNormalizationCancellationToken(Protocol):
    """Minimal cooperative cancellation contract with no framework dependency."""

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        ...


MediaNormalizationProgressCallback = Callable[[MediaNormalizationProgress], None]


@runtime_checkable
class MediaNormalizationPort(Protocol):
    """Create a mono 16 kHz PCM derivative without changing the original."""

    def normalize(
        self,
        *,
        original: BinaryIO,
        project_id: UUID,
        media_asset_id: UUID,
        duration_ms: int,
        audio_stream_index: int,
        on_progress: MediaNormalizationProgressCallback | None = None,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> NormalizedAudio:
        """Normalize an opened original and publish its identity-derived output."""
        ...


__all__ = [
    "MediaNormalizationCancellationToken",
    "MediaNormalizationError",
    "MediaNormalizationFailureCode",
    "MediaNormalizationPort",
    "MediaNormalizationProgress",
    "MediaNormalizationProgressCallback",
    "NormalizedAudio",
]
