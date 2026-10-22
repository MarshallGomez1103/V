"""Application contract for the immutable audio produced by synthesis jobs."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import BinaryIO, Protocol, runtime_checkable
from uuid import UUID

from voz.application.ports.speech_synthesis import PcmAudio
from voz.domain.entities.synthesized_audio import SynthesizedAudio


class SynthesisStorageErrorCode(StrEnum):
    """Stable failure categories callers can translate without parsing text."""

    NO_AUDIO = "no_audio"
    SAMPLE_RATE_MISMATCH = "sample_rate_mismatch"
    AUDIO_EXISTS = "audio_exists"
    AUDIO_NOT_FOUND = "audio_not_found"
    INVALID_PATH = "invalid_path"
    UNSAFE_STORAGE_PATH = "unsafe_storage_path"
    IO_ERROR = "io_error"


class SynthesisStorageError(RuntimeError):
    """Typed, path-safe error raised by a synthesis audio storage adapter."""

    def __init__(self, code: SynthesisStorageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@runtime_checkable
class SynthesisAudioWriter(Protocol):
    """Builds one job's WAV chunk by chunk, so memory does not grow with its length."""

    def append(self, chunk: PcmAudio, gap_after_ms: int = 0) -> None:
        """Add ``chunk`` followed by ``gap_after_ms`` of silence (0 for the last).

        All chunks must share one sample rate.
        """
        ...

    def commit(self) -> SynthesizedAudio:
        """Publish the WAV atomically; an existing audio is never replaced."""
        ...

    def abort(self) -> None:
        """Discard everything written so far; safe to call after ``commit``."""
        ...


@runtime_checkable
class SynthesisAudioStorage(Protocol):
    """Store, serve and remove the WAV of a synthesis job; files never change."""

    def begin(self, job_id: UUID) -> SynthesisAudioWriter:
        """Start an incremental write; the caller commits or aborts it."""
        ...

    def write(
        self,
        job_id: UUID,
        chunks: Sequence[PcmAudio],
        gaps_ms: Sequence[int],
    ) -> SynthesizedAudio:
        """Join ``chunks`` into one WAV (PCM16 mono) and publish it atomically.

        ``gaps_ms[i]`` is the silence between ``chunks[i]`` and ``chunks[i + 1]``,
        so there is exactly one gap fewer than chunks. All chunks must share one
        sample rate. An existing audio is never replaced.
        """
        ...

    def open_for_reading(self, relative_path: str) -> BinaryIO:
        """Open a stored audio (seekable, for Range) without exposing host paths."""
        ...

    def delete(self, relative_path: str) -> None:
        """Remove the audio and its job directory; a no-op when already gone."""
        ...

    def delete_job(self, job_id: UUID) -> None:
        """Same as :meth:`delete`, for a job whose audio was never recorded."""
        ...


__all__ = [
    "SynthesisAudioStorage",
    "SynthesisAudioWriter",
    "SynthesisStorageError",
    "SynthesisStorageErrorCode",
]
