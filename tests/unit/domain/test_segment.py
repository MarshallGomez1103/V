"""Unit tests for the Segment domain entity."""

from uuid import UUID, uuid4

import pytest

from voz.domain.entities.segment import Segment
from voz.domain.entities.word import Word


def make_segment(
    *,
    segment_id: UUID | None = None,
    start_ms: int = 100,
    end_ms: int = 1_000,
    text: str = " segmento literal ",
    words: tuple[Word, ...] = (),
) -> Segment:
    return Segment(
        id=segment_id or uuid4(),
        transcript_id=uuid4(),
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        words=words,
    )


def make_word(
    segment_id: UUID,
    *,
    start_ms: int = 100,
    end_ms: int = 250,
) -> Word:
    return Word(
        id=uuid4(),
        segment_id=segment_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=" palabra ",
    )


def test_segment_preserves_literal_text() -> None:
    segment = make_segment(text="  ¿Qué dijo?  ")

    assert segment.text == "  ¿Qué dijo?  "


def test_segment_generates_a_uuid_identity() -> None:
    segment = Segment(
        transcript_id=uuid4(),
        start_ms=0,
        end_ms=1,
        text="segmento",
    )

    assert isinstance(segment.id, UUID)


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(-1, 10), (0, -1), (100, 100), (101, 100)],
)
def test_segment_rejects_invalid_offset_ranges(start_ms: int, end_ms: int) -> None:
    with pytest.raises(ValueError):
        make_segment(start_ms=start_ms, end_ms=end_ms)


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(True, 10), (0, False)],
)
def test_segment_rejects_non_integer_offsets(start_ms: int, end_ms: int) -> None:
    with pytest.raises(TypeError):
        make_segment(start_ms=start_ms, end_ms=end_ms)


def test_segment_rejects_empty_text_but_accepts_literal_whitespace() -> None:
    with pytest.raises(ValueError):
        make_segment(text="")

    assert make_segment(text=" ").text == " "


def test_segment_rejects_non_string_text() -> None:
    with pytest.raises(TypeError):
        make_segment(text=123)  # type: ignore[arg-type]


def test_segment_adds_a_word_within_its_bounds_without_mutating_itself() -> None:
    segment = make_segment()
    word = make_word(segment.id, start_ms=segment.start_ms, end_ms=segment.end_ms)

    updated = segment.add_word(word)

    assert segment.words == ()
    assert updated.words == (word,)


def test_segment_rejects_a_word_owned_by_another_segment() -> None:
    segment = make_segment()
    foreign_word = make_word(uuid4())

    with pytest.raises(ValueError, match="reference this segment"):
        segment.add_word(foreign_word)


@pytest.mark.parametrize(
    ("word_start_ms", "word_end_ms"),
    [(99, 250), (250, 1_001)],
)
def test_segment_rejects_a_word_outside_its_bounds(
    word_start_ms: int,
    word_end_ms: int,
) -> None:
    segment = make_segment()
    word = make_word(
        segment.id,
        start_ms=word_start_ms,
        end_ms=word_end_ms,
    )

    with pytest.raises(ValueError, match="within segment offsets"):
        segment.add_word(word)


def test_segment_validates_words_during_aggregate_construction() -> None:
    segment_id = uuid4()
    foreign_word = make_word(uuid4())

    with pytest.raises(ValueError, match="reference this segment"):
        make_segment(segment_id=segment_id, words=(foreign_word,))
