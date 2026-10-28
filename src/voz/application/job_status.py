"""Read-side rules of a transcription job: remaining time, transcript, preview."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol
from uuid import UUID

from voz.application.job_runner import transcript_id_for
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)

_MIN_ETA_BASIS: Final = 0.02
"""Below this stage fraction the elapsed time says too little to extrapolate."""

_NO_TRANSCRIPT_YET: Final = frozenset(
    {
        TranscriptionJobState.QUEUED,
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
    }
)


class TranscriptLookup(Protocol):
    def get(self, transcript_id: UUID) -> Transcript | None: ...


@dataclass(frozen=True, slots=True)
class PreviewSegment:
    start_ms: int
    end_ms: int
    text: str


def eta_seconds(job: TranscriptionJob, now: datetime | None = None) -> float | None:
    """Seconds left in the current stage, from its progress and elapsed time.

    ``None`` without a basis: the job is not running, the stage has no measure
    yet, or its clock is unknown. The estimate assumes a constant rate.
    """
    if (
        not job.state.is_processable
        or job.stage_progress is None
        or job.stage_started_at is None
    ):
        return None
    if job.stage_progress >= 1.0:
        return 0.0
    if job.stage_progress < _MIN_ETA_BASIS:
        return None
    elapsed = ((now or datetime.now(UTC)) - job.stage_started_at).total_seconds()
    if elapsed <= 0:
        return None
    return round(elapsed * (1.0 - job.stage_progress) / job.stage_progress, 1)


def job_has_transcript(job: TranscriptionJob, transcripts: TranscriptLookup) -> bool:
    """The transcript row exists from the end of transcription, before the speakers."""
    if job.state is TranscriptionJobState.COMPLETED:
        return True
    if job.state in _NO_TRANSCRIPT_YET:
        return False
    return transcripts.get(transcript_id_for(job.id)) is not None


def preview_segments(
    checkpoints: Sequence[TranscriptionCheckpoint], after_ms: int
) -> tuple[PreviewSegment, ...]:
    """Confirmed, non-blank segments that end after ``after_ms``."""
    return tuple(
        PreviewSegment(item.start_ms, item.end_ms, text)
        for checkpoint in checkpoints
        if checkpoint.owned_end_ms > after_ms
        for item in checkpoint.segments
        if item.end_ms > after_ms and (text := item.text.strip())
    )


__all__ = [
    "PreviewSegment",
    "TranscriptLookup",
    "eta_seconds",
    "job_has_transcript",
    "preview_segments",
]
