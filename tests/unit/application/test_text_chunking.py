# ruff: noqa: RUF001  (CJK full-width punctuation is the point of these tests)
import random
import unicodedata

import pytest

from voz.application.text_chunking import (
    CHUNK_SILENCE_MS,
    PARAGRAPH_SILENCE_MS,
    TextChunk,
    plan_text_chunks,
    silence_gap_ms,
)


def texts(text: str, max_chars: int) -> list[str]:
    return [c.text for c in plan_text_chunks(text, max_chars=max_chars)]


def _glued(s: str, i: int) -> bool:
    """True if s[i] cannot be separated from s[i-1] (mark, ZWJ, skin tone)."""
    return (
        "\u200d" in (s[i], s[i - 1])
        or unicodedata.category(s[i]) in ("Mn", "Me", "Mc")
        or "\U0001f3fb" <= s[i] <= "\U0001f3ff"
    )


def assert_invariants(text: str, max_chars: int) -> tuple[TextChunk, ...]:
    chunks = plan_text_chunks(text, max_chars=max_chars)
    previous_end = 0
    for i, c in enumerate(chunks):
        assert c.index == i
        assert c.text == text[c.start : c.end]
        assert c.text == c.text.strip() and c.text
        assert c.start >= previous_end  # increasing, no overlap
        assert text[previous_end : c.start].strip() == ""  # only whitespace skipped
        # only an indivisible grapheme cluster may exceed the limit
        if len(c.text) > max_chars:  # only an indivisible cluster may exceed the limit
            assert all(_glued(c.text, k) for k in range(1, len(c.text)))
        previous_end = c.end
    assert text[previous_end:].strip() == ""
    joined = "".join("".join(c.text.split()) for c in chunks)
    assert joined == "".join(text.split())
    return chunks


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t ", "\u00a0"])
def test_empty_or_blank_text_yields_no_chunks(text: str) -> None:
    assert plan_text_chunks(text, max_chars=50) == ()


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_invalid_max_chars_raises(bad: int) -> None:
    with pytest.raises(ValueError, match="max_chars"):
        plan_text_chunks("Hola.", max_chars=bad)


def test_one_short_sentence_is_one_chunk_with_trimmed_offsets() -> None:
    chunks = plan_text_chunks("  Hola mundo.  ", max_chars=100)
    assert chunks == (TextChunk(index=0, text="Hola mundo.", start=2, end=13),)


def test_sentences_that_fit_are_grouped_and_overflow_starts_a_new_chunk() -> None:
    text = "Uno. Dos. Tres. Cuatro."
    assert texts(text, 100) == [text]
    assert texts(text, 9) == ["Uno. Dos.", "Tres.", "Cuatro."]
    assert texts(text, 7) == ["Uno.", "Dos.", "Tres.", "Cuatro."]
    assert_invariants(text, 4)


def test_exact_limit_fits() -> None:
    assert texts("Abcd. Efgh.", 11) == ["Abcd. Efgh."]
    assert texts("Abcd. Efgh.", 10) == ["Abcd.", "Efgh."]


@pytest.mark.parametrize("terminator", ["!", "?", "…", "。", "！", "？"])
def test_all_sentence_terminators_split(terminator: str) -> None:
    text = f"Primera{terminator} Segunda{terminator}"
    assert texts(text, 12) == [f"Primera{terminator}", f"Segunda{terminator}"]


def test_closing_quote_stays_with_its_sentence() -> None:
    assert texts('Dijo "hola." Luego se fue.', 14) == ['Dijo "hola."', "Luego se fue."]


def test_long_sentence_with_commas_cuts_at_the_last_comma_that_fits() -> None:
    text = "alfa beta, gamma delta, epsilon zeta eta"
    chunks = assert_invariants(text, 25)
    assert [c.text for c in chunks] == ["alfa beta, gamma delta,", "epsilon zeta eta"]


def test_early_comma_is_ignored_in_favor_of_a_later_space() -> None:
    text = "a, bcdefgh ijklmnop qrstuv"
    assert texts(text, 20) == ["a, bcdefgh ijklmnop", "qrstuv"]


def test_long_sentence_without_commas_cuts_at_the_last_space() -> None:
    text = "uno dos tres cuatro cinco seis siete"
    chunks = assert_invariants(text, 15)
    assert [c.text for c in chunks] == ["uno dos tres", "cuatro cinco", "seis siete"]


def test_cut_may_land_exactly_on_the_limit_when_a_space_follows() -> None:
    assert texts("abcde fghij klmno", 5) == ["abcde", "fghij", "klmno"]


def test_no_punctuation_and_no_spaces_falls_back_to_characters() -> None:
    text = "x" * 25
    assert texts(text, 10) == ["x" * 10, "x" * 10, "x" * 5]


def test_word_longer_than_the_limit_is_split_without_losing_neighbors() -> None:
    text = "corto supercalifragilistico fin"
    chunks = assert_invariants(text, 10)
    assert [c.text for c in chunks] == ["corto", "supercalif", "ragilistic", "o fin"]


def test_combining_marks_are_never_separated_from_their_base() -> None:
    text = "e\u0301" * 12  # 24 code points, 12 graphemes
    for limit in (3, 5, 7):
        for c in assert_invariants(text, limit):
            assert unicodedata.normalize("NFD", c.text)[0] == "e"
            assert not unicodedata.combining(c.text[0])


def test_a_single_grapheme_longer_than_the_limit_is_kept_whole() -> None:
    text = "e\u0301\u0302\u0303"
    assert texts(text, 2) == [text]


