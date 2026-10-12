"""Cancel, history and delete use cases over in-memory ports."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from synthesis_support import NOW, MemoryAudio, MemoryJobs, MemoryStorage

from voz.application.synthesis import (
    CancelSynthesisJob,
    CreateSynthesisJob,
    DeleteSynthesisResult,
    ListSynthesisHistory,
    SynthesisJobError,
    SynthesisJobFailureCode,
)
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.infrastructure.tts.fake import FAKE_TTS_PROVIDER_ID

BASE: dict[str, Any] = {
    "provider_id": FAKE_TTS_PROVIDER_ID,
    "model_id": "tone",
    "voice_id": "tone-low",
}


def _new(create: CreateSynthesisJob, text: str = "Hello.") -> SynthesisJob:
    return create.execute(text=text, **BASE).job


def _advance(jobs: MemoryJobs, job: SynthesisJob, *states: SynthesisJobState) -> None:
    for state in states:
        if state is SynthesisJobState.PERSISTING:
            job = job.with_chunks_done(job.chunks_total, at=job.updated_at)
        if state is SynthesisJobState.FAILED:
            job = job.transition_to(state, at=job.updated_at, error_code="boom")
        else:
            job = job.transition_to(state, at=job.updated_at)
    jobs.save(job)


def _stored(job: SynthesisJob) -> SynthesizedAudio:
    return SynthesizedAudio(
        job_id=job.id,
        relative_path=f"{job.id}/audio.wav",
        duration_ms=1000,
        sample_rate=16_000,
        chunk_count=job.chunks_total,
        sha256="b" * 64,
        size_bytes=44,
    )


def _complete(jobs: MemoryJobs, audio: MemoryAudio, job: SynthesisJob) -> None:
    _advance(
        jobs,
        job,
        SynthesisJobState.RUNNING,
        SynthesisJobState.PERSISTING,
        SynthesisJobState.COMPLETED,
    )
    audio.add(_stored(job))


# -- cancel -------------------------------------------------------------------


def test_cancel_queued_job_is_immediately_cancelled(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    signalled: list[UUID] = []
    job = _new(create)

    result = CancelSynthesisJob(jobs, interrupt=signalled.append).execute(job.id)

    assert result.state is SynthesisJobState.CANCELLED
    assert jobs.get(job.id) == result
    assert signalled == []


def test_cancel_running_job_goes_cancelling_and_signals_runner(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    signalled: list[UUID] = []
    job = _new(create)
    _advance(jobs, job, SynthesisJobState.RUNNING)
    cancel = CancelSynthesisJob(jobs, interrupt=signalled.append)

    first = cancel.execute(job.id)
    second = cancel.execute(job.id)  # idempotent

    assert first.state is SynthesisJobState.CANCELLING
    assert second == first
    assert signalled == [job.id, job.id]


def test_cancel_uses_a_clock_not_before_the_last_update(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    job = _new(create)

    result = CancelSynthesisJob(jobs, clock=lambda: NOW - timedelta(days=1)).execute(
        job.id
    )

    assert result.updated_at >= job.updated_at


def test_cancel_finished_job_is_refused(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    job = _new(create)
    _advance(jobs, job, SynthesisJobState.RUNNING, SynthesisJobState.FAILED)

    with pytest.raises(SynthesisJobError) as caught:
        CancelSynthesisJob(jobs).execute(job.id)

    assert caught.value.code is SynthesisJobFailureCode.JOB_TERMINAL


def test_cancel_missing_job(jobs: MemoryJobs) -> None:
    with pytest.raises(SynthesisJobError) as caught:
        CancelSynthesisJob(jobs).execute(uuid4())

    assert caught.value.code is SynthesisJobFailureCode.JOB_NOT_FOUND


# -- history ------------------------------------------------------------------


def test_history_newest_first_with_limit_and_audio_only_when_completed(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    done = _new(create, "One.")
    _complete(jobs, audio, done)
    queued = _new(create, "Two.")
    history = ListSynthesisHistory(jobs, audio)

    items = history.execute()

    assert [item.job.id for item in items] == [queued.id, done.id]
    assert items[0].audio is None
    assert items[1].audio == _stored(done)
    assert [item.job.id for item in history.execute(limit=1)] == [queued.id]
    assert len(history.execute(limit=0)) == 1  # clamped, not an error
    assert len(history.execute(limit=10**6)) == 2


# -- delete -------------------------------------------------------------------


def test_delete_completed_removes_job_audio_row_and_file(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    storage = MemoryStorage()
    job = _new(create)
    _complete(jobs, audio, job)

    DeleteSynthesisResult(jobs, audio, storage).execute(job.id)

    assert jobs.items == {} and audio.items == {}
    assert storage.deleted == [f"{job.id}/audio.wav"]


def test_delete_failed_job_without_audio_touches_no_file(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    storage = MemoryStorage()
    job = _new(create)
    _advance(jobs, job, SynthesisJobState.RUNNING, SynthesisJobState.FAILED)

    DeleteSynthesisResult(jobs, audio, storage).execute(job.id)

    assert jobs.items == {}
    assert storage.deleted == []


@pytest.mark.parametrize("started", [False, True])
def test_delete_refuses_active_job(
    create: CreateSynthesisJob,
    jobs: MemoryJobs,
    audio: MemoryAudio,
    started: bool,
) -> None:
    job = _new(create)
    if started:
        _advance(jobs, job, SynthesisJobState.RUNNING, SynthesisJobState.CANCELLING)

    with pytest.raises(SynthesisJobError) as caught:
        DeleteSynthesisResult(jobs, audio, MemoryStorage()).execute(job.id)

    assert caught.value.code is SynthesisJobFailureCode.JOB_ACTIVE
    assert job.id in jobs.items


def test_delete_missing_job(jobs: MemoryJobs, audio: MemoryAudio) -> None:
    with pytest.raises(SynthesisJobError) as caught:
        DeleteSynthesisResult(jobs, audio, MemoryStorage()).execute(uuid4())

    assert caught.value.code is SynthesisJobFailureCode.JOB_NOT_FOUND


def test_failed_file_delete_keeps_the_record_so_it_can_be_retried(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    class Broken(MemoryStorage):
        def delete(self, relative_path: str) -> None:
            raise OSError("disk")

    job = _new(create)
    _complete(jobs, audio, job)

    with pytest.raises(OSError):
        DeleteSynthesisResult(jobs, audio, Broken()).execute(job.id)

    assert job.id in jobs.items and job.id in audio.items
    DeleteSynthesisResult(jobs, audio, MemoryStorage()).execute(job.id)
    assert jobs.items == {}


def test_deleted_result_is_no_longer_reused(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    job = _new(create)
    _complete(jobs, audio, job)
    assert create.execute(text="Hello.", **BASE).reused

    DeleteSynthesisResult(jobs, audio, MemoryStorage(), create.admission).execute(
        job.id
    )

    fresh = create.execute(text="Hello.", **BASE)
    assert not fresh.reused and fresh.job.id != job.id
