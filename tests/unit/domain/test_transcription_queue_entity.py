"""A queue has no state of its own: it is read off the jobs it groups."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from voz.domain.entities.transcription_job import TranscriptionJobState as S
from voz.domain.entities.transcription_queue import (
    QueueItemStatus,
    QueueState,
    SkippedRecording,
    SkipReason,
    TranscriptionQueue,
    queue_item_status,
    queue_state,
)

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)


def test_item_status_maps_every_job_state() -> None:
    expected = {
        S.QUEUED: QueueItemStatus.PENDING,
        S.PROBING: QueueItemStatus.RUNNING,
        S.PREPROCESSING: QueueItemStatus.RUNNING,
        S.TRANSCRIBING: QueueItemStatus.RUNNING,
        S.ALIGNING: QueueItemStatus.RUNNING,
        S.DIARIZING: QueueItemStatus.RUNNING,
        S.MERGING: QueueItemStatus.RUNNING,
        S.PERSISTING: QueueItemStatus.RUNNING,
        S.CANCELLING: QueueItemStatus.RUNNING,
        S.COMPLETED: QueueItemStatus.DONE,
        S.FAILED: QueueItemStatus.ERROR,
        S.CANCELLED: QueueItemStatus.CANCELLED,
    }

    assert set(expected) == set(S)
    assert {state: queue_item_status(state) for state in S} == expected


@pytest.mark.parametrize(
    ("statuses", "state"),
    [
        ((), QueueState.FINISHED),
        ((QueueItemStatus.DONE, QueueItemStatus.ERROR), QueueState.FINISHED),
        ((QueueItemStatus.CANCELLED,), QueueState.FINISHED),
        ((QueueItemStatus.DONE, QueueItemStatus.PENDING), QueueState.RUNNING),
        ((QueueItemStatus.RUNNING, QueueItemStatus.ERROR), QueueState.RUNNING),
    ],
)
def test_queue_runs_while_any_item_is_pending_or_running(
    statuses: tuple[QueueItemStatus, ...], state: QueueState
) -> None:
    assert queue_state(statuses) is state


def test_queue_keeps_its_skipped_recordings() -> None:
    skipped = SkippedRecording(uuid4(), SkipReason.JOB_ACTIVE)

    queue = TranscriptionQueue(uuid4(), uuid4(), NOW, (skipped,))

    assert queue.skipped == (skipped,)
    assert TranscriptionQueue(uuid4(), uuid4(), NOW).skipped == ()


def test_queue_rejects_naive_time_and_non_uuid_identity() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TranscriptionQueue(uuid4(), uuid4(), datetime(2026, 11, 11, 12))
    with pytest.raises(TypeError, match="UUID"):
        TranscriptionQueue("not-a-uuid", uuid4(), NOW)  # type: ignore[arg-type]


def test_skip_reasons_are_the_stable_codes() -> None:
    assert [reason.value for reason in SkipReason] == [
        "already_transcribed",
        "job_active",
        "duration_unknown",
    ]
