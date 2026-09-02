"""Unit tests for the Word domain entity."""

from uuid import UUID, uuid4

import pytest

from voz.domain.entities.word import Word


def make_word(
    *,
    start_ms: int = 100,
    end_ms: int = 250,
    text: str = " palabra ",
) -> Word:
    return Word(
        id=uuid4(),
        segment_id=uuid4(),
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
    )


def test_word_preserves_literal_text() -> None:
    word = make_word(text="  ¿Hola!  ")

    assert word.text == "  ¿Hola!  "


def test_word_generates_a_uuid_identity() -> None:
    word = Word(
        segment_id=uuid4(),
        start_ms=0,
        end_ms=1,
        text="token",
    )

    assert isinstance(word.id, UUID)


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(-1, 10), (0, -1), (100, 100), (101, 100)],
)
def test_word_rejects_invalid_offset_ranges(start_ms: int, end_ms: int) -> None:
    with pytest.raises(ValueError):
        make_word(start_ms=start_ms, end_ms=end_ms)


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(True, 10), (0, False)],
)
def test_word_rejects_non_integer_offsets(start_ms: int, end_ms: int) -> None:
    with pytest.raises(TypeError):
        make_word(start_ms=start_ms, end_ms=end_ms)


def test_word_rejects_empty_text_but_accepts_literal_whitespace() -> None:
    with pytest.raises(ValueError):
        make_word(text="")

    assert make_word(text=" ").text == " "


def test_word_rejects_non_string_text() -> None:
    with pytest.raises(TypeError):
        make_word(text=123)  # type: ignore[arg-type]


def test_word_rejects_non_uuid_identity() -> None:
    with pytest.raises(TypeError):
        Word(
            id="not-a-uuid",  # type: ignore[arg-type]
            segment_id=uuid4(),
            start_ms=0,
            end_ms=1,
            text="token",
        )
