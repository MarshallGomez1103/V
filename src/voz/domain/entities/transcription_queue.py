"""A project queue groups ordinary transcription jobs; it keeps no state of its own."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from voz.domain.entities._validation import require_aware_datetime, require_uuid
from voz.domain.entities.transcription_job import TranscriptionJobState


class QueueItemStatus(StrEnum):
    """What one item looks like to the person, derived from its job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class QueueState(StrEnum):
    RUNNING = "running"
    FINISHED = "finished"


class SkipReason(StrEnum):
    """Why a recording of the project did not enter the queue."""

    ALREADY_TRANSCRIBED = "already_transcribed"
    JOB_ACTIVE = "job_active"
    DURATION_UNKNOWN = "duration_unknown"


_ITEM_STATUS: Final[dict[TranscriptionJobState, QueueItemStatus]] = {
    TranscriptionJobState.QUEUED: QueueItemStatus.PENDING,
    TranscriptionJobState.PROBING: QueueItemStatus.RUNNING,
    TranscriptionJobState.PREPROCESSING: QueueItemStatus.RUNNING,
    TranscriptionJobState.TRANSCRIBING: QueueItemStatus.RUNNING,
    TranscriptionJobState.ALIGNING: QueueItemStatus.RUNNING,
    TranscriptionJobState.DIARIZING: QueueItemStatus.RUNNING,
    TranscriptionJobState.MERGING: QueueItemStatus.RUNNING,
    TranscriptionJobState.PERSISTING: QueueItemStatus.RUNNING,
    TranscriptionJobState.CANCELLING: QueueItemStatus.RUNNING,
    TranscriptionJobState.COMPLETED: QueueItemStatus.DONE,
    TranscriptionJobState.FAILED: QueueItemStatus.ERROR,
    TranscriptionJobState.CANCELLED: QueueItemStatus.CANCELLED,
}


def queue_item_status(state: TranscriptionJobState) -> QueueItemStatus:
    """``CANCELLING`` is still running: the worker has not stopped yet."""
    return _ITEM_STATUS[state]


def queue_state(statuses: Iterable[QueueItemStatus]) -> QueueState:
    """Running while any item is pending or running, otherwise finished."""
    unfinished = {QueueItemStatus.PENDING, QueueItemStatus.RUNNING}
    return (
        QueueState.RUNNING
        if any(status in unfinished for status in statuses)
        else QueueState.FINISHED
    )


@dataclass(frozen=True, slots=True)
class SkippedRecording:
    media_asset_id: UUID
    reason: SkipReason

    def __post_init__(self) -> None:
        require_uuid(self.media_asset_id, field="media_asset_id")
        if not isinstance(self.reason, SkipReason):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("reason must be a SkipReason")


@dataclass(frozen=True, slots=True)
class TranscriptionQueue:
    """One "transcribe project" request; its jobs are linked by position."""

    id: UUID
    project_id: UUID
    created_at: datetime
    skipped: tuple[SkippedRecording, ...] = ()

    def __post_init__(self) -> None:
        require_uuid(self.id, field="id")
        require_uuid(self.project_id, field="project_id")
        object.__setattr__(
            self,
            "created_at",
            require_aware_datetime(self.created_at, field="created_at"),
        )


__all__ = [
    "QueueItemStatus",
    "QueueState",
    "SkipReason",
    "SkippedRecording",
    "TranscriptionQueue",
    "queue_item_status",
    "queue_state",
]
