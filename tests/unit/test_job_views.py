"""Stage timing projection shared by the REST job views and the SSE stream."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.interfaces.api.job_views import job_view

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


def test_view_exposes_the_timing_fields_as_iso_strings() -> None:
    job = _job(0.5)
    assert job.stage_started_at is not None
    view = job_view(job, now=job.stage_started_at + timedelta(seconds=10))

    assert view["started_at"] == (T0 + timedelta(seconds=1)).isoformat()
    assert view["stage_started_at"] == (T0 + timedelta(seconds=5)).isoformat()
    assert view["stage_progress"] == 0.5
    assert view["eta_seconds"] == 10.0
