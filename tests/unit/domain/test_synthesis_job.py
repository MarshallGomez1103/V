from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from voz.domain.entities import (
    InvalidJobTransition,
    SynthesisJob,
    SynthesisJobState,
    SynthesisRequest,
)

S = SynthesisJobState
JOB_ID = UUID("00000000-0000-0000-0000-000000000001")
T0 = datetime(2026, 10, 11, 8, 0, tzinfo=UTC)
REQUEST = SynthesisRequest(text="Hola.", provider_id="e", model_id="m", voice_id="0")


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def queued(chunks_total: int = 3) -> SynthesisJob:
    return SynthesisJob.create(
        job_id=JOB_ID, request=REQUEST, chunks_total=chunks_total, now=T0
    )


def running() -> SynthesisJob:
    return queued().transition_to(S.RUNNING, at=at(1))


def test_create_builds_a_queued_job_without_progress() -> None:
    job = queued()

    assert job.state is S.QUEUED
    assert (job.chunks_done, job.chunks_total, job.progress) == (0, 3, 0.0)
    assert job.created_at == job.updated_at == T0
    assert job.started_at is None and job.error_code is None


def test_happy_path_reaches_completed_with_every_chunk() -> None:
    job = running()
    assert job.started_at == at(1)
    for done in (1, 2, 3):
        job = job.with_chunks_done(done, at=at(1 + done))
    job = job.transition_to(S.PERSISTING, at=at(5)).transition_to(S.COMPLETED, at=at(6))

    assert job.state is S.COMPLETED and job.state.is_terminal
    assert job.progress == 1.0
    assert job.started_at == at(1) and job.updated_at == at(6)


def test_cannot_persist_before_every_chunk_is_done() -> None:
    with pytest.raises(ValueError, match="every chunk"):
        running().with_chunks_done(2, at=at(2)).transition_to(S.PERSISTING, at=at(3))


def test_chunk_progress_is_monotonic_and_bounded() -> None:
    job = running().with_chunks_done(2, at=at(2))
    assert job.progress == 2 / 3
    assert job.with_chunks_done(2, at=at(3)).chunks_done == 2
    with pytest.raises(ValueError, match="decrease"):
        job.with_chunks_done(1, at=at(3))
    with pytest.raises(ValueError, match="exceed"):
        job.with_chunks_done(4, at=at(3))
    with pytest.raises(TypeError):
        job.with_chunks_done(True, at=at(3))
    with pytest.raises(ValueError, match="earlier"):
        job.with_chunks_done(3, at=at(1))


@pytest.mark.parametrize("state", [S.QUEUED, S.PERSISTING, S.CANCELLING, S.FAILED])
def test_chunk_progress_only_while_running(state: SynthesisJobState) -> None:
    job = SynthesisJob(
        id=JOB_ID,
        request=REQUEST,
        state=state,
        chunks_done=1,
        chunks_total=1,
        created_at=T0,
        updated_at=T0,
        error_code="synthesis_failed" if state is S.FAILED else None,
    )
    with pytest.raises(ValueError, match="running"):
        job.with_chunks_done(1, at=at(1))


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (S.QUEUED, S.PERSISTING),
        (S.QUEUED, S.COMPLETED),
        (S.QUEUED, S.CANCELLED),
        (S.RUNNING, S.QUEUED),
        (S.RUNNING, S.COMPLETED),
        (S.CANCELLING, S.RUNNING),
        (S.CANCELLING, S.FAILED),
        (S.COMPLETED, S.RUNNING),
        (S.FAILED, S.QUEUED),
        (S.CANCELLED, S.QUEUED),
    ],
)
def test_illegal_transitions_raise_the_domain_error(
    source: SynthesisJobState, target: SynthesisJobState
) -> None:
    job = SynthesisJob(
        id=JOB_ID,
        request=REQUEST,
        state=source,
        chunks_done=1,
        chunks_total=1,
        created_at=T0,
        updated_at=T0,
        error_code="x" if source is S.FAILED else None,
    )
    assert not job.can_transition_to(target)
    with pytest.raises(InvalidJobTransition):
        job.transition_to(target, at=at(1))


@pytest.mark.parametrize("source", [S.QUEUED, S.RUNNING])
def test_cancellation_goes_through_cancelling(source: SynthesisJobState) -> None:
    job = queued() if source is S.QUEUED else running()
    cancelled = job.transition_to(S.CANCELLING, at=at(2)).transition_to(
        S.CANCELLED, at=at(3)
    )

    assert cancelled.state is S.CANCELLED and cancelled.state.is_terminal
    assert cancelled.error_code is None


def test_failure_requires_and_keeps_an_error_code() -> None:
    job = running().with_chunks_done(1, at=at(2))
    with pytest.raises(TypeError):
        job.transition_to(S.FAILED, at=at(3))
    with pytest.raises(ValueError):
        job.transition_to(S.FAILED, at=at(3), error_code=" voice_not_found")
    failed = job.transition_to(S.FAILED, at=at(3), error_code="voice_not_found")

    assert failed.state is S.FAILED and failed.error_code == "voice_not_found"
    assert failed.chunks_done == 1


def test_error_code_only_accompanies_failed() -> None:
    with pytest.raises(ValueError, match="FAILED"):
        queued().transition_to(S.RUNNING, at=at(1), error_code="x")
    with pytest.raises(ValueError, match="failed job"):
        SynthesisJob(
            id=JOB_ID,
            request=REQUEST,
            state=S.RUNNING,
            chunks_done=0,
            chunks_total=1,
            created_at=T0,
            updated_at=T0,
            error_code="x",
        )


def test_transition_rejects_earlier_or_naive_timestamps() -> None:
    job = running()
    with pytest.raises(ValueError, match="earlier"):
        job.transition_to(S.CANCELLING, at=T0)
    with pytest.raises(ValueError, match="timezone"):
        job.transition_to(S.CANCELLING, at=datetime(2026, 10, 11, 9))
    with pytest.raises(TypeError):
        job.transition_to("CANCELLING", at=at(2))


@pytest.mark.parametrize(
    ("done", "total", "error"),
    [(0, 0, ValueError), (-1, 2, ValueError), (3, 2, ValueError), (1.0, 2, TypeError)],
)
def test_chunk_counts_are_validated(done: object, total: object, error: type) -> None:
    with pytest.raises(error):
        SynthesisJob(
            id=JOB_ID,
            request=REQUEST,
            state=S.RUNNING,
            chunks_done=done,  # type: ignore[arg-type]
            chunks_total=total,  # type: ignore[arg-type]
            created_at=T0,
            updated_at=T0,
        )


def test_completed_snapshot_requires_every_chunk() -> None:
    with pytest.raises(ValueError, match="every chunk"):
        SynthesisJob(
            id=JOB_ID,
            request=REQUEST,
            state=S.COMPLETED,
            chunks_done=1,
            chunks_total=2,
            created_at=T0,
            updated_at=T0,
        )


def test_snapshot_rejects_bad_identity_request_and_clock() -> None:
    with pytest.raises(TypeError):
        SynthesisJob.create(job_id="1", request=REQUEST, chunks_total=1, now=T0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SynthesisJob.create(job_id=JOB_ID, request="hola", chunks_total=1, now=T0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="earlier"):
        SynthesisJob(
            id=JOB_ID,
            request=REQUEST,
            state=S.QUEUED,
            chunks_done=0,
            chunks_total=1,
            created_at=at(1),
            updated_at=T0,
        )
