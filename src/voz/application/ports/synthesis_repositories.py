"""Persistence ports for speech synthesis jobs and their stored audio (ADR-0010)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesized_audio import SynthesizedAudio


@runtime_checkable
class SynthesisJobRepository(Protocol):
    """Persist synthesis job snapshots for history and restart recovery."""

    def add(self, job: SynthesisJob) -> None:
        """Persist a new synthesis job."""
        ...

    def save(self, job: SynthesisJob) -> None:
        """Persist the current snapshot of an existing job."""
        ...

    def get(self, job_id: UUID) -> SynthesisJob | None:
        """Return a job by identity, or ``None`` when absent."""
        ...

    def list_recent(self, limit: int) -> Sequence[SynthesisJob]:
        """Return up to ``limit`` jobs, newest first."""
        ...

    def find_by_hash(
        self, request_hash: str, states: Collection[SynthesisJobState]
    ) -> SynthesisJob | None:
        """Return the newest job with this request hash in any of ``states``."""
        ...

    def list_recoverable(self) -> Sequence[SynthesisJob]:
        """Return non-terminal jobs that require restart recovery, oldest first."""
        ...

    def delete(self, job_id: UUID) -> bool:
        """Remove a job and its audio row; return whether the job existed."""
        ...


@runtime_checkable
class SynthesizedAudioRepository(Protocol):
    """Persist the stored result of a completed synthesis job."""

    def add(self, audio: SynthesizedAudio) -> None:
        """Persist the audio of a job; a job has at most one audio."""
        ...

    def get_by_job(self, job_id: UUID) -> SynthesizedAudio | None:
        """Return the audio of a job, or ``None`` when it has none."""
        ...

    def delete(self, job_id: UUID) -> None:
        """Remove the audio row of a job (a no-op when it has none)."""
        ...


__all__ = ["SynthesisJobRepository", "SynthesizedAudioRepository"]
