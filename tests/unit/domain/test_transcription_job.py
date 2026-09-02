from datetime import UTC, datetime, timedelta, timezone
from math import inf, nan
from uuid import UUID

import pytest

from voz.domain.entities.transcription_job import (
    InvalidJobTransition,
    TranscriptionJob,
    TranscriptionJobState,
)

JOB_ID = UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000002")
MEDIA_ASSET_ID = UUID("00000000-0000-0000-0000-000000000003")
STARTED_AT = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)

PIPELINE = (
    TranscriptionJobState.QUEUED,
    TranscriptionJobState.PROBING,
    TranscriptionJobState.PREPROCESSING,
    TranscriptionJobState.TRANSCRIBING,
    TranscriptionJobState.ALIGNING,
    TranscriptionJobState.DIARIZING,
    TranscriptionJobState.MERGING,
    TranscriptionJobState.PERSISTING,
    TranscriptionJobState.COMPLETED,
)
PROCESSABLE_STATES = PIPELINE[:-1]


def make_job(
    *,
    state: TranscriptionJobState = TranscriptionJobState.QUEUED,
    progress: float = 0.0,
    error_code: str | None = None,
) -> TranscriptionJob:
    if state is TranscriptionJobState.COMPLETED:
        progress = 1.0
    return TranscriptionJob(
        id=JOB_ID,
        project_id=PROJECT_ID,
        media_asset_id=MEDIA_ASSET_ID,
        state=state,
        progress=progress,
        created_at=STARTED_AT,
        updated_at=STARTED_AT,
        error_code=error_code,
    )


def test_create_builds_a_queued_job_with_aware_timestamps() -> None:
    job = TranscriptionJob.create(
        job_id=JOB_ID,
        project_id=PROJECT_ID,
        media_asset_id=MEDIA_ASSET_ID,
        now=STARTED_AT,
    )

    assert job.state is TranscriptionJobState.QUEUED
    assert job.progress == 0.0
    assert job.created_at == STARTED_AT
    assert job.updated_at == STARTED_AT
    assert job.error_code is None


@pytest.mark.parametrize("field_name", ["id", "project_id", "media_asset_id"])
def test_rejects_non_uuid_identities(field_name: str) -> None:
    values: dict[str, object] = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "media_asset_id": MEDIA_ASSET_ID,
        "state": TranscriptionJobState.QUEUED,
        "progress": 0.0,
        "created_at": STARTED_AT,
        "updated_at": STARTED_AT,
    }
    values[field_name] = "not-a-uuid"

    with pytest.raises(TypeError, match=f"{field_name} must be a UUID"):
        TranscriptionJob(**values)  # type: ignore[arg-type]


def test_rejects_non_enum_state_on_construction_and_transition() -> None:
    values: dict[str, object] = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "media_asset_id": MEDIA_ASSET_ID,
        "state": "QUEUED",
        "progress": 0.0,
        "created_at": STARTED_AT,
        "updated_at": STARTED_AT,
    }

    with pytest.raises(TypeError, match="state must be a TranscriptionJobState"):
        TranscriptionJob(**values)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="target must be a TranscriptionJobState"):
        make_job().transition_to("PROBING", at=STARTED_AT)


def test_pipeline_accepts_each_successor_and_completes_at_full_progress() -> None:
    job = make_job()

    for step, expected_state in enumerate(PIPELINE[1:], start=1):
        changed_at = STARTED_AT + timedelta(seconds=step)
        job = job.transition_to(expected_state, at=changed_at)
        assert job.state is expected_state
        assert job.updated_at == changed_at

    assert job.progress == 1.0
    assert job.state.is_terminal


@pytest.mark.parametrize("state", PROCESSABLE_STATES)
def test_every_processable_state_can_fail(state: TranscriptionJobState) -> None:
    job = make_job(state=state, progress=0.25)

    failed = job.transition_to(
        TranscriptionJobState.FAILED,
        at=STARTED_AT + timedelta(seconds=1),
        error_code="ASR_PROVIDER_ERROR",
    )

    assert failed.state is TranscriptionJobState.FAILED
    assert failed.error_code == "ASR_PROVIDER_ERROR"
    assert failed.progress == 0.25


@pytest.mark.parametrize("state", PROCESSABLE_STATES)
def test_every_processable_state_can_be_cancelled(
    state: TranscriptionJobState,
) -> None:
    job = make_job(state=state, progress=0.25)

    cancelling = job.transition_to(
        TranscriptionJobState.CANCELLING,
        at=STARTED_AT + timedelta(seconds=1),
    )
    cancelled = cancelling.transition_to(
        TranscriptionJobState.CANCELLED,
        at=STARTED_AT + timedelta(seconds=2),
    )

    assert cancelling.state is TranscriptionJobState.CANCELLING
    assert cancelled.state is TranscriptionJobState.CANCELLED
    assert cancelled.progress == 0.25


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TranscriptionJobState.QUEUED, TranscriptionJobState.TRANSCRIBING),
        (TranscriptionJobState.TRANSCRIBING, TranscriptionJobState.PROBING),
        (TranscriptionJobState.PROBING, TranscriptionJobState.PROBING),
        (TranscriptionJobState.CANCELLING, TranscriptionJobState.FAILED),
        (TranscriptionJobState.CANCELLING, TranscriptionJobState.COMPLETED),
    ],
)
def test_rejects_skipped_reversed_repeated_and_unplanned_transitions(
    source: TranscriptionJobState,
    target: TranscriptionJobState,
) -> None:
    with pytest.raises(InvalidJobTransition, match=source.value):
        make_job(state=source).transition_to(target, at=STARTED_AT)


