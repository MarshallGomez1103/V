"""``ListRecordings``: a project's recordings in import order with the latest job."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from voz.application.job_runner import transcript_id_for
from voz.application.list_recordings import ListRecordings
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.project_glossary import ProjectNotFound
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)

T0 = datetime(2026, 10, 1, 12, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="large-v3",
    display_name="Large v3",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/model",
    revision="f" * 40,
)


class Projects:
    def __init__(self, *projects: Project) -> None:
        self.items = {project.id: project for project in projects}

    def get(self, project_id: UUID) -> Project | None:
        return self.items.get(project_id)


class Assets:
    def __init__(self, *assets: MediaAsset) -> None:
        self.items = assets

    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]:
        return tuple(a for a in self.items if a.project_id == project_id)


class Jobs:
    def __init__(self, *jobs: TranscriptionJob) -> None:
        self.items = jobs

    def list_by_media_asset(self, media_asset_id: UUID) -> Sequence[TranscriptionJob]:
        return tuple(j for j in self.items if j.media_asset_id == media_asset_id)


class Selections:
    def __init__(self) -> None:
        self.items: dict[UUID, JobSelection] = {}

    def get(self, job_id: UUID) -> JobSelection | None:
        return self.items.get(job_id)


class Transcripts:
    def __init__(self, *transcripts: Transcript) -> None:
        self.items = {t.id: t for t in transcripts}

    def get(self, transcript_id: UUID) -> Transcript | None:
        return self.items.get(transcript_id)


def asset(
    project: Project,
    name: str,
    minutes: int,
    *,
    media_type: str | None = "audio/wav",
    asset_id: UUID | None = None,
) -> MediaAsset:
    return MediaAsset(
        project.id,
        "a" * 64,
        name,
        1_000,
        id=asset_id or uuid4(),
        media_type=media_type,
        duration_ms=60_000,
        created_at=T0 + timedelta(minutes=minutes),
    )


def job(
    asset_: MediaAsset,
    minutes: int,
    state: TranscriptionJobState = TranscriptionJobState.COMPLETED,
    job_id: UUID | None = None,
) -> TranscriptionJob:
    at = T0 + timedelta(minutes=minutes)
    return TranscriptionJob(
        id=job_id or uuid4(),
        project_id=asset_.project_id,
        media_asset_id=asset_.id,
        state=state,
        progress=1.0 if state is TranscriptionJobState.COMPLETED else 0.0,
        created_at=at,
        updated_at=at,
    )


def selection(job_: TranscriptionJob) -> JobSelection:
    return JobSelection(job_.id, "option-v1", MODEL, None, None, job_.created_at)


def test_lists_every_recording_in_import_order_with_latest_job() -> None:
    project = Project("Course")
    first = asset(project, "one.wav", 1)
    second = asset(project, "two.mp3", 2, media_type=None)
    third = asset(project, "three.wav", 3)
    old = job(second, 5, TranscriptionJobState.FAILED)
    latest = job(second, 6)
    selections = Selections()
    selections.items[latest.id] = selection(latest)
    transcript = Transcript(project.id, second.id, id=transcript_id_for(latest.id))
    use_case = ListRecordings(
        Projects(project),
        Assets(third, first, second),  # the repository order is not trusted
        Jobs(latest, old),  # the latest job is not the last one listed
        selections,
        Transcripts(transcript),
    )

    recordings = use_case.execute(project.id)

    assert [r.filename for r in recordings] == ["one.wav", "two.mp3", "three.wav"]
    assert [r.media_asset_id for r in recordings] == [first.id, second.id, third.id]
    assert recordings[0].latest_job is None
    assert recordings[2].latest_job is None
    assert recordings[1].media_type == "audio/mpeg"  # the extension fills the gap
    assert recordings[1].duration_ms == 60_000
    shown = recordings[1].latest_job
    assert shown is not None
    assert (shown.id, shown.state, shown.model_id, shown.created_at) == (
        latest.id,
        TranscriptionJobState.COMPLETED,
        "large-v3",
        latest.created_at,
    )
    assert shown.transcript_id == transcript.id


def test_equal_timestamps_are_ordered_by_identity() -> None:
    project = Project("Course")
    low, high = (UUID(int=1), UUID(int=2))
    use_case = ListRecordings(
        Projects(project),
        Assets(
            asset(project, "b.wav", 0, asset_id=high),
            asset(project, "a.wav", 0, asset_id=low),
        ),
        Jobs(),
        Selections(),
        Transcripts(),
    )

    assert [r.media_asset_id for r in use_case.execute(project.id)] == [low, high]


@pytest.mark.parametrize("reverse", [False, True])
def test_jobs_created_at_the_same_instant_are_ordered_by_identity(
    reverse: bool,
) -> None:
    project = Project("Course")
    recording = asset(project, "one.wav", 1)
    low = job(recording, 2, job_id=UUID(int=1))
    high = job(recording, 2, job_id=UUID(int=2))
    jobs = (high, low) if reverse else (low, high)
    use_case = ListRecordings(
        Projects(project), Assets(recording), Jobs(*jobs), Selections(), Transcripts()
    )

    (only,) = use_case.execute(project.id)

    assert only.latest_job is not None
    assert only.latest_job.id == high.id


def test_a_job_without_transcript_or_selection_reports_none() -> None:
    project = Project("Course")
    recording = asset(project, "one.wav", 1)
    running = job(recording, 2, TranscriptionJobState.TRANSCRIBING)
    use_case = ListRecordings(
        Projects(project), Assets(recording), Jobs(running), Selections(), Transcripts()
    )

    (only,) = use_case.execute(project.id)

    assert only.latest_job is not None
    assert only.latest_job.transcript_id is None
    assert only.latest_job.model_id is None
    assert only.latest_job.state is TranscriptionJobState.TRANSCRIBING


def test_only_the_recordings_of_that_project_are_listed() -> None:
    mine, other = Project("Mine"), Project("Other")
    use_case = ListRecordings(
        Projects(mine, other),
        Assets(asset(mine, "mine.wav", 1), asset(other, "other.wav", 2)),
        Jobs(),
        Selections(),
        Transcripts(),
    )

    assert [r.filename for r in use_case.execute(mine.id)] == ["mine.wav"]


def test_unknown_project_raises_not_found() -> None:
    use_case = ListRecordings(Projects(), Assets(), Jobs(), Selections(), Transcripts())

    with pytest.raises(ProjectNotFound):
        use_case.execute(uuid4())