def test_zwj_emoji_sequence_is_not_split() -> None:
    family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
    text = family * 4
    for c in assert_invariants(text, 7):
        assert c.text.count(family) >= 1
        assert c.text == family * (len(c.text) // len(family))


def test_variation_selector_and_skin_tone_stay_with_their_emoji() -> None:
    text = "❤\ufe0f" * 6 + "\U0001f44d\U0001f3fd" * 6
    for c in assert_invariants(text, 3):
        assert c.text[0] not in "\ufe0f\U0001f3fd"


def test_emoji_text_with_spaces() -> None:
    text = "Hola \U0001f600 mundo \U0001f30d! Adiós \U0001f44b."
    assert texts(text, 20) == ["Hola \U0001f600 mundo \U0001f30d!", "Adiós \U0001f44b."]


def test_cjk_splits_on_ideographic_punctuation_without_spaces() -> None:
    text = "今天天气很好。我们去公园！你来吗？"
    assert texts(text, 8) == ["今天天气很好。", "我们去公园！", "你来吗？"]
    assert texts(text, 100) == [text]


def test_cjk_long_sentence_cuts_at_cjk_comma_then_by_characters() -> None:
    assert texts("今天天气很好，我们去公园玩耍吧", 9) == [
        "今天天气很好，",
        "我们去公园玩耍吧",
    ]
    assert texts("一二三四五六七八九十", 4) == ["一二三四", "五六七八", "九十"]


@pytest.mark.parametrize(
    ("text", "max_chars", "expected"),
    [
        ("El Sr. Pérez llegó. Se fue.", 20, ["El Sr. Pérez llegó.", "Se fue."]),
        (
            "La Dra. López vio al Dr. Ruiz. Fin.",
            31,
            ["La Dra. López vio al Dr. Ruiz.", "Fin."],
        ),
        (
            "Hay frutas, p. ej. manzanas. Otra.",
            30,
            ["Hay frutas, p. ej. manzanas.", "Otra."],
        ),
        ("Use tools, e.g. a hammer. Next.", 25, ["Use tools, e.g. a hammer.", "Next."]),
        ("Es decir, i.e. otra cosa. Fin.", 25, ["Es decir, i.e. otra cosa.", "Fin."]),
        ("Vino A. Gomez al fin. Luego.", 22, ["Vino A. Gomez al fin.", "Luego."]),
        ("En los EE.UU. hubo sol. Fin.", 24, ["En los EE.UU. hubo sol.", "Fin."]),
    ],
)
def test_abbreviations_do_not_split_the_sentence(
    text: str, max_chars: int, expected: list[str]
) -> None:
    assert texts(text, max_chars) == expected
    assert_invariants(text, max_chars)


def test_etc_ends_a_sentence_only_before_a_capital() -> None:
    assert texts("Pan, leche, etc. Después salimos.", 20) == [
        "Pan, leche, etc.",
        "Después salimos.",
    ]
    assert texts("Pan, leche, etc. y más cosas.", 14) != [
        "Pan, leche, etc.",
        "y más cosas.",
    ]


def test_decimal_numbers_and_dotted_tokens_do_not_split() -> None:
    assert texts("Pi vale 3.14 más o menos. Fin.", 26) == [
        "Pi vale 3.14 más o menos.",
        "Fin.",
    ]
    assert texts("Visita ejemplo.com ahora. Fin.", 25) == [
        "Visita ejemplo.com ahora.",
        "Fin.",
    ]


def test_ellipsis_inside_a_word_run_does_not_split_but_trailing_one_does() -> None:
    assert texts("Espera…ya voy. Hola…", 14) == ["Espera…ya voy.", "Hola…"]
    assert texts("Bueno… Sigamos.", 8) == ["Bueno…", "Sigamos."]


def test_paragraph_break_is_a_boundary_even_without_punctuation() -> None:
    text = "Título sin punto\n\nPrimer párrafo\n  \n  Segundo"
    assert texts(text, 20) == ["Título sin punto", "Primer párrafo", "Segundo"]
    # grouped when they fit, keeping the original text between them
    [chunk] = plan_text_chunks(text, max_chars=100)
    assert chunk.text == text


def test_single_newline_is_just_whitespace() -> None:
    assert texts("linea uno\nlinea dos", 100) == ["linea uno\nlinea dos"]


def test_silence_gap_is_longer_across_paragraphs() -> None:
    text = "Uno.\n\nDos. Tres."
    a, b, c = plan_text_chunks(text, max_chars=8)
    assert silence_gap_ms(text[a.end : b.start]) == PARAGRAPH_SILENCE_MS
    assert silence_gap_ms(text[b.end : c.start]) == CHUNK_SILENCE_MS
    assert silence_gap_ms("") == CHUNK_SILENCE_MS
    assert 0 < CHUNK_SILENCE_MS < PARAGRAPH_SILENCE_MS


def test_chunks_are_immutable() -> None:
    [chunk] = plan_text_chunks("Hola.", max_chars=10)
    with pytest.raises(AttributeError):
        chunk.text = "otro"  # type: ignore[misc]


def test_planning_is_deterministic_and_does_not_mutate_input() -> None:
    text = "Uno, dos. Tres cuatro cinco.\n\nSeis."
    assert plan_text_chunks(text, max_chars=9) == plan_text_chunks(text, max_chars=9)


def test_random_text_keeps_every_invariant() -> None:
    rng = random.Random(1103)
    alphabet = list("ab cde  fg,;.!?…。！？\n\t\u0301\u200d😀今天 Sr.A3.14")
    for _ in range(400):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 160)))
        assert_invariants(text, rng.choice([1, 2, 3, 5, 8, 13, 40, 200]))
