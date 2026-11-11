"""One request creates a job per eligible recording; the rest is reported, not asked."""
# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from test_create_transcription_job import (
    MODEL,
    Catalog,
    Jobs,
    MediaAssets,
    Projects,
    Runtime,
    Selections,
)

from voz.application.create_transcription_job import (
    CreateJobError,
    CreateJobFailureCode,
    CreateTranscriptionJob,
)
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.job_runner import JobNotFound, JobTerminal, transcript_id_for
from voz.application.ports.diarization import DiarizationOptions
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.quality_profiles import ACADEMIC_PROFILE
from voz.application.transcription_queue import (
    CancelTranscriptionQueue,
    CreateTranscriptionQueue,
    GetTranscriptionQueue,
    QueueError,
    QueueFailureCode,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.transcription_queue import (
    QueueState,
    SkipReason,
    TranscriptionQueue,
)

S = TranscriptionJobState
NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)
PROJECT = Project("Clase", id=uuid4(), created_at=NOW)
OPTION = option_identity(MODEL)


class Queues:
    def __init__(self, jobs: Jobs, selections: Selections) -> None:
        self.queues: dict[UUID, TranscriptionQueue] = {}
        self.order: dict[UUID, list[UUID]] = {}
        self._jobs = jobs
        self._selections = selections

    def add(
        self,
        queue: TranscriptionQueue,
        items: Sequence[tuple[TranscriptionJob, JobSelection]],
    ) -> None:
        self.queues[queue.id] = queue
        for job, selection in items:
            self._jobs.add(job)
            self._selections.add(selection)
        self.order[queue.id] = [job.id for job, _ in items]

    def get(self, queue_id: UUID) -> TranscriptionQueue | None:
        return self.queues.get(queue_id)

    def latest_for_project(self, project_id: UUID) -> TranscriptionQueue | None:
        mine = [q for q in self.queues.values() if q.project_id == project_id]
        return mine[-1] if mine else None

    def job_ids(self, queue_id: UUID) -> Sequence[UUID]:
        return self.order.get(queue_id, [])


class Transcripts:
    def __init__(self) -> None:
        self.items: dict[UUID, Transcript] = {}

    def get(self, transcript_id: UUID) -> Transcript | None:
        return self.items.get(transcript_id)


class Canceller:
    """Records the order; a cancelled job becomes CANCELLED like the real runner."""

    def __init__(self, jobs: Jobs, *, vanished: frozenset[UUID] = frozenset()) -> None:
        self.jobs = jobs
        self.calls: list[UUID] = []
        self.vanished = vanished

    def cancel(self, job_id: UUID) -> TranscriptionJob:
        self.calls.append(job_id)
        if job_id in self.vanished:
            raise JobTerminal("COMPLETED")
        job = self.jobs.items[job_id]
        if job.state.is_terminal:
            raise JobTerminal(job.state.value)
        if job_id not in self.jobs.items:
            raise JobNotFound(str(job_id))
        cancelled = replace(job, state=S.CANCELLED)
        self.jobs.save(cancelled)
        return cancelled


class World:
    def __init__(self, durations: Sequence[int | None], *, cloud: bool = False) -> None:
        self.assets = [
            MediaAsset(
                PROJECT.id,
                f"{index:064x}",
                f"audio-{index}.wav",
                10,
                duration_ms=duration,
                created_at=NOW + timedelta(seconds=index),
            )
            for index, duration in enumerate(durations)
        ]
        self.jobs = Jobs()
        self.selections = Selections()
        self.queues = Queues(self.jobs, self.selections)
        self.transcripts = Transcripts()
        ids = iter(range(1, 10_000))
        self.create_job = CreateTranscriptionJob(
            GetTranscriptionOptions(Catalog(model=MODEL, cloud=cloud), Runtime()),
            Projects(PROJECT),
            MediaAssets(*reversed(self.assets)),
            self.jobs,
            self.selections,
            id_factory=lambda: UUID(int=next(ids)),
            clock=lambda: NOW,
        )
        self.create = CreateTranscriptionQueue(
            create_job=self.create_job,
            media_assets=self.create_job.media_assets,
            jobs=self.jobs,
            queues=self.queues,
        )
        self.get = GetTranscriptionQueue(
            Projects(PROJECT),
            self.queues,
            self.jobs,
            self.create_job.media_assets,
            self.transcripts,
        )

    def seed_job(self, asset: MediaAsset, state: S) -> TranscriptionJob:
        job = replace(
            TranscriptionJob.create(
                job_id=uuid4(),
                project_id=PROJECT.id,
                media_asset_id=asset.id,
                now=NOW,
            ),
            state=state,
            progress=1.0 if state is S.COMPLETED else 0.0,
        )
        self.jobs.add(job)
        return job

    def start(self, **options: object) -> UUID:
        created = self.create.execute(
            project_id=PROJECT.id,
            option_id=OPTION,
            **options,  # type: ignore[arg-type]
        )
        return created.queue_id

    def set_state(self, job_id: UUID, state: S, progress: float = 0.0) -> None:
        self.jobs.save(replace(self.jobs.items[job_id], state=state, progress=progress))


