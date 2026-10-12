"""Word-level transcript timing in the domain model."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from voz.domain.entities._validation import require_uuid


def _validate_offsets(start_ms: int, end_ms: int) -> None:
    if type(start_ms) is not int or type(end_ms) is not int:
        raise TypeError("word offsets must be integer milliseconds")
    if start_ms < 0 or end_ms < 0:
        raise ValueError("word offsets cannot be negative")
    if start_ms >= end_ms:
        raise ValueError("word start_ms must be less than end_ms")


def _validate_text(text: object) -> None:
    if not isinstance(text, str):
        raise TypeError("word text must be a string")
    if text == "":
        raise ValueError("word text cannot be empty")


@dataclass(frozen=True, slots=True)
class Word:
    """A literal transcript token located inside a segment timeline."""

    segment_id: UUID
    start_ms: int
    end_ms: int
    text: str
    id: UUID = field(default_factory=uuid4, kw_only=True)

    def __post_init__(self) -> None:
        require_uuid(self.id, field="id")
        require_uuid(self.segment_id, field="segment_id")
        _validate_offsets(self.start_ms, self.end_ms)
        _validate_text(self.text)
