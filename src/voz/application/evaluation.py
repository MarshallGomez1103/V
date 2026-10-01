"""Word and character error rates for optional ASR quality benchmarks (S13.10).

Pure standard-library functions. Both texts go through :func:`normalize_text`
before comparison, so the score ignores case and punctuation but never accents.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass


def normalize_text(text: str) -> str:
    """Normalize a transcript for scoring.

    1. Unicode NFKC (compatibility forms such as ligatures or full-width).
    2. Lowercase with ``casefold``.
    3. Every punctuation (``P*``) or symbol (``S*``) character becomes a space.
       Apostrophes and hyphens therefore split words on both sides alike.
    4. Runs of whitespace collapse to one space; the ends are trimmed.

    Accents and digits are kept as they are: numbers are NOT spelled out or
    converted ("3" and "tres" differ), because that would hide real errors.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    cleaned = "".join(
        " " if unicodedata.category(char)[0] in "PS" else char for char in folded
    )
    return " ".join(cleaned.split())


@dataclass(frozen=True, slots=True)
class ErrorRate:
    """Edit distance against a reference; ``rate`` is ``None`` without reference."""

    edits: int
    reference_length: int

    @property
    def rate(self) -> float | None:
        if self.reference_length > 0:
            return self.edits / self.reference_length
        # An empty reference only scores perfectly against an empty hypothesis.
        return 0.0 if self.edits == 0 else None


def edit_distance[T](reference: Sequence[T], hypothesis: Sequence[T]) -> int:
    """Levenshtein distance (substitution, insertion, deletion all cost 1)."""
    start = 0
    limit = min(len(reference), len(hypothesis))
    while start < limit and reference[start] == hypothesis[start]:
        start += 1
    end_a, end_b = len(reference), len(hypothesis)
    while (
        end_a > start
        and end_b > start
        and reference[end_a - 1] == hypothesis[end_b - 1]
    ):
        end_a -= 1
        end_b -= 1
    a, b = reference[start:end_a], hypothesis[start:end_b]
    if not a or not b:
        return max(len(a), len(b))
    previous = list(range(len(b) + 1))
    for i, item in enumerate(a, 1):
        current = [i]
        for j, other in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (item != other),
                )
            )
        previous = current
    return previous[-1]


def word_error_rate(reference: str, hypothesis: str) -> ErrorRate:
    """Word-level errors after normalization."""
    ref = normalize_text(reference).split()
    return ErrorRate(edit_distance(ref, normalize_text(hypothesis).split()), len(ref))


def character_error_rate(reference: str, hypothesis: str) -> ErrorRate:
    """Character-level errors after normalization (single spaces count)."""
    ref = normalize_text(reference)
    return ErrorRate(edit_distance(ref, normalize_text(hypothesis)), len(ref))


__all__ = [
    "ErrorRate",
    "character_error_rate",
    "edit_distance",
    "normalize_text",
    "word_error_rate",
]
