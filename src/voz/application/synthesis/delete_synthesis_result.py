"""Delete a finished synthesis job together with its stored audio."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from voz.application.admission import AdmissionGate
from voz.application.ports.synthesis_audio_storage import SynthesisAudioStorage
from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.application.synthesis.errors import SynthesisJobError, SynthesisJobFailureCode


@dataclass(slots=True)
class DeleteSynthesisResult:
    """File first, rows second: a failed delete leaves the record to retry.

    Storage deletion is idempotent, so retrying after a partial failure works.
    """

    jobs: SynthesisJobRepository
    audio: SynthesizedAudioRepository
    storage: SynthesisAudioStorage
    admission: AdmissionGate = field(default_factory=AdmissionGate)
    """Shared with creation so a result cannot be reused while it is deleted."""

    def execute(self, job_id: UUID) -> None:
        with self.admission.hold():
            job = self.jobs.get(job_id)
            if job is None:
                raise SynthesisJobError(
                    SynthesisJobFailureCode.JOB_NOT_FOUND,
                    "The synthesis job does not exist.",
                )
            if not job.state.is_terminal:
                raise SynthesisJobError(
                    SynthesisJobFailureCode.JOB_ACTIVE,
                    "Cancel the synthesis job before deleting it.",
                )
            stored = self.audio.get_by_job(job_id)
            if stored is not None:
                self.storage.delete(stored.relative_path)
            self.audio.delete(job_id)
            self.jobs.delete(job_id)


__all__ = ["DeleteSynthesisResult"]
