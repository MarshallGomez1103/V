"""Framework-independent transcription job state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Final, Self
from uuid import UUID


class TranscriptionJobState(StrEnum):
    """Explicit lifecycle states for long-running transcription work."""

    QUEUED = "QUEUED"
    PROBING = "PROBING"
    PREPROCESSING = "PREPROCESSING"
    TRANSCRIBING = "TRANSCRIBING"
    ALIGNING = "ALIGNING"
    DIARIZING = "DIARIZING"
    MERGING = "MERGING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATES

    @property
    def is_processable(self) -> bool:
        return self in PROCESSABLE_STATES


PROCESSABLE_STATES: Final[frozenset[TranscriptionJobState]] = frozenset(
    {
        TranscriptionJobState.QUEUED,
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
        TranscriptionJobState.ALIGNING,
        TranscriptionJobState.DIARIZING,
        TranscriptionJobState.MERGING,
        TranscriptionJobState.PERSISTING,
    }
)

TERMINAL_STATES: Final[frozenset[TranscriptionJobState]] = frozenset(
    {
        TranscriptionJobState.COMPLETED,
        TranscriptionJobState.FAILED,
        TranscriptionJobState.CANCELLED,
    }
)

_PIPELINE_SUCCESSORS: Final[dict[TranscriptionJobState, TranscriptionJobState]] = {
    TranscriptionJobState.QUEUED: TranscriptionJobState.PROBING,
    TranscriptionJobState.PROBING: TranscriptionJobState.PREPROCESSING,
    TranscriptionJobState.PREPROCESSING: TranscriptionJobState.TRANSCRIBING,
    TranscriptionJobState.TRANSCRIBING: TranscriptionJobState.ALIGNING,
    TranscriptionJobState.ALIGNING: TranscriptionJobState.DIARIZING,
    TranscriptionJobState.DIARIZING: TranscriptionJobState.MERGING,
    TranscriptionJobState.MERGING: TranscriptionJobState.PERSISTING,
    TranscriptionJobState.PERSISTING: TranscriptionJobState.COMPLETED,
}

_ALLOWED_TRANSITIONS: Final[
    dict[TranscriptionJobState, frozenset[TranscriptionJobState]]
] = {
    state: frozenset(
        {
            _PIPELINE_SUCCESSORS[state],
            TranscriptionJobState.FAILED,
            TranscriptionJobState.CANCELLING,
        }
    )
    for state in PROCESSABLE_STATES
}
_ALLOWED_TRANSITIONS[TranscriptionJobState.CANCELLING] = frozenset(
    {TranscriptionJobState.CANCELLED}
)


class InvalidJobTransition(ValueError):
    """Raised when a job lifecycle transition is not explicitly permitted."""


def _require_uuid(value: object, *, field_name: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")
    return value


def _require_state(value: object, *, field_name: str) -> TranscriptionJobState:
    if not isinstance(value, TranscriptionJobState):
        raise TypeError(f"{field_name} must be a TranscriptionJobState")
    return value


def _require_progress(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("progress must be a real number")
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("progress must be finite and between 0 and 1")
    return float(value)


def _require_aware_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_error_code(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("error_code must be a string")
    if not value or value != value.strip():
        raise ValueError("error_code must be a non-empty trimmed string")
    return value


@dataclass(frozen=True, slots=True)
class TranscriptionJob:
    """Immutable job snapshot whose state changes only through explicit transitions."""

    id: UUID
    project_id: UUID
    media_asset_id: UUID
    state: TranscriptionJobState
    progress: float
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    started_at: datetime | None = None
    """When the job first left ``QUEUED`` (picked up by the worker)."""
    stage_started_at: datetime | None = None
    """When the current state began; ``None`` for jobs from before stage timing."""
    stage_progress: float | None = None
    """Progress inside the current stage (0..1); ``None`` when it has no measure."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_uuid(self.id, field_name="id"))
        object.__setattr__(
            self,
            "project_id",
            _require_uuid(self.project_id, field_name="project_id"),
        )
        object.__setattr__(
            self,
            "media_asset_id",
            _require_uuid(self.media_asset_id, field_name="media_asset_id"),
        )
        object.__setattr__(
            self,
            "state",
            _require_state(self.state, field_name="state"),
        )
        object.__setattr__(self, "progress", _require_progress(self.progress))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_timestamp(self.created_at, field_name="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _require_aware_timestamp(self.updated_at, field_name="updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")

        if self.state is TranscriptionJobState.COMPLETED and self.progress != 1.0:
            raise ValueError("a completed job must have progress equal to 1")

        if self.error_code is not None:
            object.__setattr__(self, "error_code", _require_error_code(self.error_code))
            if self.state is not TranscriptionJobState.FAILED:
                raise ValueError("error_code is only valid for a failed job")

        for name in ("started_at", "stage_started_at"):
            value = getattr(self, name)
            if value is not None:
                _require_aware_timestamp(value, field_name=name)
        if self.stage_progress is not None:
            object.__setattr__(
                self, "stage_progress", _require_progress(self.stage_progress)
            )

    @classmethod
    def create(
        cls,
        *,
        job_id: UUID,
        project_id: UUID,
        media_asset_id: UUID,
        now: datetime | None = None,
    ) -> Self:
        """Create a new queued job with zero progress."""

        timestamp = now if now is not None else datetime.now(UTC)
        return cls(
            id=job_id,
            project_id=project_id,
            media_asset_id=media_asset_id,
            state=TranscriptionJobState.QUEUED,
            progress=0.0,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def can_transition_to(self, target: object) -> bool:
        """Return whether ``target`` is an explicit successor of the current state."""

        return target in _ALLOWED_TRANSITIONS.get(self.state, frozenset())

    def transition_to(
        self,
        target: object,
        *,
        at: datetime | None = None,
        error_code: str | None = None,
    ) -> Self:
        """Return the next valid job snapshot or reject the transition."""

        validated_target = _require_state(target, field_name="target")
        if not self.can_transition_to(validated_target):
            raise InvalidJobTransition(
                f"cannot transition transcription job from {self.state.value} "
                f"to {validated_target.value}"
            )
        if (
            validated_target is not TranscriptionJobState.FAILED
            and error_code is not None
        ):
            raise ValueError("error_code can only accompany a transition to FAILED")

        timestamp = at if at is not None else datetime.now(UTC)
        _require_aware_timestamp(timestamp, field_name="at")
        if timestamp < self.updated_at:
            raise ValueError("transition timestamp cannot be earlier than updated_at")

        return replace(
            self,
            state=validated_target,
            progress=(
                1.0
                if validated_target is TranscriptionJobState.COMPLETED
                else self.progress
            ),
            updated_at=timestamp,
            error_code=(
                error_code if validated_target is TranscriptionJobState.FAILED else None
            ),
            started_at=(
                timestamp
                if self.state is TranscriptionJobState.QUEUED
                and validated_target is TranscriptionJobState.PROBING
                and self.started_at is None
                else self.started_at
            ),
            stage_started_at=timestamp,
            stage_progress=None,
        )

    def with_progress(self, progress: object, *, at: datetime | None = None) -> Self:
        """Return a processable job snapshot with monotonic progress."""

        if not self.state.is_processable:
            raise ValueError("progress can only change while a job is processable")
        validated_progress = _require_progress(progress)
        if validated_progress < self.progress:
            raise ValueError("progress cannot decrease")

        timestamp = at if at is not None else datetime.now(UTC)
        _require_aware_timestamp(timestamp, field_name="at")
        if timestamp < self.updated_at:
            raise ValueError("progress timestamp cannot be earlier than updated_at")

        return replace(self, progress=validated_progress, updated_at=timestamp)

    def with_stage_progress(
        self,
        stage_progress: object,
        *,
        progress: object | None = None,
        at: datetime | None = None,
    ) -> Self:
        """Return a snapshot with progress inside the current stage.

        The stage fraction never decreases within a stage; the global ``progress``
        (when given) is raised to at least its current value.
        """

        if not self.state.is_processable:
            raise ValueError("progress can only change while a job is processable")
        validated_stage = _require_progress(stage_progress)
        if self.stage_progress is not None and validated_stage < self.stage_progress:
            raise ValueError("stage progress cannot decrease")
        global_progress = (
            self.progress
            if progress is None
            else max(self.progress, _require_progress(progress))
        )
        timestamp = self._monotonic_timestamp(at, "progress")
        return replace(
            self,
            progress=global_progress,
            stage_progress=validated_stage,
            updated_at=timestamp,
        )

    def reopen_for_diarization(
        self, *, progress: object, at: datetime | None = None
    ) -> Self:
        """Return a finished job sent back to ``DIARIZING`` to redo only speakers.

        The transcript is kept; the pipeline then ends in ``COMPLETED`` again.
        """

        if not self.state.is_terminal:
            raise ValueError("only a finished job can be reopened")
        timestamp = self._monotonic_timestamp(at, "reopen")
        return replace(
            self,
            state=TranscriptionJobState.DIARIZING,
            progress=_require_progress(progress),
            updated_at=timestamp,
            error_code=None,
            stage_started_at=timestamp,
            stage_progress=None,
        )

    def restart_stage(self, *, at: datetime | None = None) -> Self:
        """Restart the clock of the current stage (work redone after a recovery)."""

        if not self.state.is_processable:
            raise ValueError("a stage can only restart while a job is processable")
        timestamp = self._monotonic_timestamp(at, "stage")
        return replace(
            self, stage_started_at=timestamp, stage_progress=None, updated_at=timestamp
        )

    def _monotonic_timestamp(self, at: datetime | None, label: str) -> datetime:
        timestamp = at if at is not None else datetime.now(UTC)
        _require_aware_timestamp(timestamp, field_name="at")
        if timestamp < self.updated_at:
            raise ValueError(f"{label} timestamp cannot be earlier than updated_at")
        return timestamp
