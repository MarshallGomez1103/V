"""Stage timing projection shared by the REST job views and the SSE stream."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.interfaces.api.job_views import eta_seconds, job_view

T0 = datetime(2026, 10, 3, 12, tzinfo=UTC)


def _job(progress: float | None) -> TranscriptionJob:
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=uuid4(), media_asset_id=uuid4(), now=T0
    )
    for step, target in enumerate(
        (
            TranscriptionJobState.PROBING,
            TranscriptionJobState.PREPROCESSING,
            TranscriptionJobState.TRANSCRIBING,
            TranscriptionJobState.ALIGNING,
            TranscriptionJobState.DIARIZING,
        ),
        start=1,
    ):
        job = job.transition_to(target, at=T0 + timedelta(seconds=step))
    if progress is not None:
        job = job.with_stage_progress(progress, progress=0.8, at=job.updated_at)
    return job


def test_eta_extrapolates_the_elapsed_time_of_the_stage() -> None:
    job = _job(0.25)  # the stage began 100 s ago, a quarter is done
    assert job.stage_started_at is not None
    now = job.stage_started_at + timedelta(seconds=100)

    assert eta_seconds(job, now) == 300.0


def test_eta_needs_a_basis() -> None:
    assert eta_seconds(_job(None)) is None  # no measure yet
    assert eta_seconds(_job(0.01)) is None  # too little to extrapolate
    job = _job(0.5)
    assert eta_seconds(job, job.stage_started_at) is None  # no time elapsed


def test_eta_is_zero_when_the_stage_is_full_and_null_when_finished() -> None:
    assert eta_seconds(_job(1.0)) == 0.0
    done = _job(0.5).transition_to(
        TranscriptionJobState.CANCELLING, at=T0 + timedelta(minutes=5)
    )
    assert eta_seconds(done) is None  # not processable any more


def test_view_exposes_the_timing_fields_as_iso_strings() -> None:
    job = _job(0.5)
    assert job.stage_started_at is not None
    view = job_view(job, now=job.stage_started_at + timedelta(seconds=10))

    assert view["started_at"] == (T0 + timedelta(seconds=1)).isoformat()
    assert view["stage_started_at"] == (T0 + timedelta(seconds=5)).isoformat()
    assert view["stage_progress"] == 0.5
    assert view["eta_seconds"] == 10.0
