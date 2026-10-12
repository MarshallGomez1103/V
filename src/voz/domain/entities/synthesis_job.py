"""Framework-independent speech synthesis job state machine (ADR-0010)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Self, cast
from uuid import UUID

from voz.domain.entities._validation import require_aware_datetime, require_uuid
from voz.domain.entities.synthesis_request import SynthesisRequest
from voz.domain.entities.transcription_job import InvalidJobTransition


class SynthesisJobState(StrEnum):
    """Lifecycle of a synthesis job, mirroring ``TranscriptionJobState``."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL

    @property
    def is_processable(self) -> bool:
        return self in _PIPELINE


_PIPELINE: Final[dict[SynthesisJobState, SynthesisJobState]] = {
    SynthesisJobState.QUEUED: SynthesisJobState.RUNNING,
    SynthesisJobState.RUNNING: SynthesisJobState.PERSISTING,
    SynthesisJobState.PERSISTING: SynthesisJobState.COMPLETED,
}
_TERMINAL: Final = frozenset(
    {SynthesisJobState.COMPLETED, SynthesisJobState.FAILED, SynthesisJobState.CANCELLED}
)
_ALLOWED: Final[dict[SynthesisJobState, frozenset[SynthesisJobState]]] = {
    state: frozenset(
        {successor, SynthesisJobState.FAILED, SynthesisJobState.CANCELLING}
    )
    for state, successor in _PIPELINE.items()
}
_ALLOWED[SynthesisJobState.CANCELLING] = frozenset({SynthesisJobState.CANCELLED})


def _require_count(value: object, *, field: str, minimum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    if value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def _require_error_code(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("error_code must be a string")
    if not value or value != value.strip():
        raise ValueError("error_code must be a non-empty trimmed string")
    return value


@dataclass(frozen=True, slots=True)
class SynthesisJob:
    """Immutable job snapshot; state changes only through explicit transitions.

    Progress is counted in text chunks (V2-04): ``chunks_done`` of
    ``chunks_total`` never decreases, and every chunk must be done before the
    job can persist its audio.
    """

    id: UUID
    request: SynthesisRequest
    state: SynthesisJobState
    chunks_done: int
    chunks_total: int
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    started_at: datetime | None = None
    """When the job first left ``QUEUED``."""

    def __post_init__(self) -> None:
        require_uuid(self.id, field="id")
        if not isinstance(cast(object, self.request), SynthesisRequest):
            raise TypeError("request must be a SynthesisRequest")
        if not isinstance(cast(object, self.state), SynthesisJobState):
            raise TypeError("state must be a SynthesisJobState")
        _require_count(self.chunks_total, field="chunks_total", minimum=1)
        _require_count(self.chunks_done, field="chunks_done", minimum=0)
        if self.chunks_done > self.chunks_total:
            raise ValueError("chunks_done cannot exceed chunks_total")
        for name in ("created_at", "updated_at", "started_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self, name, require_aware_datetime(value, field=name)
                )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if (
            self.state in (SynthesisJobState.PERSISTING, SynthesisJobState.COMPLETED)
            and self.chunks_done != self.chunks_total
        ):
            raise ValueError(f"a {self.state.value} job must have every chunk done")
        if self.error_code is not None:
            _require_error_code(self.error_code)
            if self.state is not SynthesisJobState.FAILED:
                raise ValueError("error_code is only valid for a failed job")

    @property
    def progress(self) -> float:
        """Fraction of chunks rendered, between 0 and 1."""

        return self.chunks_done / self.chunks_total

    @classmethod
    def create(
        cls,
        *,
        job_id: UUID,
        request: SynthesisRequest,
        chunks_total: int,
        now: datetime | None = None,
    ) -> Self:
        """Create a queued job with no chunk rendered yet."""

        timestamp = now if now is not None else datetime.now(UTC)
        return cls(
            id=job_id,
            request=request,
            state=SynthesisJobState.QUEUED,
            chunks_done=0,
            chunks_total=chunks_total,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def can_transition_to(self, target: object) -> bool:
        """Return whether ``target`` is an explicit successor of the current state."""

        return target in _ALLOWED.get(self.state, frozenset())

    def transition_to(
        self,
        target: object,
        *,
        at: datetime | None = None,
        error_code: str | None = None,
    ) -> Self:
        """Return the next valid job snapshot or reject the transition."""

        if not isinstance(target, SynthesisJobState):
            raise TypeError("target must be a SynthesisJobState")
        if not self.can_transition_to(target):
            raise InvalidJobTransition(
                f"cannot transition synthesis job from {self.state.value} "
                f"to {target.value}"
            )
        if target is SynthesisJobState.FAILED:
            _require_error_code(error_code)
        elif error_code is not None:
            raise ValueError("error_code can only accompany a transition to FAILED")
        timestamp = self._monotonic_timestamp(at)
        return replace(
            self,
            state=target,
            updated_at=timestamp,
            error_code=error_code,
            started_at=(
                timestamp
                if self.state is SynthesisJobState.QUEUED
                and target is SynthesisJobState.RUNNING
                else self.started_at
            ),
        )

    def with_chunks_done(
        self, chunks_done: object, *, at: datetime | None = None
    ) -> Self:
        """Return a running job snapshot with monotonic chunk progress."""

        if self.state is not SynthesisJobState.RUNNING:
            raise ValueError("chunk progress can only change while a job is running")
        done = _require_count(chunks_done, field="chunks_done", minimum=0)
        if done < self.chunks_done:
            raise ValueError("chunk progress cannot decrease")
        if done > self.chunks_total:
            raise ValueError("chunks_done cannot exceed chunks_total")
        return replace(self, chunks_done=done, updated_at=self._monotonic_timestamp(at))

    def _monotonic_timestamp(self, at: datetime | None) -> datetime:
        timestamp = require_aware_datetime(
            at if at is not None else datetime.now(UTC), field="at"
        )
        if timestamp < self.updated_at:
            raise ValueError("timestamp cannot be earlier than updated_at")
        return timestamp
