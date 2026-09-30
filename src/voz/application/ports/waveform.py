"""Port and value types for precomputed waveform peaks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID


class WaveformFailureCode(StrEnum):
    """Stable failure codes for waveform peaks."""

    MEDIA_ASSET_NOT_FOUND = "media_asset_not_found"
    BUCKETS_INVALID = "peaks_buckets_invalid"
    UNAVAILABLE = "waveform_unavailable"


class WaveformError(RuntimeError):
    """Path-safe failure raised while producing waveform peaks."""

    def __init__(self, code: WaveformFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class PeakSeries:
    """Normalized ``(min, max)`` pairs in ``[-1, 1]`` plus the decoded duration."""

    duration_ms: int
    peaks: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class WaveformPeaks:
    """Use-case result for one media asset."""

    media_asset_id: UUID
    duration_ms: int
    buckets: int
    peaks: tuple[tuple[float, float], ...]


@runtime_checkable
class WaveformPeaksProvider(Protocol):
    """Decode (or reuse a cached decode of) one stored media asset."""

    def peaks(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        content_sha256: str,
        buckets: int,
    ) -> PeakSeries:
        """Return exactly ``buckets`` normalized peaks or raise ``WaveformError``."""
        ...


__all__ = [
    "PeakSeries",
    "WaveformError",
    "WaveformFailureCode",
    "WaveformPeaks",
    "WaveformPeaksProvider",
]
