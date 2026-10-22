"""Redo only the speakers of a finished transcript, without re-transcribing.

The transcript's own job is sent back to ``DIARIZING``: the runner then reports
the same stage progress and ETA as any job, a restart resumes it, and it ends in
``COMPLETED`` again. Names and colors of speakers that the new run recognises (by
overlap, see ``assign_speakers``) are kept; manual segment reassignments are not.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from voz.application.admission import AdmissionGate
from voz.application.job_runner import TRANSCRIBE_END_WITH_SPEAKERS, transcript_id_for
from voz.application.ports.diarization import DiarizationOptions
from voz.application.ports.diarization_availability import DiarizationAvailability
from voz.application.ports.repositories import (
    TranscriptionJobRepository,
    TranscriptRepository,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.domain.entities.transcription_job import (
    InvalidJobTransition,
    TranscriptionJob,
)


class RediarizeFailureCode(StrEnum):
    TRANSCRIPT_NOT_FOUND = "transcript_not_found"
    JOB_NOT_FOUND = "rediarize_unavailable"
    JOB_ALREADY_ACTIVE = "job_already_active"
    DIARIZATION_UNAVAILABLE = "diarization_unavailable"
    DIARIZATION_MODELS_MISSING = "diarization_models_missing"


class RediarizeError(RuntimeError):
    def __init__(self, code: RediarizeFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class Rediarization:
    job: TranscriptionJob
    selection: JobSelection


@dataclass(slots=True)
class RediarizeTranscript:
    transcripts: TranscriptRepository
    jobs: TranscriptionJobRepository
    selections: TranscriptionJobSelectionRepository
    availability: DiarizationAvailability
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    admission: AdmissionGate = field(default_factory=AdmissionGate)
    """Shared with job creation; the default is a private gate."""

    def execute(
        self, transcript_id: UUID, options: DiarizationOptions
    ) -> Rediarization:
        """Reopen the owning job; the caller enqueues it on the runner."""
        with self.admission.hold():
            return self._reopen(transcript_id, options)

    def _reopen(
        self, transcript_id: UUID, options: DiarizationOptions
    ) -> Rediarization:
        """The active-job check and the reopening are atomic under the gate.

        # ponytail: selection and job are two writes; a crash between them leaves
        # the new options on a finished job, which is harmless.
        """
        transcript = self.transcripts.get(transcript_id)
        if transcript is None:
            raise RediarizeError(
                RediarizeFailureCode.TRANSCRIPT_NOT_FOUND,
                "The transcript does not exist.",
            )
        owner = next(
            (
                job
                for job in self.jobs.list_by_project(transcript.project_id)
                if transcript_id_for(job.id) == transcript_id
            ),
            None,
        )
        if owner is None:
            raise RediarizeError(
                RediarizeFailureCode.JOB_NOT_FOUND,
                "This transcript has no job to recompute speakers from.",
            )
        if self.jobs.list_recoverable():
            raise RediarizeError(
                RediarizeFailureCode.JOB_ALREADY_ACTIVE,
                "Another job is running. Wait for it to finish or cancel it.",
            )
        if not self.availability.runtime_available():
            raise RediarizeError(
                RediarizeFailureCode.DIARIZATION_UNAVAILABLE,
                "Speaker diarization is not available. Install its runtime.",
            )
        if not self.availability.models_installed():
            raise RediarizeError(
                RediarizeFailureCode.DIARIZATION_MODELS_MISSING,
                "The speaker models are not installed. "
                "Download them in the model manager.",
            )
        try:
            reopened = owner.reopen_for_diarization(
                progress=TRANSCRIBE_END_WITH_SPEAKERS,
                at=max(self.clock(), owner.updated_at),
            )
        except InvalidJobTransition:
            raise RediarizeError(
                RediarizeFailureCode.JOB_NOT_FOUND,
                "Only a completed transcription can recompute its speakers.",
            ) from None
        self.selections.replace_diarization(owner.id, options)
        self.jobs.save(reopened)
        selection = self.selections.get(owner.id)
        assert selection is not None
        return Rediarization(reopened, selection)


__all__ = [
    "Rediarization",
    "RediarizeError",
    "RediarizeFailureCode",
    "RediarizeTranscript",
]
