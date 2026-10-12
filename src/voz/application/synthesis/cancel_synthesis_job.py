"""Request cancellation of a synthesis job."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from voz.application.ports.synthesis_repositories import SynthesisJobRepository
from voz.application.synthesis.errors import SynthesisJobError, SynthesisJobFailureCode
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState


def _ignore(_job_id: UUID) -> None:
    return None


@dataclass(slots=True)
class CancelSynthesisJob:
    """QUEUED jobs end CANCELLED now; started ones become CANCELLING.

    A started job is finished by whoever runs it (the synthesis runner), so
    ``interrupt`` is called with its id to make that worker stop. Cancelling a
    job that is already CANCELLING is idempotent and signals again.
    """

    jobs: SynthesisJobRepository
    interrupt: Callable[[UUID], None] = _ignore
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def execute(self, job_id: UUID) -> SynthesisJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise SynthesisJobError(
                SynthesisJobFailureCode.JOB_NOT_FOUND,
                "The synthesis job does not exist.",
            )
        if job.state.is_terminal:
            raise SynthesisJobError(
                SynthesisJobFailureCode.JOB_TERMINAL,
                "The synthesis job has already finished.",
            )
        if job.state is SynthesisJobState.CANCELLING:
            self.interrupt(job_id)
            return job
        at = max(self.clock(), job.updated_at)
        queued = job.state is SynthesisJobState.QUEUED
        cancelling = job.transition_to(SynthesisJobState.CANCELLING, at=at)
        if queued:
            cancelling = cancelling.transition_to(SynthesisJobState.CANCELLED, at=at)
        self.jobs.save(cancelling)
        if not queued:
            self.interrupt(job_id)
        return cancelling


__all__ = ["CancelSynthesisJob"]
