"""Read-side rules of a transcription job: remaining time, transcript, preview."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from voz.application.job_runner import transcript_id_for
from voz.application.job_status import (
    PreviewSegment,
    eta_seconds,
    job_has_transcript,
    preview_segments,
)
from voz.application.ports.transcription import TranscriptionSegment
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)

T0 = datetime(2026, 10, 3, 12, tzinfo=UTC)


_PIPELINE = (
    TranscriptionJobState.PROBING,
    TranscriptionJobState.PREPROCESSING,
    TranscriptionJobState.TRANSCRIBING,
    TranscriptionJobState.ALIGNING,
    TranscriptionJobState.DIARIZING,
    TranscriptionJobState.MERGING,
    TranscriptionJobState.PERSISTING,
    TranscriptionJobState.COMPLETED,
)


def _job_at(last: TranscriptionJobState) -> TranscriptionJob:
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=uuid4(), media_asset_id=uuid4(), now=T0
    )
    if last is TranscriptionJobState.QUEUED:
        return job
    for step, target in enumerate(_PIPELINE, start=1):
        job = job.transition_to(target, at=T0 + timedelta(seconds=step))
        if target is last:
            break
    return job


def _job(progress: float | None) -> TranscriptionJob:
    job = _job_at(TranscriptionJobState.DIARIZING)
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


class _Transcripts:
    def __init__(self, *known: UUID) -> None:
        self.known = set(known)
        self.lookups = 0

    def get(self, transcript_id: UUID) -> Transcript | None:
        self.lookups += 1
        if transcript_id not in self.known:
            return None
        return Transcript(uuid4(), uuid4(), id=transcript_id, created_at=T0)


@pytest.mark.parametrize(
    "state",
    [
        TranscriptionJobState.QUEUED,
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
    ],
)
def test_no_transcript_before_the_end_of_transcription(
    state: TranscriptionJobState,
) -> None:
    job = _job_at(state)
    lookup = _Transcripts(transcript_id_for(job.id))

    # The state alone decides: the store is not even asked.
    assert not job_has_transcript(job, lookup)
    assert lookup.lookups == 0


def test_a_completed_job_has_its_transcript_without_asking_the_store() -> None:
    lookup = _Transcripts()

    assert job_has_transcript(_job_at(TranscriptionJobState.COMPLETED), lookup)
    assert lookup.lookups == 0


@pytest.mark.parametrize(
    "state", [TranscriptionJobState.ALIGNING, TranscriptionJobState.DIARIZING]
)
def test_later_stages_have_a_transcript_once_its_row_exists(
    state: TranscriptionJobState,
) -> None:
    job = _job_at(state)

    assert not job_has_transcript(job, _Transcripts())
    assert job_has_transcript(job, _Transcripts(transcript_id_for(job.id)))


def _checkpoint(
    owned_start_ms: int, owned_end_ms: int, *texts: tuple[int, int, str]
) -> TranscriptionCheckpoint:
    return TranscriptionCheckpoint(
        job_id=uuid4(),
        chunk_index=0,
        process_start_ms=owned_start_ms,
        process_end_ms=owned_end_ms,
        owned_start_ms=owned_start_ms,
        owned_end_ms=owned_end_ms,
        provider_id="fake",
        model_id="fake",
        model_source=None,
        model_revision=None,
        requested_language=None,
        segments=tuple(TranscriptionSegment(*item) for item in texts),
        language=None,
        progress=0.5,
        job_progress=0.5,
        completed_at=T0,
    )


def test_preview_lists_confirmed_segments_with_trimmed_text() -> None:
    chunks = [_checkpoint(0, 1000, (0, 400, " hola "), (400, 900, "mundo"))]

    assert preview_segments(chunks, 0) == (
        PreviewSegment(0, 400, "hola"),
        PreviewSegment(400, 900, "mundo"),
    )


def test_preview_only_returns_what_ends_after_the_cursor() -> None:
    chunks = [
        _checkpoint(0, 1000, (0, 400, "uno"), (400, 900, "dos")),
        _checkpoint(1000, 2000, (1000, 1500, "tres")),
    ]

    assert preview_segments(chunks, 400) == (
        PreviewSegment(400, 900, "dos"),
        PreviewSegment(1000, 1500, "tres"),
    )
    assert preview_segments(chunks, 1500) == ()
    # A chunk wholly behind the cursor contributes nothing.
    assert preview_segments(chunks[:1], 1000) == ()


def test_preview_skips_blank_text_and_handles_no_checkpoints() -> None:
    assert preview_segments([_checkpoint(0, 500, (0, 500, "  "))], 0) == ()
    assert preview_segments([], 0) == ()