def test_creates_one_job_per_recording_in_import_order_with_same_options() -> None:
    world = World([2_000, 3_000, 4_000])
    diarization = DiarizationOptions()
    world.create_job.diarization_availability = _Available()

    created = world.create.execute(
        project_id=PROJECT.id,
        option_id=OPTION,
        language="es",
        diarization=diarization,
        profile="academic",
        prompt="  Clase de física  ",
    )

    jobs = [world.jobs.items[job_id] for job_id in created.job_ids]
    assert [job.media_asset_id for job in jobs] == [a.id for a in world.assets]
    assert {job.created_at for job in jobs} == {NOW}
    assert all(job.state is S.QUEUED for job in jobs)
    assert list(world.queues.job_ids(created.queue_id)) == list(created.job_ids)
    for job in jobs:
        selection = world.selections.items[job.id]
        assert selection.language == "es"
        assert selection.diarization == diarization
        assert selection.quality_profile == ACADEMIC_PROFILE
        assert selection.prompt == "Clase de física"
        assert selection.clip is None


class _Available:
    def runtime_available(self) -> bool:
        return True

    def models_installed(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True


def test_skips_transcribed_active_and_unmeasured_recordings_with_reasons() -> None:
    world = World([2_000, 2_000, None, 2_000, 2_000, 2_000, 2_000])
    done, active, _, failed, cancelled, both, fresh = world.assets
    world.seed_job(done, S.COMPLETED)
    world.seed_job(active, S.TRANSCRIBING)
    world.seed_job(failed, S.FAILED)
    world.seed_job(cancelled, S.CANCELLED)
    world.seed_job(both, S.COMPLETED)
    world.seed_job(both, S.QUEUED)  # a speakers rerun on a finished transcription

    queue_id = world.start()
    snapshot = world.get.by_id(queue_id)

    assert [item.media_asset_id for item in snapshot.items] == [
        failed.id,
        cancelled.id,
        fresh.id,
    ]
    assert [(s.filename, s.reason) for s in snapshot.skipped] == [
        ("audio-0.wav", SkipReason.ALREADY_TRANSCRIBED),
        ("audio-1.wav", SkipReason.JOB_ACTIVE),
        ("audio-2.wav", SkipReason.DURATION_UNKNOWN),
        ("audio-5.wav", SkipReason.ALREADY_TRANSCRIBED),
    ]
    counts = snapshot.counts
    assert (counts.total, counts.pending, counts.skipped) == (3, 3, 4)


def test_rejects_cloud_option() -> None:
    world = World([2_000, 2_000], cloud=True)

    with pytest.raises(QueueError) as error:
        world.start()

    assert error.value.code is QueueFailureCode.CLOUD_UNSUPPORTED
    assert not world.jobs.items
    assert not world.selections.items
    assert not world.queues.queues


def test_second_active_queue_is_rejected() -> None:
    world = World([2_000, 2_000])
    first = world.start()

    with pytest.raises(QueueError) as error:
        world.start()
    assert error.value.code is QueueFailureCode.ACTIVE
    assert len(world.queues.queues) == 1

    for job_id in world.queues.job_ids(first):
        world.set_state(job_id, S.FAILED)
    assert world.get.by_id(first).state is QueueState.FINISHED
    # Finished (even with errors) frees the project; the failed recordings are eligible.
    second = world.start()
    assert second != first
    assert world.get.for_project(PROJECT.id) == world.get.by_id(second)


def test_empty_queue_reports_skipped() -> None:
    world = World([None, 2_000])
    world.seed_job(world.assets[1], S.COMPLETED)

    with pytest.raises(QueueError) as error:
        world.start()

    assert error.value.code is QueueFailureCode.EMPTY
    assert [(s.filename, s.reason) for s in error.value.skipped] == [
        ("audio-0.wav", SkipReason.DURATION_UNKNOWN),
        ("audio-1.wav", SkipReason.ALREADY_TRANSCRIBED),
    ]
    assert not world.queues.queues


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"profile": "nope"}, CreateJobFailureCode.QUALITY_PROFILE_UNKNOWN),
        ({"prompt": "x" * 601}, CreateJobFailureCode.PROMPT_INVALID),
        (
            {"diarization": DiarizationOptions()},
            CreateJobFailureCode.DIARIZATION_UNAVAILABLE,
        ),
    ],
)
def test_invalid_options_create_nothing(
    options: dict[str, object], code: CreateJobFailureCode
) -> None:
    world = World([2_000, 2_000])

    with pytest.raises(CreateJobError) as error:
        world.start(**options)

    assert error.value.code is code
    assert not world.jobs.items
    assert not world.queues.queues


