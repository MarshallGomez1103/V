"""Read model for the library: one summary row per project."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from voz.domain.entities.transcription_job import TranscriptionJobState


@dataclass(frozen=True, slots=True)
class LibraryMedia:
    media_asset_id: UUID
    filename: str | None
    media_type: str | None
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class LibraryJob:
    id: UUID
    state: TranscriptionJobState
    transcript_id: UUID | None
    """Set only when the transcript row already exists."""
    model_id: str | None
    progress: float
    error_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    project_id: UUID
    name: str
    created_at: datetime
    media: LibraryMedia | None
    """``None`` for a project that never got a recording."""
    latest_job: LibraryJob | None
    speaker_count: int
    segment_count: int
    """Both counts belong to the latest job's transcript (0 without one)."""

    @property
    def activity_at(self) -> datetime:
        job = self.latest_job
        return self.created_at if job is None else max(self.created_at, job.updated_at)


@runtime_checkable
class LibraryReader(Protocol):
    def entries(self) -> Sequence[LibraryEntry]:
        """Every project, in any order."""
        ...


__all__ = ["LibraryEntry", "LibraryJob", "LibraryMedia", "LibraryReader"]
