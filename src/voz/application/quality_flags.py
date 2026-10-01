"""Non-destructive transcript quality heuristics (S13.04, S13.05, S13.12).

Pure functions: they read what the engine reported and return stable flags that
live next to the literal text. They never alter, drop or "correct" text; only a
user edit may change what the transcript says.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from voz.application.ports.transcription import TranscriptionSegment

REPETITION: Final = "repetition"
SILENCE_HALLUCINATION: Final = "silence_hallucination"
OUT_OF_BOUNDS: Final = "out_of_bounds"
LOW_CONFIDENCE: Final = "low_confidence"

# Stable order: what the API and the UI show.
ALL_FLAGS: Final = (REPETITION, SILENCE_HALLUCINATION, OUT_OF_BOUNDS, LOW_CONFIDENCE)

# Whisper's own fallback thresholds (openai/whisper ``compression_ratio_threshold``
# and ``logprob_threshold``/``no_speech_threshold``), kept as documented constants.
COMPRESSION_RATIO_LIMIT: Final = 2.4
NO_SPEECH_PROB_LIMIT: Final = 0.6
LOW_CONFIDENCE_LOGPROB: Final = -1.0
# Looser evidence suffices when the text is also a classic silence hallucination.
PHRASE_NO_SPEECH_PROB: Final = 0.3
# A segment may overshoot the audio by rounding; more than this is out of bounds.
OUT_OF_BOUNDS_TOLERANCE_MS: Final = 500
# Consecutive repeats of the same n-gram: a single word may be a real laugh or
# stutter, so it needs more repeats than a repeated phrase.
_WORD_REPEATS: Final = 5
_PHRASE_REPEATS: Final = 3
_MAX_NGRAM: Final = 4

# Typical phrases Whisper invents over silence or noise (normalized, lowercase).
_HALLUCINATION_PHRASES: Final = frozenset(
    {
        "thank you",
        "thanks for watching",
        "thank you for watching",
        "please subscribe",
        "subscribe to my channel",
        "gracias",
        "gracias por ver el video",
        "gracias por ver",
        "suscribete",
        "subtitulos por la comunidad de amara org",
        "you",
        "bye",
    }
)

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def _has_repeated_ngram(tokens: list[str]) -> bool:
    """True when one n-gram repeats back to back more than the limits allow."""
    for size in range(1, _MAX_NGRAM + 1):
        needed = _WORD_REPEATS if size == 1 else _PHRASE_REPEATS
        if len(tokens) < size * needed:
            break
        for start in range(len(tokens) - size * needed + 1):
            gram = tokens[start : start + size]
            if all(
                tokens[start + size * k : start + size * (k + 1)] == gram
                for k in range(1, needed)
            ):
                return True
    return False


def _is_hallucination_phrase(text: str) -> bool:
    # Accents are dropped so "Suscríbete" matches; the stored text is untouched.
    return " ".join(_tokens(_strip_accents(text))) in _HALLUCINATION_PHRASES


def _strip_accents(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def quality_flags(
    segment: TranscriptionSegment,
    *,
    audio_duration_ms: int | None = None,
) -> tuple[str, ...]:
    """Return the stable flags (in ``ALL_FLAGS`` order) that apply to a segment.

    ``audio_duration_ms`` is the duration of the audio the segment was decoded
    from; omit it when unknown.
    """
    found: set[str] = set()
    tokens = _tokens(segment.text)
    if (
        segment.compression_ratio is not None
        and segment.compression_ratio > COMPRESSION_RATIO_LIMIT
    ) or _has_repeated_ngram(tokens):
        found.add(REPETITION)

    out_of_bounds = segment.exceeds_audio or (
        audio_duration_ms is not None
        and segment.end_ms > audio_duration_ms + OUT_OF_BOUNDS_TOLERANCE_MS
    )
    if out_of_bounds:
        found.add(OUT_OF_BOUNDS)

    no_speech = segment.no_speech_prob
    logprob = segment.avg_logprob
    evident_silence = (
        no_speech is not None
        and logprob is not None
        and no_speech > NO_SPEECH_PROB_LIMIT
        and logprob < LOW_CONFIDENCE_LOGPROB
    )
    # Looser evidence suffices when the text is also a classic hallucination.
    known_phrase = _is_hallucination_phrase(segment.text) and (
        out_of_bounds or (no_speech is not None and no_speech > PHRASE_NO_SPEECH_PROB)
    )
    if evident_silence or known_phrase:
        found.add(SILENCE_HALLUCINATION)

    if logprob is not None and logprob < LOW_CONFIDENCE_LOGPROB:
        found.add(LOW_CONFIDENCE)
    return tuple(flag for flag in ALL_FLAGS if flag in found)


__all__ = [
    "ALL_FLAGS",
    "LOW_CONFIDENCE",
    "OUT_OF_BOUNDS",
    "REPETITION",
    "SILENCE_HALLUCINATION",
    "quality_flags",
]