def test_unknown_project_and_unknown_option_are_the_job_errors() -> None:
    world = World([2_000])
    with pytest.raises(CreateJobError) as no_project:
        world.create.execute(project_id=uuid4(), option_id=OPTION)
    with pytest.raises(CreateJobError) as no_option:
        world.create.execute(project_id=PROJECT.id, option_id="option-v1-missing")

    assert no_project.value.code is CreateJobFailureCode.PROJECT_NOT_FOUND
    assert no_option.value.code is CreateJobFailureCode.OPTION_UNKNOWN
    assert not world.queues.queues


def test_snapshot_derives_counts_state_and_progress_from_the_jobs() -> None:
    world = World([2_000] * 5)
    queue_id = world.start()
    first, second, third, fourth, fifth = world.queues.job_ids(queue_id)
    world.set_state(first, S.COMPLETED, 1.0)
    world.set_state(second, S.FAILED, 0.4)
    world.set_state(third, S.CANCELLED, 0.1)
    world.set_state(fourth, S.DIARIZING, 0.5)
    world.transcripts.items[transcript_id_for(fourth)] = object()  # type: ignore[assignment]
    world.jobs.save(replace(world.jobs.items[second], error_code="provider_failed"))

    snapshot = world.get.by_id(queue_id)

    counts = snapshot.counts
    assert (
        counts.total,
        counts.pending,
        counts.running,
        counts.done,
        counts.error,
        counts.cancelled,
        counts.skipped,
    ) == (5, 1, 1, 1, 1, 1, 0)
    assert snapshot.state is QueueState.RUNNING
    assert snapshot.progress == pytest.approx((3 + 0.5) / 5)
    assert [item.position for item in snapshot.items] == [0, 1, 2, 3, 4]
    assert snapshot.items[0].transcript_id == transcript_id_for(first)
    assert snapshot.items[1].job.error_code == "provider_failed"
    assert snapshot.items[2].transcript_id is None
    assert snapshot.items[3].transcript_id == transcript_id_for(fourth)
    assert snapshot.items[4].transcript_id is None
    assert fifth == snapshot.items[4].job.id

    world.set_state(fourth, S.COMPLETED, 1.0)
    world.set_state(fifth, S.CANCELLED)
    assert world.get.by_id(queue_id).state is QueueState.FINISHED
    assert world.get.by_id(queue_id).progress == 1.0


def test_get_reports_missing_project_queue_and_none_before_any() -> None:
    world = World([2_000])
    assert world.get.for_project(PROJECT.id) is None
    with pytest.raises(QueueError) as no_queue:
        world.get.by_id(uuid4())
    with pytest.raises(QueueError) as no_project:
        world.get.for_project(uuid4())

    assert no_queue.value.code is QueueFailureCode.NOT_FOUND
    assert no_project.value.code is QueueFailureCode.PROJECT_NOT_FOUND


def test_cancel_queue_cancels_pending_items_then_running() -> None:
    world = World([2_000] * 5)
    queue_id = world.start()
    first, second, third, fourth, fifth = world.queues.job_ids(queue_id)
    world.set_state(first, S.COMPLETED, 1.0)
    world.set_state(second, S.TRANSCRIBING, 0.3)
    canceller = Canceller(world.jobs)

    CancelTranscriptionQueue(world.queues, world.jobs, canceller).execute(queue_id)

    assert canceller.calls == [third, fourth, fifth, second]
    states = [world.jobs.items[j].state for j in (first, second, third, fourth, fifth)]
    assert states == [S.COMPLETED, S.CANCELLED, S.CANCELLED, S.CANCELLED, S.CANCELLED]


def test_cancel_tolerates_an_item_that_finished_meanwhile() -> None:
    world = World([2_000] * 3)
    queue_id = world.start()
    first, second, third = world.queues.job_ids(queue_id)
    canceller = Canceller(world.jobs, vanished=frozenset({second}))

    CancelTranscriptionQueue(world.queues, world.jobs, canceller).execute(queue_id)

    assert world.jobs.items[first].state is S.CANCELLED
    assert world.jobs.items[third].state is S.CANCELLED


def test_cancel_unknown_or_finished_queue_is_typed() -> None:
    world = World([2_000])
    queue_id = world.start()
    cancel = CancelTranscriptionQueue(world.queues, world.jobs, Canceller(world.jobs))
    with pytest.raises(QueueError) as unknown:
        cancel.execute(uuid4())
    (only,) = world.queues.job_ids(queue_id)
    world.set_state(only, S.COMPLETED, 1.0)
    with pytest.raises(QueueError) as finished:
        cancel.execute(queue_id)

    assert unknown.value.code is QueueFailureCode.NOT_FOUND
    assert finished.value.code is QueueFailureCode.FINISHED
