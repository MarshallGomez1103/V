"""Segment-level transcript timing in the domain model."""

import math
from dataclasses import dataclass, field, replace
from typing import cast
from uuid import UUID, uuid4

from voz.domain.entities._validation import require_uuid
from voz.domain.entities.word import Word


# ponytail: word.py and speaker_turn.py keep their own _validate_offsets: the
# error messages name the entity, so they are not interchangeable. Ceiling: one
# shared check taking the entity noun once a fourth entity needs it.
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
    speaker_id: UUID | None = field(default=None, kw_only=True)
    edited: bool = field(default=False, kw_only=True)
    revision: int = field(default=0, kw_only=True)
    original_text: str | None = field(default=None, kw_only=True)
    # Non-destructive quality hints (S13.04/S13.05); they never change ``text``.
    quality_flags: tuple[str, ...] = field(default=(), kw_only=True)
    avg_logprob: float | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        require_uuid(self.id, field="id")
        require_uuid(self.transcript_id, field="transcript_id")
        if self.speaker_id is not None:
            require_uuid(self.speaker_id, field="speaker_id")
        if type(self.edited) is not bool:
            raise TypeError("segment edited must be a bool")
        if type(self.revision) is not int:
            raise TypeError("segment revision must be an integer")
        if self.revision < 0:
            raise ValueError("segment revision cannot be negative")
        if self.original_text is not None:
            _validate_text(self.original_text)
        self._validate_quality()
        _validate_offsets(self.start_ms, self.end_ms)
        _validate_text(self.text)
        self._validate_words(self.words)

    def _validate_quality(self) -> None:
        flags = cast(object, self.quality_flags)
        if not isinstance(flags, tuple) or not all(
            isinstance(flag, str) and flag for flag in cast(tuple[object, ...], flags)
        ):
            raise TypeError(
                "segment quality_flags must be a tuple of non-empty strings"
            )
        logprob = cast(object, self.avg_logprob)
        if logprob is not None and (
            isinstance(logprob, bool)
            or not isinstance(logprob, (int, float))
            or not math.isfinite(logprob)
        ):
            raise TypeError("segment avg_logprob must be a finite number or None")

    def edit_text(self, text: str) -> "Segment":
        """Return a copy with corrected text, keeping the literal ASR text once."""

        _validate_text(text)
        original = self.original_text if self.edited else self.text
        return replace(
            self,
            text=text,
            edited=True,
            revision=self.revision + 1,
            original_text=original,
        )

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
