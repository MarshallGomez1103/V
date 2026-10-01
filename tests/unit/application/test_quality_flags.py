"""Non-destructive quality heuristics (S13.04, S13.05, S13.12)."""

from __future__ import annotations

import pytest

from voz.application.ports.transcription import TranscriptionSegment
from voz.application.quality_flags import (
    ALL_FLAGS,
    LOW_CONFIDENCE,
    OUT_OF_BOUNDS,
    REPETITION,
    SILENCE_HALLUCINATION,
    quality_flags,
)


def _segment(
    text: str,
    *,
    end_ms: int = 1_000,
    avg_logprob: float | None = None,
    no_speech_prob: float | None = None,
    compression_ratio: float | None = None,
    exceeds_audio: bool = False,
) -> TranscriptionSegment:
    return TranscriptionSegment(
        0,
        end_ms,
        text,
        avg_logprob=avg_logprob,
        no_speech_prob=no_speech_prob,
        compression_ratio=compression_ratio,
        exceeds_audio=exceeds_audio,
    )


def test_real_thank_you_over_a_tone_is_hallucination_and_out_of_bounds() -> None:
    # Observed: Whisper over a voiceless tone returned " Thank you." ending at
    # 29.98 s for a 0.25 s clip.
    segment = _segment(" Thank you.", end_ms=29_980)

    assert quality_flags(segment, audio_duration_ms=250) == (
        SILENCE_HALLUCINATION,
        OUT_OF_BOUNDS,
    )


def test_hallucination_phrase_needs_evidence_beyond_the_text() -> None:
    # A real "Gracias." with no engine data and inside the audio is not flagged.
    assert quality_flags(_segment("Gracias."), audio_duration_ms=2_000) == ()
    assert quality_flags(_segment("Gracias."), audio_duration_ms=None) == ()
    # Accents and punctuation do not hide the known phrase once evidence exists.
    assert quality_flags(
        _segment("¡Suscríbete!", no_speech_prob=0.5), audio_duration_ms=2_000
    ) == (SILENCE_HALLUCINATION,)


def test_no_speech_with_poor_logprob_is_hallucination_and_low_confidence() -> None:
    segment = _segment("texto cualquiera", no_speech_prob=0.9, avg_logprob=-1.4)

    assert quality_flags(segment) == (SILENCE_HALLUCINATION, LOW_CONFIDENCE)
    # Confident speech decoded with a high no_speech_prob is left alone.
    assert quality_flags(_segment("hola", no_speech_prob=0.9, avg_logprob=-0.2)) == ()


@pytest.mark.parametrize(
    ("logprob", "expected"),
    [(-1.0, ()), (-1.01, (LOW_CONFIDENCE,)), (-0.3, ()), (None, ())],
)
def test_low_confidence_threshold_is_strictly_below_minus_one(
    logprob: float | None, expected: tuple[str, ...]
) -> None:
    assert quality_flags(_segment("hola", avg_logprob=logprob)) == expected


@pytest.mark.parametrize(
    "text",
    [
        "no no no no no no",  # one word, many times
        "y entonces y entonces y entonces y entonces",  # a phrase
        "Sí, sí, sí, sí, sí.",  # punctuation does not break the run
    ],
)
def test_repeated_ngrams_are_flagged(text: str) -> None:
    assert quality_flags(_segment(text)) == (REPETITION,)


@pytest.mark.parametrize(
    "text",
    [
        "no no no hay problema",  # a short stutter is real speech
        "uno dos tres cuatro cinco seis",
        "ja ja ja",
    ],
)
def test_ordinary_text_is_not_a_repetition(text: str) -> None:
    assert quality_flags(_segment(text)) == ()


def test_compression_ratio_over_the_limit_flags_repetition() -> None:
    assert quality_flags(_segment("texto", compression_ratio=2.5)) == (REPETITION,)
    assert quality_flags(_segment("texto", compression_ratio=2.4)) == ()


def test_out_of_bounds_has_a_rounding_tolerance_and_honors_the_engine_marker() -> None:
    assert quality_flags(_segment("hola", end_ms=1_400), audio_duration_ms=1_000) == ()
    assert quality_flags(_segment("hola", end_ms=1_600), audio_duration_ms=1_000) == (
        OUT_OF_BOUNDS,
    )
    assert quality_flags(_segment("hola", exceeds_audio=True)) == (OUT_OF_BOUNDS,)


def test_flags_come_in_stable_order_and_text_is_never_touched() -> None:
    segment = _segment(
        "no no no no no no",
        end_ms=40_000,
        avg_logprob=-2.0,
        no_speech_prob=0.8,
        compression_ratio=3.0,
    )

    flags = quality_flags(segment, audio_duration_ms=500)

    assert flags == ALL_FLAGS
    assert segment.text == "no no no no no no"
