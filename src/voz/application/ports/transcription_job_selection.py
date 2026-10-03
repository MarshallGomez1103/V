"""Durable, reproducible snapshot of the option selected for one job."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast, runtime_checkable
from uuid import UUID

from voz.application.asr_device_selection import ExecutionDecision
from voz.application.ports.diarization import DiarizationOptions
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.quality_profile import QualityProfile
from voz.domain.entities.transcription_job import TranscriptionJob


@dataclass(frozen=True, slots=True)
class JobSelection:
    """Everything needed to rebuild the exact provider request later.

    The full ``ModelDescriptor`` is kept (not only its identity) so that a
    provider configured for one descriptor accepts the request unchanged after
    a restart, and so the job stays reproducible when the catalog moves on.
    """

    job_id: UUID
    option_id: str
    model: ModelDescriptor
    execution: ExecutionDecision | None
    language: str | None
    created_at: datetime
    diarization: DiarizationOptions | None = None
    """Speaker diarization requested for this job; ``None`` means disabled."""
    diarization_error_code: str | None = None
    """Stable code when diarization failed but the transcript was kept."""
    quality_profile: QualityProfile | None = None
    """Full decoding recipe used (S13.02); ``None`` for jobs from before profiles."""
    glossary: tuple[str, ...] = ()
    """Project glossary at creation time, frozen so the job can be repeated."""
    prompt: str | None = None
    """Style instruction for the ASR engine (initial prompt); ``None`` means none."""

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.job_id), UUID):
            raise TypeError("job_id must be a UUID")
        if not isinstance(cast(object, self.model), ModelDescriptor):
            raise TypeError("model must be a ModelDescriptor")
        if not self.option_id or self.option_id != self.option_id.strip():
            raise ValueError("option_id must be a non-empty trimmed string")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if not isinstance(cast(object, self.glossary), tuple):
            raise TypeError("glossary must be a tuple of strings")


@runtime_checkable
class TranscriptionJobSelectionRepository(Protocol):
    """Persist exactly one selection snapshot per transcription job."""

    def add(self, selection: JobSelection) -> None:
        """Persist the snapshot for a job that has none yet."""
        ...

    def get(self, job_id: UUID) -> JobSelection | None:
        """Return the snapshot for a job, or ``None`` when absent."""
        ...

    def record_diarization_error(self, job_id: UUID, code: str) -> None:
        """Persist why diarization failed; the rest of the snapshot is immutable."""
        ...


@runtime_checkable
class JobWithSelectionWriter(Protocol):
    """Create a job and its selection snapshot as one atomic write."""

    def add_with_selection(
        self, job: TranscriptionJob, selection: JobSelection
    ) -> None:
        """Persist both or neither; a failure leaves no orphan job."""
        ...


__all__ = [
    "JobSelection",
    "JobWithSelectionWriter",
    "TranscriptionJobSelectionRepository",
]
