"""Time-bound acoustic speaker assignments in the domain model."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from voz.domain.entities._validation import require_non_blank, require_uuid


def _validate_offsets(start_ms: int, end_ms: int) -> None:
    if type(start_ms) is not int or type(end_ms) is not int:
        raise TypeError("speaker turn offsets must be integer milliseconds")
    if start_ms < 0 or end_ms < 0:
        raise ValueError("speaker turn offsets cannot be negative")
    if start_ms >= end_ms:
        raise ValueError("speaker turn start_ms must be less than end_ms")


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    """An acoustic cluster interval optionally assigned to a UI speaker."""

    transcript_id: UUID
    cluster_label: str
    start_ms: int
    end_ms: int
    id: UUID = field(default_factory=uuid4, kw_only=True)
    speaker_id: UUID | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_uuid(self.id, field="id"))
        object.__setattr__(
            self,
            "transcript_id",
            require_uuid(self.transcript_id, field="transcript_id"),
        )
        object.__setattr__(
            self,
            "cluster_label",
            require_non_blank(self.cluster_label, field="cluster_label"),
        )
        _validate_offsets(self.start_ms, self.end_ms)
        if self.speaker_id is not None:
            object.__setattr__(
                self,
                "speaker_id",
                require_uuid(self.speaker_id, field="speaker_id"),
            )

    def assign_speaker(self, speaker_id: UUID | None) -> SpeakerTurn:
        """Return a UI assignment without changing the acoustic cluster."""

        if speaker_id is not None:
            require_uuid(speaker_id, field="speaker_id")
        return replace(self, speaker_id=speaker_id)
