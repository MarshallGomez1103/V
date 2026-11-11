"""List the recordings of one project with the latest job of each."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from voz.application.job_runner import transcript_id_for
from voz.application.library import media_type_or_guess
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.project_glossary import ProjectNotFound
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)


class ProjectLookup(Protocol):
    def get(self, project_id: UUID) -> Project | None: ...


class ProjectAssets(Protocol):
    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]: ...


class AssetJobs(Protocol):
    def list_by_media_asset(
        self, media_asset_id: UUID
    ) -> Sequence[TranscriptionJob]: ...


class SelectionLookup(Protocol):
    def get(self, job_id: UUID) -> JobSelection | None: ...


class TranscriptLookup(Protocol):
    def get(self, transcript_id: UUID) -> Transcript | None: ...


@dataclass(frozen=True, slots=True)
class RecordingJob:
    id: UUID
    state: TranscriptionJobState
    transcript_id: UUID | None
    model_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Recording:
    media_asset_id: UUID
    filename: str
    media_type: str | None
    duration_ms: int | None
    created_at: datetime
    latest_job: RecordingJob | None


@dataclass(frozen=True, slots=True)
class ListRecordings:
    projects: ProjectLookup
    media_assets: ProjectAssets
    jobs: AssetJobs
    selections: SelectionLookup
    transcripts: TranscriptLookup

    def execute(self, project_id: UUID) -> Sequence[Recording]:
        """Import order; identity breaks ties so the order is deterministic."""
        if self.projects.get(project_id) is None:
            raise ProjectNotFound(str(project_id))
        assets = sorted(
            self.media_assets.list_by_project(project_id),
            key=lambda asset: (asset.created_at, str(asset.id)),
        )
        # ponytail: one job lookup per recording (a project holds tens of
        # recordings, so N small reads). Ceiling: a SQL read model next to
        # persistence/library.py once a project holds hundreds.
        return tuple(self._recording(asset) for asset in assets)

    def _recording(self, asset: MediaAsset) -> Recording:
        jobs = self.jobs.list_by_media_asset(asset.id)
        latest = max(jobs, key=lambda job: (job.created_at, str(job.id)), default=None)
        return Recording(
            media_asset_id=asset.id,
            filename=asset.display_name,
            media_type=media_type_or_guess(asset.media_type, asset.display_name),
            duration_ms=asset.duration_ms,
            created_at=asset.created_at,
            latest_job=None if latest is None else self._job(latest),
        )

    def _job(self, job: TranscriptionJob) -> RecordingJob:
        transcript_id = transcript_id_for(job.id)
        selection = self.selections.get(job.id)
        return RecordingJob(
            id=job.id,
            state=job.state,
            transcript_id=(
                transcript_id
                if self.transcripts.get(transcript_id) is not None
                else None
            ),
            model_id=None if selection is None else selection.model.model_id,
            created_at=job.created_at,
        )


__all__ = ["ListRecordings", "Recording", "RecordingJob"]
