"""Known-answer tests for the WER/CER helpers (S13.10)."""

from __future__ import annotations

import pytest

from voz.application.evaluation import (
    ErrorRate,
    character_error_rate,
    edit_distance,
    normalize_text,
    word_error_rate,
)


def test_normalize_lowercases_strips_punctuation_and_keeps_accents_and_digits() -> None:
    assert normalize_text("  ¿Qué HORA es?  Son las 3, señor. ") == (
        "qué hora es son las 3 señor"
    )


def test_normalize_applies_nfkc_and_splits_on_apostrophes_and_hyphens() -> None:
    assert normalize_text("\uff21\uff22\uff23 \ufb01n don't a-b") == "abc fin don t a b"


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("", "", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("same", "same", 0),
        ("abcd", "abxd", 1),
    ],
)
def test_edit_distance_known_values(a: str, b: str, expected: int) -> None:
    assert edit_distance(a, b) == expected
    assert edit_distance(b, a) == expected


def test_edit_distance_works_on_word_lists() -> None:
    assert edit_distance(["a", "b", "c"], ["a", "c"]) == 1


def test_wer_counts_substitution_insertion_and_deletion() -> None:
    result = word_error_rate("el gato negro duerme", "El gato blanco duerme mucho.")
    assert result == ErrorRate(edits=2, reference_length=4)
    assert result.rate == 0.5


def test_wer_ignores_case_and_punctuation_but_not_accents() -> None:
    assert word_error_rate("Está aquí.", "esta AQUÍ").rate == 0.5
    assert word_error_rate("Está aquí.", "ESTÁ, aquí!").rate == 0.0


def test_cer_known_value() -> None:
    result = character_error_rate("hola mundo", "hola mundp")
    assert result == ErrorRate(edits=1, reference_length=10)
    assert result.rate == 0.1


def test_wer_can_exceed_one_and_handles_empty_reference() -> None:
    assert word_error_rate("hola", "hola y adiós a todos").rate == 4.0
    assert word_error_rate("", "").rate == 0.0
    assert word_error_rate("", "algo").rate is None
    assert word_error_rate("algo", "").rate == 1.0
