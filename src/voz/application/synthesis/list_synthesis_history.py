"""List recent synthesis jobs with the audio of the completed ones."""

from __future__ import annotations

from dataclasses import dataclass

from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesized_audio import SynthesizedAudio

DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200


@dataclass(frozen=True, slots=True)
class SynthesisHistoryItem:
    job: SynthesisJob
    audio: SynthesizedAudio | None = None
    """Present only for a COMPLETED job."""


@dataclass(slots=True)
class ListSynthesisHistory:
    jobs: SynthesisJobRepository
    audio: SynthesizedAudioRepository

    def execute(
        self, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> tuple[SynthesisHistoryItem, ...]:
        """Newest first; ``limit`` is clamped to ``1..MAX_HISTORY_LIMIT``."""
        limit = min(max(limit, 1), MAX_HISTORY_LIMIT)
        return tuple(
            SynthesisHistoryItem(
                job,
                self.audio.get_by_job(job.id)
                if job.state is SynthesisJobState.COMPLETED
                else None,
            )
            for job in self.jobs.list_recent(limit)
        )


__all__ = [
    "DEFAULT_HISTORY_LIMIT",
    "MAX_HISTORY_LIMIT",
    "ListSynthesisHistory",
    "SynthesisHistoryItem",
]
