"""Integration tests for atomic chunk checkpoints, cancellation and resume."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
)
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)

BASE_TIME = datetime(2026, 9, 5, 12, tzinfo=UTC)
DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="ffffffffffffffffffffffffffffffffffffffff",
)


class _AudioContext(AbstractContextManager[BinaryIO]):
    def __init__(self, clip: TranscriptionClip) -> None:
        self.audio = BytesIO(f"{clip.start_ms}:{clip.end_ms}".encode())

    def __enter__(self) -> BinaryIO:
        return self.audio

    def __exit__(self, *args: object) -> None:
        self.audio.close()


class _AudioSource:
    def open(
        self,
        clip: TranscriptionClip | None = None,
    ) -> AbstractContextManager[BinaryIO]:
        assert clip is not None
        return _AudioContext(clip)


class _Provider:
    provider_id = "fake-asr"

    def __init__(self) -> None:
        self.clips: list[tuple[int, int]] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del cancellation
        start_ms, end_ms = (int(value) for value in audio.read().decode().split(":"))
        assert options.clip is None
        self.clips.append((start_ms, end_ms))
        return TranscriptionResult(
            segments=(
                TranscriptionSegment(
                    start_ms=0,
                    end_ms=end_ms - start_ms,
                    text=f"chunk-{start_ms}",
                ),
            ),
            language="es",
        )


class _Cancellation:
    requested = False

    def is_cancelled(self) -> bool:
        return self.requested


class SimulatedCrash(RuntimeError):
    pass


def _seed_job(database_path: Path) -> tuple[TranscriptionJob, Engine]:
    engine = create_sqlite_engine(database_path)
    metadata.create_all(engine)
    projects = SqliteProjectRepository(engine)
    assets = SqliteMediaAssetRepository(engine)
    jobs = SqliteTranscriptionJobRepository(engine)
    project = Project("Clase", id=uuid4(), created_at=BASE_TIME)
    asset = MediaAsset(
        project.id,
        "a" * 64,
        "clase.wav",
        1_024,
        id=uuid4(),
        duration_ms=65_000,
        created_at=BASE_TIME,
    )
    job = TranscriptionJob.create(
        job_id=uuid4(),
        project_id=project.id,
        media_asset_id=asset.id,
        now=BASE_TIME,
    )
    for state in (
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
    ):
        job = job.transition_to(state, at=BASE_TIME)
    projects.add(project)
    assets.add(asset)
    jobs.add(job)
    return job, engine


def test_resume_after_post_commit_crash_does_not_repeat_confirmed_chunk(
    tmp_path: Path,
) -> None:
    database_path = (tmp_path / "voz.db").absolute()
    job, first_engine = _seed_job(database_path)
    first_provider = _Provider()
    first_jobs = SqliteTranscriptionJobRepository(first_engine)
    job = job.with_progress(0.5, at=BASE_TIME)
    first_jobs.save(job)
    first_checkpoints = SqliteTranscriptionCheckpointStore(first_engine)
    coordinator = RecoverableTranscription(
        first_provider,
        _AudioSource(),
        first_checkpoints,
        first_jobs,
        clock=lambda: BASE_TIME + timedelta(seconds=1),
    )

    try:
        coordinator.execute(
            job=job,
            duration_ms=65_000,
            options=TranscriptionOptions(model=DESCRIPTOR, language="es"),
            chunk_duration_ms=30_000,
            overlap_ms=5_000,
            on_progress=lambda progress: (_ for _ in ()).throw(SimulatedCrash),
        )
    except SimulatedCrash:
        pass
    else:
        raise AssertionError("simulated crash was not raised")

    assert first_provider.clips == [(0, 35_000)]
    first_checkpoint = first_checkpoints.list_for_job(job.id)[0]
    assert first_checkpoint.model_source == DESCRIPTOR.source
    assert first_checkpoint.requested_language == "es"
    assert first_checkpoint.progress == 1 / 3
    assert first_checkpoint.job_progress == 0.5
    first_engine.dispose()

    second_engine = create_sqlite_engine(database_path)
    second_jobs = SqliteTranscriptionJobRepository(second_engine)
    resumed_job = second_jobs.get(job.id)
    assert resumed_job is not None
    assert resumed_job.progress == 0.5
    wrong_language_provider = _Provider()
    with pytest.raises(ValueError, match="requested language"):
        RecoverableTranscription(
            wrong_language_provider,
            _AudioSource(),
            SqliteTranscriptionCheckpointStore(second_engine),
            second_jobs,
            clock=lambda: BASE_TIME + timedelta(seconds=2),
        ).execute(
            job=resumed_job,
            duration_ms=65_000,
            options=TranscriptionOptions(model=DESCRIPTOR, language="fr"),
            chunk_duration_ms=30_000,
            overlap_ms=5_000,
        )
    assert wrong_language_provider.clips == []

    wrong_source_provider = _Provider()
    with pytest.raises(ValueError, match="requested plan"):
        RecoverableTranscription(
            wrong_source_provider,
            _AudioSource(),
            SqliteTranscriptionCheckpointStore(second_engine),
            second_jobs,
            clock=lambda: BASE_TIME + timedelta(seconds=2),
        ).execute(
            job=resumed_job,
            duration_ms=65_000,
            options=TranscriptionOptions(
                model=replace(DESCRIPTOR, source="another/model"),
                language="es",
            ),
            chunk_duration_ms=30_000,
            overlap_ms=5_000,
        )
    assert wrong_source_provider.clips == []

    second_provider = _Provider()
    second_checkpoints = SqliteTranscriptionCheckpointStore(second_engine)
    outcome = RecoverableTranscription(
        second_provider,
        _AudioSource(),
        second_checkpoints,
        second_jobs,
        clock=lambda: BASE_TIME + timedelta(seconds=2),
    ).execute(
        job=resumed_job,
        duration_ms=65_000,
        options=TranscriptionOptions(model=DESCRIPTOR, language="es"),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    assert second_provider.clips == [(25_000, 65_000), (55_000, 65_000)]
    assert outcome.completed_chunks == outcome.total_chunks == 3
    assert outcome.job.progress == 1.0
    assert outcome.result.language == "es"
    assert len(outcome.result.segments) == 3
    assert len(second_checkpoints.list_for_job(job.id)) == 3
    second_engine.dispose()


def test_cancellation_between_chunks_preserves_only_confirmed_prefix(
    tmp_path: Path,
) -> None:
    database_path = (tmp_path / "voz.db").absolute()
    job, engine = _seed_job(database_path)
    jobs = SqliteTranscriptionJobRepository(engine)
    checkpoints = SqliteTranscriptionCheckpointStore(engine)
    provider = _Provider()
    cancellation = _Cancellation()

    def request_cancel_after_first(_progress: object) -> None:
        cancellation.requested = True

    outcome = RecoverableTranscription(
        provider,
        _AudioSource(),
        checkpoints,
        jobs,
        clock=lambda: BASE_TIME + timedelta(seconds=1),
    ).execute(
        job=job,
        duration_ms=65_000,
        options=TranscriptionOptions(model=DESCRIPTOR),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
        on_progress=request_cancel_after_first,
        cancellation=cancellation,
    )

    assert outcome.cancelled
    assert outcome.job.state is TranscriptionJobState.CANCELLED
    assert outcome.completed_chunks == 1
    assert len(outcome.result.segments) == 1
    assert provider.clips == [(0, 35_000)]
    assert len(checkpoints.list_for_job(job.id)) == 1
    persisted = jobs.get(job.id)
    assert persisted is not None
    assert persisted.state is TranscriptionJobState.CANCELLED
    assert persisted.progress == 1 / 3
    engine.dispose()


def test_failed_checkpoint_insert_cannot_advance_job_progress(tmp_path: Path) -> None:
    job, engine = _seed_job((tmp_path / "voz.db").absolute())
    jobs = SqliteTranscriptionJobRepository(engine)
    checkpoints = SqliteTranscriptionCheckpointStore(engine)
    first_job = job.with_progress(1 / 3, at=BASE_TIME + timedelta(seconds=1))
    first = TranscriptionCheckpoint(
        job_id=job.id,
        chunk_index=0,
        process_start_ms=0,
        process_end_ms=35_000,
        owned_start_ms=0,
        owned_end_ms=30_000,
        provider_id=DESCRIPTOR.provider_id,
        model_id=DESCRIPTOR.model_id,
        model_source=DESCRIPTOR.source,
        model_revision=DESCRIPTOR.revision,
        requested_language=None,
        segments=(TranscriptionSegment(0, 30_000, "confirmed"),),
        language="es",
        progress=first_job.progress,
        job_progress=first_job.progress,
        completed_at=first_job.updated_at,
    )
    checkpoints.commit(first, first_job)

    second_job = first_job.with_progress(2 / 3, at=BASE_TIME + timedelta(seconds=2))
    duplicate = TranscriptionCheckpoint(
        job_id=job.id,
        chunk_index=0,
        process_start_ms=0,
        process_end_ms=35_000,
        owned_start_ms=0,
        owned_end_ms=30_000,
        provider_id=DESCRIPTOR.provider_id,
        model_id=DESCRIPTOR.model_id,
        model_source=DESCRIPTOR.source,
        model_revision=DESCRIPTOR.revision,
        requested_language=None,
        segments=(TranscriptionSegment(0, 30_000, "must-not-replace"),),
        language="es",
        progress=first.progress,
        job_progress=second_job.progress,
        completed_at=second_job.updated_at,
    )

    with pytest.raises(IntegrityError):
        checkpoints.commit(duplicate, second_job)

    persisted = jobs.get(job.id)
    assert persisted is not None
    assert persisted.progress == 1 / 3
    assert checkpoints.list_for_job(job.id) == (first,)
    engine.dispose()


def _checkpoint_with(
    job: TranscriptionJob, segments: tuple[TranscriptionSegment, ...]
) -> tuple[TranscriptionCheckpoint, TranscriptionJob]:
    advanced = job.with_progress(1 / 3, at=BASE_TIME + timedelta(seconds=1))
    return (
        TranscriptionCheckpoint(
            job_id=job.id,
            chunk_index=0,
            process_start_ms=0,
            process_end_ms=35_000,
            owned_start_ms=0,
            owned_end_ms=30_000,
            provider_id=DESCRIPTOR.provider_id,
            model_id=DESCRIPTOR.model_id,
            model_source=DESCRIPTOR.source,
            model_revision=DESCRIPTOR.revision,
            requested_language=None,
            segments=segments,
            language="es",
            progress=advanced.progress,
            job_progress=advanced.progress,
            completed_at=advanced.updated_at,
        ),
        advanced,
    )


def test_checkpoint_round_trips_word_timestamps(tmp_path: Path) -> None:
    job, engine = _seed_job((tmp_path / "voz.db").absolute())
    checkpoints = SqliteTranscriptionCheckpointStore(engine)
    segments = (
        TranscriptionSegment(
            0,
            1_000,
            " hola mundo",
            words=(
                TranscriptionWord(0, 400, " hola", 0.75),
                TranscriptionWord(400, 1_000, " mundo"),
            ),
        ),
        TranscriptionSegment(1_000, 2_000, " sin palabras"),
    )
    checkpoint, advanced = _checkpoint_with(job, segments)

    checkpoints.commit(checkpoint, advanced)

    assert checkpoints.list_for_job(job.id) == (checkpoint,)
    engine.dispose()


def test_checkpoints_written_before_word_timestamps_still_load(tmp_path: Path) -> None:
    job, engine = _seed_job((tmp_path / "voz.db").absolute())
    checkpoints = SqliteTranscriptionCheckpointStore(engine)
    checkpoint, advanced = _checkpoint_with(
        job, (TranscriptionSegment(0, 1_000, " viejo"),)
    )
    checkpoints.commit(checkpoint, advanced)
    with engine.begin() as connection:  # the pre-words payload shape, verbatim
        connection.execute(
            text("UPDATE transcription_checkpoints SET segments_json = :json"),
            {"json": '[{"start_ms":0,"end_ms":1000,"text":" viejo"}]'},
        )

    (loaded,) = checkpoints.list_for_job(job.id)

    assert loaded.segments == (TranscriptionSegment(0, 1_000, " viejo"),)
    assert loaded.segments[0].words == ()
    engine.dispose()


class _PositionProvider(_Provider):
    """Reports positions inside the chunk and records what the database held."""

    def __init__(self, jobs: SqliteTranscriptionJobRepository, job_id: object) -> None:
        super().__init__()
        self.jobs = jobs
        self.job_id = job_id
        self.saved: list[tuple[float | None, float]] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        data = audio.read()
        start_ms, end_ms = (int(value) for value in data.decode().split(":"))
        assert options.on_position is not None
        for local_ms in ((end_ms - start_ms) // 2, end_ms - start_ms):
            options.on_position(local_ms)
            stored = self.jobs.get(self.job_id)  # type: ignore[arg-type]
            assert stored is not None
            self.saved.append((stored.stage_progress, stored.progress))
        return super().transcribe(
            audio=BytesIO(data), options=options, cancellation=cancellation
        )


def test_progress_inside_a_chunk_is_saved_throttled_and_weighted(
    tmp_path: Path,
) -> None:
    job, engine = _seed_job((tmp_path / "voz.db").absolute())
    jobs = SqliteTranscriptionJobRepository(engine)
    provider = _PositionProvider(jobs, job.id)
    clock = iter(range(10_000))  # monotonic seconds: one tick per query
    now = {"t": 0.0}

    def monotonic() -> float:
        return now["t"]

    coordinator = RecoverableTranscription(
        provider,
        _AudioSource(),
        SqliteTranscriptionCheckpointStore(engine),
        jobs,
        clock=lambda: BASE_TIME + timedelta(seconds=next(clock)),
        monotonic=monotonic,
        min_save_interval_s=0.5,
    )

    outcome = coordinator.execute(
        job=job,
        duration_ms=65_000,
        options=TranscriptionOptions(model=DESCRIPTOR),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
        progress_range=(0.1, 0.9),
    )

    # Time never advances: only the first report of the whole run is written
    # (the 2nd..Nth are within 0.5 s); chunk ends are always written atomically.
    assert provider.saved[0][0] == pytest.approx(0.5 / 3)
    assert provider.saved[0][1] == pytest.approx(0.1 + 0.8 * provider.saved[0][0])  # type: ignore[operator]
    assert provider.saved[1][0] == provider.saved[0][0]  # throttled, unchanged
    assert outcome.job.stage_progress == 1.0
    assert outcome.job.progress == pytest.approx(0.9)
    final = jobs.get(job.id)
    assert final is not None and final.progress == pytest.approx(0.9)
    checkpoints = SqliteTranscriptionCheckpointStore(engine).list_for_job(job.id)
    assert [c.job_progress for c in checkpoints] == sorted(
        c.job_progress for c in checkpoints
    )
    assert checkpoints[-1].job_progress == pytest.approx(0.9)
    engine.dispose()


def test_progress_inside_a_chunk_writes_again_after_the_interval(
    tmp_path: Path,
) -> None:
    job, engine = _seed_job((tmp_path / "voz.db").absolute())
    jobs = SqliteTranscriptionJobRepository(engine)
    provider = _PositionProvider(jobs, job.id)
    ticks = iter(float(i) for i in range(1_000))  # one second per throttle check
    clock = iter(range(10_000))

    RecoverableTranscription(
        provider,
        _AudioSource(),
        SqliteTranscriptionCheckpointStore(engine),
        jobs,
        clock=lambda: BASE_TIME + timedelta(seconds=next(clock)),
        monotonic=lambda: next(ticks),
    ).execute(
        job=job,
        duration_ms=65_000,
        options=TranscriptionOptions(model=DESCRIPTOR),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    stages = [stage for stage, _ in provider.saved]
    assert stages[0] != stages[1]  # the second report was far enough to be written
    engine.dispose()


def test_resume_accepts_a_job_ahead_of_its_last_checkpoint(tmp_path: Path) -> None:
    job, engine = _seed_job((tmp_path / "voz.db").absolute())
    jobs = SqliteTranscriptionJobRepository(engine)
    provider = _Provider()
    checkpoints = SqliteTranscriptionCheckpointStore(engine)
    clock = lambda: BASE_TIME + timedelta(seconds=1)  # noqa: E731
    coordinator = RecoverableTranscription(
        provider, _AudioSource(), checkpoints, jobs, clock=clock
    )
    options = TranscriptionOptions(model=DESCRIPTOR)
    with pytest.raises(SimulatedCrash):
        coordinator.execute(
            job=job,
            duration_ms=65_000,
            options=options,
            chunk_duration_ms=30_000,
            overlap_ms=5_000,
            on_progress=lambda progress: (_ for _ in ()).throw(SimulatedCrash),
        )
    stored = jobs.get(job.id)
    assert stored is not None
    # A mid-chunk save of the next chunk left the job ahead of the checkpoint.
    ahead = stored.with_stage_progress(
        0.5, progress=stored.progress + 0.1, at=BASE_TIME + timedelta(seconds=2)
    )
    jobs.save(ahead)

    outcome = RecoverableTranscription(
        _Provider(), _AudioSource(), checkpoints, jobs, clock=clock
    ).execute(
        job=ahead,
        duration_ms=65_000,
        options=options,
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    assert outcome.job.progress == 1.0
    assert outcome.completed_chunks == 3
    engine.dispose()
