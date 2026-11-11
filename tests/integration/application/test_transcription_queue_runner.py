"""A project queue is ordinary jobs: the global worker runs them in position order."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import shutil
import threading
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import Engine, insert

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.job_runner import JobRunner
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.transcription_queue import (
    CancelTranscriptionQueue,
    CreateTranscriptionQueue,
    GetTranscriptionQueue,
    QueueItemView,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.transcription_queue import QueueItemStatus, QueueState
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.schema import (
    metadata,
    transcription_queue_items,
    transcription_queues,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.infrastructure.persistence.transcription_queues import (
    SqliteTranscriptionQueueRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
WAV_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"
BASE_TIME = datetime(2026, 11, 11, 12, tzinfo=UTC)


class _NoPreparer:
    def prepare(
        self,
        *,
        project_id: object,
        media_asset_id: object,
        cancellation: MediaNormalizationCancellationToken | None = None,
        on_progress: object = None,
    ) -> None:
        raise AssertionError("derivative already exists")


def _unused() -> NoReturn:
    raise AssertionError("recover must not run a job")


def _runner(engine: Engine, root: Path) -> JobRunner:
    """A runner that is never started: ``recover`` only re-enqueues."""
    return JobRunner(
        jobs=SqliteTranscriptionJobRepository(engine),
        selections=SqliteTranscriptionJobSelectionRepository(engine),
        media_assets=SqliteMediaAssetRepository(engine),
        transcripts=SqliteTranscriptRepository(engine),
        segments=SqliteSegmentRepository(engine),
        checkpoints=SqliteTranscriptionCheckpointStore(engine),
        provider_for=lambda selection: _unused(),
        audio_source_for=lambda project_id, media_asset_id: (
            FileSystemInferenceAudioSource(root, project_id, media_asset_id)
        ),
        audio_preparer=_NoPreparer(),
        clock=lambda: BASE_TIME,
    )


def test_recover_orders_queue_items_by_position_under_frozen_clock(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    metadata.create_all(engine)
    project = Project("Clase", created_at=BASE_TIME)
    SqliteProjectRepository(engine).add(project)
    jobs = SqliteTranscriptionJobRepository(engine)
    assets = SqliteMediaAssetRepository(engine)
    # Ten jobs created in the same instant. Position 0 gets the largest id, so the
    # old (created_at, id) order is exactly the reverse of the queue order.
    ids = sorted((uuid4() for _ in range(10)), reverse=True)
    for index, job_id in enumerate(ids):
        asset = MediaAsset(
            project.id, f"{index:064x}", f"clase-{index}.wav", 1_000, duration_ms=250
        )
        assets.add(asset)
        jobs.add(
            TranscriptionJob.create(
                job_id=job_id,
                project_id=project.id,
                media_asset_id=asset.id,
                now=BASE_TIME,
            )
        )
    queue_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(transcription_queues).values(
                id=str(queue_id),
                project_id=str(project.id),
                created_at=BASE_TIME.isoformat(),
                skipped_json="[]",
            )
        )
        connection.execute(
            insert(transcription_queue_items),
            [
                {"queue_id": str(queue_id), "position": position, "job_id": str(job_id)}
                for position, job_id in enumerate(ids)
            ],
        )
    # A standalone job from the same instant and a later one frame the queue.
    alone = TranscriptionJob.create(
        job_id=UUID(int=0),
        project_id=project.id,
        media_asset_id=assets.list_by_project(project.id)[0].id,
        now=BASE_TIME,
    )
    later = TranscriptionJob.create(
        job_id=uuid4(),
        project_id=project.id,
        media_asset_id=assets.list_by_project(project.id)[1].id,
        now=BASE_TIME + timedelta(seconds=1),
    )
    jobs.add(alone)
    jobs.add(later)

    recovered = _runner(engine, tmp_path).recover()

    # No queue position sorts first (NULL), then the queue by position, then later jobs.
    assert recovered == (alone.id, *ids, later.id)


MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16,),
        ComputePrecision.INT8,
    ),
)
RECORDINGS = 10


class _Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (ModelRegistration(MODEL, InstallationStatus.REGISTERED, True),)


class _Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        del provider_id
        return RuntimeAvailability(
            True,
            HardwareCapabilities(frozenset(), frozenset({ComputePrecision.INT8})),
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


@dataclass(slots=True)
class _Provider:
    """Fake engine that knows its recording and how many jobs are in flight."""

    project_jobs: Callable[[], Sequence[TranscriptionJob]]
    current: UUID | None = None
    fail_for: UUID | None = None
    block_first: threading.Event | None = None
    entered: threading.Event = field(default_factory=threading.Event)
    seen: list[UUID] = field(default_factory=list[UUID])
    max_busy: int = 0
    provider_id: str = "fake-asr"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del options, cancellation
        assert self.current is not None
        if self.current not in self.seen:
            self.seen.append(self.current)
        busy = sum(
            1
            for job in self.project_jobs()
            if job.state is not TranscriptionJobState.QUEUED
            and not job.state.is_terminal
        )
        self.max_busy = max(self.max_busy, busy)
        if self.block_first is not None:
            self.entered.set()
            assert self.block_first.wait(15), "the test never released the engine"
            self.block_first = None
        if self.current == self.fail_for:
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED, "the engine failed"
            )
        with wave.open(audio, "rb") as source:
            duration_ms = source.getnframes() * 1_000 // source.getframerate()
        return TranscriptionResult((TranscriptionSegment(0, duration_ms, "ok"),), "es")


@dataclass(slots=True)
class Harness:
    engine: Engine
    root: Path
    project: Project
    assets: list[MediaAsset]
    provider: _Provider
    create: CreateTranscriptionQueue
    get: GetTranscriptionQueue

    def runner(self) -> JobRunner:
        ticks = iter(range(1, 100_000))

        def audio_source(
            project_id: UUID, media_asset_id: UUID
        ) -> FileSystemInferenceAudioSource:
            self.provider.current = media_asset_id
            return FileSystemInferenceAudioSource(self.root, project_id, media_asset_id)

        return JobRunner(
            jobs=SqliteTranscriptionJobRepository(self.engine),
            selections=SqliteTranscriptionJobSelectionRepository(self.engine),
            media_assets=SqliteMediaAssetRepository(self.engine),
            transcripts=SqliteTranscriptRepository(self.engine),
            segments=SqliteSegmentRepository(self.engine),
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=lambda selection: self.provider,
            audio_source_for=audio_source,
            audio_preparer=_NoPreparer(),
            clock=lambda: BASE_TIME + timedelta(seconds=next(ticks)),
            chunk_duration_ms=100,
            overlap_ms=20,
        )

    def start_queue(self, runner: JobRunner) -> UUID:
        created = self.create.execute(
            project_id=self.project.id,
            option_id=option_identity(MODEL),
            language="es",
        )
        for job_id in created.job_ids:
            runner.enqueue(job_id)
        return created.queue_id

    def items(self, queue_id: UUID) -> tuple[QueueItemView, ...]:
        return self.get.by_id(queue_id).items


def harness(tmp_path: Path, recordings: int = RECORDINGS) -> Harness:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    metadata.create_all(engine)
    project = Project("Clase", created_at=BASE_TIME)
    SqliteProjectRepository(engine).add(project)
    media = SqliteMediaAssetRepository(engine)
    root = tmp_path / "data"
    assets: list[MediaAsset] = []
    for index in range(recordings):
        asset = MediaAsset(
            project.id,
            f"{index:064x}",
            f"clase-{index}.wav",
            8_044,
            duration_ms=250,
            created_at=BASE_TIME + timedelta(seconds=index),
        )
        media.add(asset)
        assets.append(asset)
        target = root / "projects" / str(project.id) / "derivatives"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(WAV_FIXTURE, target / f"{asset.id}.inference.wav")
    jobs = SqliteTranscriptionJobRepository(engine)
    queues = SqliteTranscriptionQueueRepository(engine)
    create_job = CreateTranscriptionJob(
        GetTranscriptionOptions(_Catalog(), _Runtime()),
        SqliteProjectRepository(engine),
        media,
        jobs,
        SqliteTranscriptionJobSelectionRepository(engine),
        job_writer=jobs,
        clock=lambda: BASE_TIME,
    )
    provider = _Provider(lambda: jobs.list_by_project(project.id))
    return Harness(
        engine,
        root,
        project,
        assets,
        provider,
        CreateTranscriptionQueue(create_job, media, jobs, queues),
        GetTranscriptionQueue(
            SqliteProjectRepository(engine),
            queues,
            jobs,
            media,
            SqliteTranscriptRepository(engine),
        ),
    )


def test_ten_recordings_run_in_order_one_at_a_time(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    runner = fixture.runner()
    runner.start()
    try:
        queue_id = fixture.start_queue(runner)
        assert runner.wait_idle(30)
    finally:
        runner.stop()

    items = fixture.items(queue_id)
    assert [item.status for item in items] == [QueueItemStatus.DONE] * RECORDINGS
    assert fixture.provider.seen == [asset.id for asset in fixture.assets]
    assert fixture.provider.max_busy == 1
    # Finished one after the other, in position order.
    finished = [item.job.updated_at for item in items]
    assert finished == sorted(finished)
    assert fixture.get.by_id(queue_id).state is QueueState.FINISHED
    assert fixture.get.by_id(queue_id).progress == 1.0


def test_failure_of_one_item_does_not_stop_the_queue(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    fixture.provider.fail_for = fixture.assets[3].id
    runner = fixture.runner()
    runner.start()
    try:
        queue_id = fixture.start_queue(runner)
        assert runner.wait_idle(30)
    finally:
        runner.stop()

    items = fixture.items(queue_id)
    expected = [QueueItemStatus.DONE] * RECORDINGS
    expected[3] = QueueItemStatus.ERROR
    assert [item.status for item in items] == expected
    assert items[3].job.error_code is not None
    assert "/" not in items[3].job.error_code
    assert fixture.get.by_id(queue_id).state is QueueState.FINISHED
    counts = fixture.get.by_id(queue_id).counts
    assert (counts.done, counts.error, counts.total) == (9, 1, 10)


def test_cancel_queue_cancels_pending_items_then_running(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    release = threading.Event()
    fixture.provider.block_first = release
    runner = fixture.runner()
    runner.start()
    try:
        queue_id = fixture.start_queue(runner)
        assert fixture.provider.entered.wait(15), "the first item never started"
        jobs = SqliteTranscriptionJobRepository(fixture.engine)
        CancelTranscriptionQueue(
            SqliteTranscriptionQueueRepository(fixture.engine), jobs, runner
        ).execute(queue_id)
        release.set()
        assert runner.wait_idle(30)
    finally:
        release.set()
        runner.stop()

    items = fixture.items(queue_id)
    assert [item.status for item in items] == [QueueItemStatus.CANCELLED] * RECORDINGS
    # Nothing after the running item ever reached the engine.
    assert fixture.provider.seen == [fixture.assets[0].id]
    assert fixture.get.by_id(queue_id).state is QueueState.FINISHED


def test_restart_resumes_unfinished_items_in_order_without_repeating_finished(
    tmp_path: Path,
) -> None:
    fixture = harness(tmp_path)
    first = fixture.runner()
    queue_id = fixture.start_queue(first)  # created, worker never started
    jobs = SqliteTranscriptionJobRepository(fixture.engine)
    ordered = [item.job for item in fixture.items(queue_id)]
    # The first three finished before "closing the app".
    for job in ordered[:3]:
        done = job
        for state in (
            TranscriptionJobState.PROBING,
            TranscriptionJobState.PREPROCESSING,
            TranscriptionJobState.TRANSCRIBING,
            TranscriptionJobState.ALIGNING,
            TranscriptionJobState.DIARIZING,
            TranscriptionJobState.MERGING,
            TranscriptionJobState.PERSISTING,
            TranscriptionJobState.COMPLETED,
        ):
            done = done.transition_to(state, at=BASE_TIME + timedelta(seconds=1))
        jobs.save(done)

    second = fixture.runner()
    recovered = second.recover()
    second.start()
    try:
        assert second.wait_idle(30)
    finally:
        second.stop()

    assert recovered == tuple(job.id for job in ordered[3:])
    assert fixture.provider.seen == [asset.id for asset in fixture.assets[3:]]
    statuses = [item.status for item in fixture.items(queue_id)]
    assert statuses == [QueueItemStatus.DONE] * RECORDINGS
