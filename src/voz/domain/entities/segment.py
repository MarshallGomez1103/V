"""Segment-level transcript timing in the domain model."""

from dataclasses import dataclass, field, replace
from typing import cast
from uuid import UUID, uuid4

from voz.domain.entities.word import Word


def _validate_uuid(value: object, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


def _validate_offsets(start_ms: int, end_ms: int) -> None:
    if type(start_ms) is not int or type(end_ms) is not int:
        raise TypeError("segment offsets must be integer milliseconds")
    if start_ms < 0 or end_ms < 0:
        raise ValueError("segment offsets cannot be negative")
    if start_ms >= end_ms:
        raise ValueError("segment start_ms must be less than end_ms")


def _validate_text(text: object) -> None:
    if not isinstance(text, str):
        raise TypeError("segment text must be a string")
    if text == "":
        raise ValueError("segment text cannot be empty")


@dataclass(frozen=True, slots=True)
class Segment:
    """A literal transcript span and its optional word-level timings."""

    transcript_id: UUID
    start_ms: int
    end_ms: int
    text: str
    id: UUID = field(default_factory=uuid4, kw_only=True)
    words: tuple[Word, ...] = field(default=(), kw_only=True)

    def __post_init__(self) -> None:
        _validate_uuid(self.id, "id")
        _validate_uuid(self.transcript_id, "transcript_id")
        _validate_offsets(self.start_ms, self.end_ms)
        _validate_text(self.text)
        self._validate_words(self.words)

    def _validate_words(self, words: object) -> None:
        if not isinstance(words, tuple):
            raise TypeError("segment words must be a tuple")
        validated_words = cast(tuple[object, ...], words)
        for word in validated_words:
            self._validate_word(word)

    def add_word(self, word: Word) -> "Segment":
        """Return a new segment containing a word that belongs to its timeline."""

        self._validate_word(word)
        return replace(self, words=(*self.words, word))

    def _validate_word(self, word: object) -> None:
        if not isinstance(word, Word):
            raise TypeError("segment words must be Word instances")
        if word.segment_id != self.id:
            raise ValueError("word must reference this segment")
        if word.start_ms < self.start_ms or word.end_ms > self.end_ms:
            raise ValueError("word offsets must remain within segment offsets")
