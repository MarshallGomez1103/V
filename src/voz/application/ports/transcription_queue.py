"""Ports of the project transcription queue."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.domain.entities.transcription_queue import TranscriptionQueue


@runtime_checkable
class TranscriptionQueueRepository(Protocol):
    """Persist queues and the order of the ordinary jobs they group."""

    def add(
        self,
        queue: TranscriptionQueue,
        items: Sequence[tuple[TranscriptionJob, JobSelection]],
    ) -> None:
        """Persist the queue, every job, its selection and its position or nothing.

        Positions are the indexes of ``items``, starting at zero.
        """
        ...

    def get(self, queue_id: UUID) -> TranscriptionQueue | None:
        """Return the queue, or ``None`` when absent."""
        ...

    def latest_for_project(self, project_id: UUID) -> TranscriptionQueue | None:
        """Return the most recently created queue of a project, if any."""
        ...

    def job_ids(self, queue_id: UUID) -> Sequence[UUID]:
        """Return the job identities of a queue in position order."""
        ...


class JobCanceller(Protocol):
    """Cancel one job; ``JobRunner`` is the implementation."""

    def cancel(self, job_id: UUID) -> TranscriptionJob:
        """Raise ``JobNotFound`` or ``JobTerminal`` when there is nothing to cancel."""
        ...


__all__ = ["JobCanceller", "TranscriptionQueueRepository"]