@pytest.mark.parametrize(
    "terminal_state",
    [
        TranscriptionJobState.COMPLETED,
        TranscriptionJobState.FAILED,
        TranscriptionJobState.CANCELLED,
    ],
)
@pytest.mark.parametrize("target", list(TranscriptionJobState))
def test_terminal_states_never_advance(
    terminal_state: TranscriptionJobState,
    target: TranscriptionJobState,
) -> None:
    job = make_job(
        state=terminal_state,
        error_code="ASR_PROVIDER_ERROR"
        if terminal_state is TranscriptionJobState.FAILED
        else None,
    )

    assert not job.can_transition_to(target)
    with pytest.raises(InvalidJobTransition):
        job.transition_to(target, at=STARTED_AT)


@pytest.mark.parametrize("progress", [-0.01, 1.01, inf, -inf, nan])
def test_rejects_progress_outside_the_finite_closed_interval(
    progress: float,
) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        make_job(progress=progress)


@pytest.mark.parametrize("progress", [True, False, "0.5", None])
def test_rejects_non_numeric_progress(progress: object) -> None:
    values: dict[str, object] = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "media_asset_id": MEDIA_ASSET_ID,
        "state": TranscriptionJobState.QUEUED,
        "progress": progress,
        "created_at": STARTED_AT,
        "updated_at": STARTED_AT,
    }

    with pytest.raises(TypeError, match="progress must be a real number"):
        TranscriptionJob(**values)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="progress must be a real number"):
        make_job().with_progress(progress, at=STARTED_AT)


def test_progress_is_monotonic_and_preserves_original_snapshot() -> None:
    job = make_job(progress=0.25)
    changed_at = STARTED_AT + timedelta(seconds=1)

    updated = job.with_progress(0.75, at=changed_at)

    assert updated.progress == 0.75
    assert updated.updated_at == changed_at
    assert job.progress == 0.25
    with pytest.raises(ValueError, match="cannot decrease"):
        updated.with_progress(0.5, at=changed_at)


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_rejects_naive_persisted_timestamps(field_name: str) -> None:
    values: dict[str, object] = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "media_asset_id": MEDIA_ASSET_ID,
        "state": TranscriptionJobState.QUEUED,
        "progress": 0.0,
        "created_at": STARTED_AT,
        "updated_at": STARTED_AT,
    }
    values[field_name] = datetime(2026, 9, 2, 8, 0)

    with pytest.raises(ValueError, match=f"{field_name} must be timezone-aware"):
        TranscriptionJob(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_rejects_non_datetime_timestamps(field_name: str) -> None:
    values: dict[str, object] = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "media_asset_id": MEDIA_ASSET_ID,
        "state": TranscriptionJobState.QUEUED,
        "progress": 0.0,
        "created_at": STARTED_AT,
        "updated_at": STARTED_AT,
    }
    values[field_name] = "2026-09-02T08:00:00Z"

    with pytest.raises(TypeError, match=f"{field_name} must be a datetime"):
        TranscriptionJob(**values)  # type: ignore[arg-type]


def test_preserves_aware_timestamp_offsets() -> None:
    bogota = timezone(timedelta(hours=-5))
    local_time = datetime(2026, 9, 2, 8, 0, tzinfo=bogota)

    job = TranscriptionJob.create(
        job_id=JOB_ID,
        project_id=PROJECT_ID,
        media_asset_id=MEDIA_ASSET_ID,
        now=local_time,
    )

    assert job.created_at is local_time
    assert job.updated_at is local_time


def test_rejects_timestamps_that_move_backwards() -> None:
    job = make_job()

    with pytest.raises(ValueError, match="earlier than updated_at"):
        job.transition_to(
            TranscriptionJobState.PROBING,
            at=STARTED_AT - timedelta(microseconds=1),
        )


def test_rejects_persisted_updated_at_before_created_at() -> None:
    with pytest.raises(ValueError, match="earlier than created_at"):
        TranscriptionJob(
            id=JOB_ID,
            project_id=PROJECT_ID,
            media_asset_id=MEDIA_ASSET_ID,
            state=TranscriptionJobState.QUEUED,
            progress=0.0,
            created_at=STARTED_AT,
            updated_at=STARTED_AT - timedelta(microseconds=1),
        )


@pytest.mark.parametrize("error_code", ["", " ", " PADDED", "PADDED "])
def test_rejects_invalid_error_codes(error_code: str) -> None:
    with pytest.raises(ValueError, match="non-empty trimmed"):
        make_job(state=TranscriptionJobState.FAILED, error_code=error_code)


def test_rejects_non_string_error_code() -> None:
    with pytest.raises(TypeError, match="error_code must be a string"):
        make_job(
            state=TranscriptionJobState.FAILED,
            error_code=123,  # type: ignore[arg-type]
        )


def test_error_code_is_only_valid_for_failure() -> None:
    with pytest.raises(ValueError, match="only valid for a failed job"):
        make_job(error_code="ASR_PROVIDER_ERROR")

    with pytest.raises(ValueError, match="only accompany"):
        make_job().transition_to(
            TranscriptionJobState.PROBING,
            at=STARTED_AT,
            error_code="ASR_PROVIDER_ERROR",
        )
