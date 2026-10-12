"""SQLite adapters for synthesis jobs and stored audio."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.application.synthesis.create_synthesis_job import request_hash
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import SynthesisRequest
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import migrations_directory
from voz.infrastructure.persistence.synthesis import (
    SqliteSynthesisJobRepository,
    SqliteSynthesizedAudioRepository,
)

NOW = datetime(2026, 10, 11, 9, tzinfo=UTC)
REQUEST = SynthesisRequest(
    text="Hola, mundo. ¿Qué tal?\nSegunda línea con ñ y 日本語.",
    provider_id="sherpa-onnx",
    model_id="kitten-nano",
    voice_id="spk-3",
    model_revision="rev-1",
    language="es-CO",
    speed=1.25,
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine(tmp_path / "voz.sqlite3")
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    with created.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield created
    created.dispose()


@pytest.fixture
def jobs(engine: Engine) -> SqliteSynthesisJobRepository:
    return SqliteSynthesisJobRepository(engine)


@pytest.fixture
def audios(engine: Engine) -> SqliteSynthesizedAudioRepository:
    return SqliteSynthesizedAudioRepository(engine)


def _job(
    *, at: datetime = NOW, request: SynthesisRequest = REQUEST, chunks: int = 4
) -> SynthesisJob:
    return SynthesisJob.create(
        job_id=uuid4(), request=request, chunks_total=chunks, now=at
    )


def _audio(job_id: UUID) -> SynthesizedAudio:
    return SynthesizedAudio(
        job_id=job_id,
        relative_path=f"{job_id}/audio.wav",
        duration_ms=4_321,
        sample_rate=24_000,
        chunk_count=4,
        sha256="ab" * 32,
        size_bytes=207_408,
    )


def test_adapters_satisfy_their_ports(engine: Engine) -> None:
    assert isinstance(SqliteSynthesisJobRepository(engine), SynthesisJobRepository)
    assert isinstance(
        SqliteSynthesizedAudioRepository(engine), SynthesizedAudioRepository
    )


def test_job_round_trips_every_field(jobs: SqliteSynthesisJobRepository) -> None:
    job = _job()
    jobs.add(job)

    stored = jobs.get(job.id)

    assert stored == job
    assert stored is not None
    assert stored.request == REQUEST
    assert stored.created_at.utcoffset() == timedelta(0)


def test_job_without_optional_fields_round_trips(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    job = _job(request=SynthesisRequest("Hola", "p", "m", "v"), chunks=1)
    jobs.add(job)

    stored = jobs.get(job.id)

    assert stored == job
    assert stored is not None
    assert stored.request.model_revision is None
    assert stored.request.language is None
    assert stored.started_at is None


def test_timestamps_with_offsets_come_back_as_the_same_instant(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    bogota = NOW.astimezone(timezone(timedelta(hours=-5)))
    job = SynthesisJob.create(
        job_id=uuid4(), request=REQUEST, chunks_total=1, now=bogota
    )
    jobs.add(job)

    stored = jobs.get(job.id)

    assert stored is not None
    assert stored.created_at == bogota
    assert stored.created_at.tzinfo is not None


def test_saved_transitions_progress_and_failure_are_persisted(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    job = _job()
    jobs.add(job)

    job = job.transition_to(
        SynthesisJobState.RUNNING, at=NOW + timedelta(seconds=1)
    ).with_chunks_done(2, at=NOW + timedelta(seconds=2))
    jobs.save(job)
    assert jobs.get(job.id) == job
    stored = jobs.get(job.id)
    assert stored is not None
    assert stored.started_at == NOW + timedelta(seconds=1)
    assert (stored.state, stored.chunks_done) == (SynthesisJobState.RUNNING, 2)

    failed = job.transition_to(
        SynthesisJobState.FAILED,
        at=NOW + timedelta(seconds=3),
        error_code="synthesis_failed",
    )
    jobs.save(failed)
    assert jobs.get(job.id) == failed
    assert failed.error_code == "synthesis_failed"


def test_full_happy_path_is_persisted_step_by_step(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    def at(seconds: int) -> datetime:
        return NOW + timedelta(seconds=seconds)

    job = _job(chunks=2)
    jobs.add(job)
    running = job.transition_to(SynthesisJobState.RUNNING, at=at(1))
    job = running.with_chunks_done(2, at=at(2))
    for snapshot in (running, job):
        jobs.save(snapshot)
        assert jobs.get(snapshot.id) == snapshot
    for state in (SynthesisJobState.PERSISTING, SynthesisJobState.COMPLETED):
        job = job.transition_to(state, at=at(3))
        jobs.save(job)
        assert jobs.get(job.id) == job
    assert job.progress == 1.0


def test_save_of_a_missing_job_fails_and_creates_nothing(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    ghost = _job()

    with pytest.raises(LookupError, match="missing synthesis job"):
        jobs.save(ghost)

    assert jobs.get(ghost.id) is None
    assert jobs.list_recent(10) == ()


def test_adding_the_same_job_twice_is_rejected(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    job = _job()
    jobs.add(job)

    with pytest.raises(IntegrityError):
        jobs.add(job)


def test_get_of_an_unknown_job_is_none(jobs: SqliteSynthesisJobRepository) -> None:
    assert jobs.get(uuid4()) is None


def test_list_recent_is_newest_first_and_honours_the_limit(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    created = [_job(at=NOW + timedelta(minutes=minute)) for minute in (5, 1, 9, 3)]
    for job in created:
        jobs.add(job)

    by_age = sorted(created, key=lambda job: job.created_at, reverse=True)
    assert list(jobs.list_recent(10)) == by_age
    assert list(jobs.list_recent(2)) == by_age[:2]


@pytest.mark.parametrize("limit", [0, -1])
def test_list_recent_rejects_a_non_positive_limit(
    jobs: SqliteSynthesisJobRepository, limit: int
) -> None:
    with pytest.raises(ValueError, match="positive"):
        jobs.list_recent(limit)


def test_request_hash_is_stored_with_the_job(
    engine: Engine, jobs: SqliteSynthesisJobRepository
) -> None:
    job = _job()
    jobs.add(job)

    with engine.connect() as connection:
        stored = connection.exec_driver_sql(
            "SELECT request_hash FROM synthesis_jobs"
        ).scalar_one()
    assert stored == request_hash(REQUEST)


def test_find_by_hash_returns_the_newest_job_in_the_given_states(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    def at(minutes: int) -> datetime:
        return NOW + timedelta(minutes=minutes)

    def done(created: datetime) -> SynthesisJob:
        return (
            _job(at=created)
            .transition_to(SynthesisJobState.RUNNING, at=created)
            .with_chunks_done(4, at=created)
            .transition_to(SynthesisJobState.PERSISTING, at=created)
            .transition_to(SynthesisJobState.COMPLETED, at=created)
        )

    old, new = done(at(1)), done(at(5))
    queued = _job(at=at(9))
    other = _job(at=at(11), request=SynthesisRequest("Otro texto", "p", "m", "v"))
    for job in (old, new, queued, other):
        jobs.add(job)
    digest = request_hash(REQUEST)

    assert jobs.find_by_hash(digest, [SynthesisJobState.COMPLETED]) == new
    assert jobs.find_by_hash(digest, {SynthesisJobState.QUEUED}) == queued
    assert (
        jobs.find_by_hash(
            digest, (SynthesisJobState.COMPLETED, SynthesisJobState.QUEUED)
        )
        == queued
    )
    assert jobs.find_by_hash(digest, [SynthesisJobState.FAILED]) is None
    assert jobs.find_by_hash(digest, []) is None
    assert (
        jobs.find_by_hash(request_hash(other.request), [SynthesisJobState.QUEUED])
        == other
    )
    assert jobs.find_by_hash("0" * 64, [SynthesisJobState.QUEUED]) is None


def test_find_by_hash_follows_saved_state_and_deleted_jobs(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    job = _job()
    jobs.add(job)
    digest = request_hash(REQUEST)
    running = job.transition_to(
        SynthesisJobState.RUNNING, at=NOW + timedelta(seconds=1)
    )
    jobs.save(running)

    assert jobs.find_by_hash(digest, [SynthesisJobState.QUEUED]) is None
    assert jobs.find_by_hash(digest, [SynthesisJobState.RUNNING]) == running
    jobs.delete(job.id)
    assert jobs.find_by_hash(digest, [SynthesisJobState.RUNNING]) is None


def test_list_recoverable_returns_only_non_terminal_jobs_oldest_first(
    jobs: SqliteSynthesisJobRepository,
) -> None:
    def at(minutes: int) -> datetime:
        return NOW + timedelta(minutes=minutes)

    queued = _job(at=at(3))
    running = _job(at=at(1)).transition_to(SynthesisJobState.RUNNING, at=at(2))
    cancelling = _job(at=at(2)).transition_to(SynthesisJobState.CANCELLING, at=at(4))
    failed = _job().transition_to(SynthesisJobState.FAILED, at=at(1), error_code="x")
    cancelled = (
        _job()
        .transition_to(SynthesisJobState.CANCELLING, at=at(1))
        .transition_to(SynthesisJobState.CANCELLED, at=at(2))
    )
    completed = (
        _job(chunks=1)
        .transition_to(SynthesisJobState.RUNNING, at=at(1))
        .with_chunks_done(1, at=at(2))
        .transition_to(SynthesisJobState.PERSISTING, at=at(3))
        .transition_to(SynthesisJobState.COMPLETED, at=at(4))
    )
    for job in (queued, running, cancelling, failed, cancelled, completed):
        jobs.add(job)

    assert list(jobs.list_recoverable()) == [running, cancelling, queued]


def test_audio_round_trips_and_is_absent_for_a_job_without_one(
    jobs: SqliteSynthesisJobRepository, audios: SqliteSynthesizedAudioRepository
) -> None:
    job = _job()
    jobs.add(job)
    assert audios.get_by_job(job.id) is None

    audio = _audio(job.id)
    audios.add(audio)

    assert audios.get_by_job(job.id) == audio


def test_a_job_has_at_most_one_audio_and_audio_needs_its_job(
    jobs: SqliteSynthesisJobRepository, audios: SqliteSynthesizedAudioRepository
) -> None:
    job = _job()
    jobs.add(job)
    audios.add(_audio(job.id))

    with pytest.raises(IntegrityError):
        audios.add(_audio(job.id))
    with pytest.raises(IntegrityError):
        audios.add(_audio(uuid4()))


def test_deleting_the_audio_keeps_the_job(
    jobs: SqliteSynthesisJobRepository, audios: SqliteSynthesizedAudioRepository
) -> None:
    job = _job()
    jobs.add(job)
    audios.add(_audio(job.id))

    audios.delete(job.id)
    audios.delete(job.id)  # idempotent

    assert audios.get_by_job(job.id) is None
    assert jobs.get(job.id) == job


def test_deleting_the_job_cascades_to_its_audio_only(
    jobs: SqliteSynthesisJobRepository, audios: SqliteSynthesizedAudioRepository
) -> None:
    gone, kept = _job(), _job()
    for job in (gone, kept):
        jobs.add(job)
        audios.add(_audio(job.id))

    assert jobs.delete(gone.id) is True
    assert jobs.delete(gone.id) is False

    assert jobs.get(gone.id) is None
    assert audios.get_by_job(gone.id) is None
    assert audios.get_by_job(kept.id) == _audio(kept.id)
    assert jobs.get(kept.id) == kept


@pytest.mark.parametrize(
    ("assignment", "error"),
    [
        ("id = 'not-a-uuid'", ValueError),
        ("state = 'EXPLODED'", ValueError),
        ("output_format = 'mp3'", ValueError),
        ("created_at = 'yesterday'", ValueError),
        ("created_at = '2026-10-11T09:00:00'", ValueError),  # naive timestamp
        ("chunks_done = 1.5", TypeError),
        ("speed = 'fast'", TypeError),
        ("speed = 9.0", ValueError),
        ("text = '   '", ValueError),
        ("voice_id = ''", ValueError),
        ("error_code = 'oops'", ValueError),  # only a FAILED job may carry one
        ("updated_at = '2000-01-01T00:00:00+00:00'", ValueError),
        ("provider_id = NULL", IntegrityError),
    ],
)
def test_corrupt_job_rows_are_rejected_on_read(
    engine: Engine,
    jobs: SqliteSynthesisJobRepository,
    assignment: str,
    error: type[Exception],
) -> None:
    job = _job()
    jobs.add(job)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"UPDATE synthesis_jobs SET {assignment}")
    except IntegrityError:  # NOT NULL / CHECK stop it before it is ever stored
        assert error is IntegrityError
        return

    with pytest.raises(error):
        jobs.list_recent(10)
    with pytest.raises(error):
        jobs.list_recoverable()


@pytest.mark.parametrize(
    "assignment",
    [
        "relative_path = '/etc/passwd'",
        "relative_path = '../escape.wav'",
        "relative_path = 'C:\\x.wav'",
        "sha256 = 'XYZ'",
        "sample_rate = 'high'",
    ],
)
def test_corrupt_audio_rows_are_rejected_on_read(
    engine: Engine,
    jobs: SqliteSynthesisJobRepository,
    audios: SqliteSynthesizedAudioRepository,
    assignment: str,
) -> None:
    job = _job()
    jobs.add(job)
    audios.add(_audio(job.id))
    with engine.begin() as connection:
        connection.exec_driver_sql(f"UPDATE synthesized_audio SET {assignment}")

    with pytest.raises((ValueError, TypeError)):
        audios.get_by_job(job.id)
