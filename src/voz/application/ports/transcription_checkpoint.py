"""Durable checkpoint contract for recoverable chunk transcription."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast, runtime_checkable
from uuid import UUID

from voz.application.ports.transcription import (
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.domain.entities.transcription_job import TranscriptionJob

_IMMUTABLE_REVISION = re.compile(r"[0-9a-f]{40}", re.ASCII)


@dataclass(frozen=True, slots=True)
class TranscriptionCheckpoint:
    """A fully confirmed chunk result with reproducible model identity."""

    job_id: UUID
    chunk_index: int
    process_start_ms: int
    process_end_ms: int
    owned_start_ms: int
    owned_end_ms: int
    provider_id: str
    model_id: str
    model_source: str | None
    model_revision: str | None
    requested_language: str | None
    segments: tuple[TranscriptionSegment, ...]
    language: str | None
    progress: float
    job_progress: float
    completed_at: datetime

    def __post_init__(self) -> None:
        raw_job_id = cast(object, self.job_id)
        if not isinstance(raw_job_id, UUID):
            raise TypeError("job_id must be a UUID")
        if type(self.chunk_index) is not int or self.chunk_index < 0:
            raise ValueError("chunk_index must be a non-negative integer")
        if not (
            0
            <= self.process_start_ms
            <= self.owned_start_ms
            < self.owned_end_ms
            <= self.process_end_ms
        ):
            raise ValueError("checkpoint chunk bounds are invalid")
        for field_name, value in (
            ("provider_id", self.provider_id),
            ("model_id", self.model_id),
        ):
            raw_value = cast(object, value)
            if (
                not isinstance(raw_value, str)
                or not raw_value
                or raw_value != raw_value.strip()
            ):
                raise ValueError(f"{field_name} must be non-empty and trimmed")
        for field_name, value in (
            ("model_source", self.model_source),
            ("model_revision", self.model_revision),
        ):
            raw_value = cast(object, value)
            if raw_value is not None and (
                not isinstance(raw_value, str)
                or not raw_value
                or raw_value != raw_value.strip()
            ):
                raise ValueError(f"{field_name} must be non-empty and trimmed")
        if (self.model_source is None) != (self.model_revision is None):
            raise ValueError(
                "model_source and model_revision must be provided together"
            )
        if (
            self.model_revision is not None
            and _IMMUTABLE_REVISION.fullmatch(self.model_revision) is None
        ):
            raise ValueError(
                "model_revision must be a 40-character lowercase commit SHA"
            )
        raw_segments = cast(object, self.segments)
        if not isinstance(raw_segments, tuple):
            raise TypeError("segments must contain TranscriptionSegment values")
        segments = cast(tuple[object, ...], raw_segments)
        if any(not isinstance(item, TranscriptionSegment) for item in segments):
            raise TypeError("segments must contain TranscriptionSegment values")
        typed_segments = cast(tuple[TranscriptionSegment, ...], raw_segments)
        TranscriptionResult(segments=(), language=self.requested_language)
        TranscriptionResult(segments=typed_segments, language=self.language)
        if any(
            item.start_ms < self.owned_start_ms or item.end_ms > self.owned_end_ms
            for item in typed_segments
        ):
            raise ValueError("checkpoint segments must remain within owned bounds")
        for field_name, value in (
            ("progress", self.progress),
            ("job_progress", self.job_progress),
        ):
            raw_value = cast(object, value)
            if isinstance(raw_value, bool) or not isinstance(
                raw_value,
                (int, float),
            ):
                raise TypeError(f"{field_name} must be a real number")
            if not 0.0 < raw_value <= 1.0:
                raise ValueError(
                    f"{field_name} must be greater than zero and at most one"
                )
            object.__setattr__(self, field_name, float(raw_value))
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")


@runtime_checkable
class TranscriptionCheckpointStore(Protocol):
    """Commit one chunk result and job progress in the same transaction."""

    def commit(
        self,
        checkpoint: TranscriptionCheckpoint,
        job: TranscriptionJob,
    ) -> None:
        """Atomically persist a complete checkpoint and matching job snapshot."""
        ...

    def list_for_job(self, job_id: UUID) -> Sequence[TranscriptionCheckpoint]:
        """Return confirmed chunks in index order after reopening storage."""
        ...


__all__ = ["TranscriptionCheckpoint", "TranscriptionCheckpointStore"]
