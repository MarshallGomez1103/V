"""Contract for a future word aligner that refines canonical segments.

Today VOZ does not implement it: word timings come straight from the ASR
provider when it declares ``ModelCapability.WORD_TIMESTAMPS`` (faster-whisper's
native DTW word timestamps, see ADR-0008) and ride on
``TranscriptionSegment.words``. This port only fixes the seam so a separate
aligner (for example a forced-alignment engine) can be added later without
touching the pipeline; do not build a plugin framework before a second real
implementation exists.
"""

from __future__ import annotations

from typing import BinaryIO, Protocol, runtime_checkable

from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionSegment,
    TranscriptionWord,
)


@runtime_checkable
class AlignmentProvider(Protocol):
    """Locate the words of already transcribed segments in the audio."""

    @property
    def provider_id(self) -> str:
        """Return the stable identifier of this aligner."""
        ...

    def align(
        self,
        *,
        audio: BinaryIO,
        segments: tuple[TranscriptionSegment, ...],
        language: str | None = None,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> tuple[tuple[TranscriptionWord, ...], ...]:
        """Return one word tuple per input segment, in the same order.

        Offsets share the segments' timeline and must lie inside their segment.
        A segment the aligner cannot place gets an empty tuple; an unsupported
        language or a failed alignment raises ``TranscriptionError`` and callers
        keep the segments without words (the job never fails because of words).
        """
        ...


__all__ = ["AlignmentProvider"]
