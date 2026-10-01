"""Word timing invariants of the transcription port and the chunk pipeline (S7)."""

from __future__ import annotations

from contextlib import AbstractContextManager
from io import BytesIO
from itertools import pairwise
from typing import BinaryIO

import pytest

from voz.application.chunked_transcription import (
    AudioChunk,
    ChunkedTranscription,
    globalize_chunk_result,
    owned_chunk_segments,
)
from voz.application.ports.alignment import AlignmentProvider
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
    clamp_words,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor

DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


def _word(start_ms: int, end_ms: int, text: str = " a") -> TranscriptionWord:
    return TranscriptionWord(start_ms, end_ms, text)


def test_word_rejects_negative_reversed_empty_and_bad_probability() -> None:
    with pytest.raises(ValueError):
        _word(-1, 5)
    with pytest.raises(ValueError):
        _word(10, 5)
    with pytest.raises(ValueError):
        TranscriptionWord(0, 5, "")
    with pytest.raises(ValueError):
        TranscriptionWord(0, 5, "a", probability=1.5)
    with pytest.raises(ValueError):
        TranscriptionWord(0, 5, "a", probability=float("nan"))
    with pytest.raises(TypeError):
        TranscriptionWord(0.5, 5, "a")  # type: ignore[arg-type]


def test_segment_words_default_to_empty_and_must_be_ordered_inside() -> None:
    assert TranscriptionSegment(0, 100, "hola").words == ()
    ok = TranscriptionSegment(0, 100, "hola", words=(_word(0, 40), _word(40, 100)))
    assert len(ok.words) == 2
    with pytest.raises(ValueError):  # overlaps the previous word
        TranscriptionSegment(0, 100, "hola", words=(_word(0, 60), _word(50, 100)))
    with pytest.raises(ValueError):  # leaves the segment
        TranscriptionSegment(0, 100, "hola", words=(_word(0, 120),))
    with pytest.raises(TypeError):
        TranscriptionSegment(0, 100, "hola", words=[_word(0, 10)])  # type: ignore[arg-type]


def test_options_request_word_timestamps_by_default_and_validate_the_flag() -> None:
    assert TranscriptionOptions(model=DESCRIPTOR).word_timestamps is True
    assert TranscriptionOptions(model=DESCRIPTOR, word_timestamps=False)
    with pytest.raises(TypeError):
        TranscriptionOptions(model=DESCRIPTOR, word_timestamps=1)  # type: ignore[arg-type]


def test_clamp_words_is_monotonic_non_negative_and_inside_the_bounds() -> None:
    clamped = clamp_words(
        (
            _word(80, 120, " before"),  # starts before the segment: clipped
            _word(110, 130, " overlaps"),  # starts inside the previous word
            _word(130, 130, " empty"),  # zero duration: dropped
            _word(140, 160, " ok"),
            _word(190, 260, " after"),  # ends past the segment: clipped
            _word(250, 260, " outside"),  # entirely outside: dropped
        ),
        100,
        200,
    )

    assert [(w.start_ms, w.end_ms, w.text) for w in clamped] == [
        (100, 120, " before"),
        (120, 130, " overlaps"),
        (140, 160, " ok"),
        (190, 200, " after"),
    ]
    assert all(w.start_ms >= 100 and w.end_ms <= 200 for w in clamped)
    assert all(a.end_ms <= b.start_ms for a, b in pairwise(clamped))
    assert clamp_words((), 0, 10) == ()


def test_globalize_shifts_words_with_their_segment() -> None:
    chunk = AudioChunk(1, 25_000, 65_000, 30_000, 60_000)
    result = globalize_chunk_result(
        chunk,
        TranscriptionResult(
            (TranscriptionSegment(5_000, 6_000, "x", words=(_word(5_000, 5_500),)),),
            "es",
        ),
    )

    (segment,) = result.segments
    assert (segment.start_ms, segment.end_ms) == (30_000, 31_000)
    assert [(w.start_ms, w.end_ms) for w in segment.words] == [(30_000, 30_500)]


def test_overlap_region_words_follow_the_owning_chunk_without_duplicates() -> None:
    first = AudioChunk(0, 0, 35_000, 0, 30_000)
    second = AudioChunk(1, 25_000, 65_000, 30_000, 60_000)
    # The same sentence heard by both chunks inside the shared 25-35 s overlap.
    in_first = TranscriptionSegment(
        27_000, 33_000, "s", words=(_word(27_000, 30_000), _word(30_000, 33_000))
    )
    in_second = TranscriptionSegment(
        27_000, 33_000, "s", words=(_word(27_000, 30_000), _word(30_000, 33_000))
    )

    kept_first = owned_chunk_segments(first, (in_first,))
    kept_second = owned_chunk_segments(second, (in_second,))

    # Midpoint 30_000 belongs to the second chunk only; first keeps nothing.
    assert kept_first == ()
    assert [(s.start_ms, s.end_ms) for s in kept_second] == [(30_000, 33_000)]
    # Clamped to the owned region: the word straddling the boundary is cut.
    assert [(w.start_ms, w.end_ms) for w in kept_second[0].words] == [(30_000, 33_000)]


def test_owned_segment_clamps_words_to_the_owned_region() -> None:
    chunk = AudioChunk(0, 0, 35_000, 0, 30_000)
    segment = TranscriptionSegment(
        28_000,
        31_000,
        "s",
        words=(_word(28_000, 29_000), _word(29_000, 30_500), _word(30_500, 31_000)),
    )

    (kept,) = owned_chunk_segments(chunk, (segment,))

    assert (kept.start_ms, kept.end_ms) == (28_000, 30_000)
    assert [(w.start_ms, w.end_ms) for w in kept.words] == [
        (28_000, 29_000),
        (29_000, 30_000),
    ]


class _AudioContext(AbstractContextManager[BinaryIO]):
    def __init__(self, clip: TranscriptionClip) -> None:
        self.audio = BytesIO(f"{clip.start_ms}:{clip.end_ms}".encode())

    def __enter__(self) -> BinaryIO:
        return self.audio

    def __exit__(self, *args: object) -> None:
        self.audio.close()


class _Source:
    def open(self, clip: TranscriptionClip | None = None) -> _AudioContext:
        assert clip is not None
        return _AudioContext(clip)


class _WordProvider:
    provider_id = "fake-asr"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del cancellation
        start_ms, end_ms = (int(v) for v in audio.read().decode().split(":"))
        length = end_ms - start_ms
        # One segment per chunk in chunk-local time, two words inside.
        return TranscriptionResult(
            (
                TranscriptionSegment(
                    0,
                    length,
                    "t",
                    words=(_word(0, length // 2), _word(length // 2, length)),
                ),
            ),
            "es",
        )


def test_chunked_pipeline_yields_monotonic_global_words_without_duplicates() -> None:
    result = ChunkedTranscription(_WordProvider(), _Source()).execute(
        duration_ms=65_000,
        options=TranscriptionOptions(model=DESCRIPTOR),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    words = [word for segment in result.segments for word in segment.words]
    assert words  # words clipped out of an owned region are dropped, text is kept
    assert all(w.start_ms >= 0 and w.start_ms < w.end_ms for w in words)
    assert all(a.end_ms <= b.start_ms for a, b in pairwise(words))
    for segment in result.segments:
        assert all(
            segment.start_ms <= w.start_ms and w.end_ms <= segment.end_ms
            for w in segment.words
        )


def test_alignment_port_is_structural_and_has_no_implementation() -> None:
    class Aligner:
        provider_id = "fake-aligner"

        def align(
            self,
            *,
            audio: BinaryIO,
            segments: tuple[TranscriptionSegment, ...],
            language: str | None = None,
            cancellation: TranscriptionCancellationToken | None = None,
        ) -> tuple[tuple[TranscriptionWord, ...], ...]:
            return tuple(() for _ in segments)

    assert isinstance(Aligner(), AlignmentProvider)
    assert not isinstance(object(), AlignmentProvider)


def test_provider_speaker_label_survives_globalization_and_ownership() -> None:
    chunk = AudioChunk(1, 25_000, 65_000, 30_000, 60_000)
    local = TranscriptionResult(
        (TranscriptionSegment(10_000, 12_000, " hola", speaker="A"),), "es"
    )
    (globalized,) = globalize_chunk_result(chunk, local).segments
    (kept,) = owned_chunk_segments(chunk, (globalized,))
    assert (kept.start_ms, kept.speaker) == (35_000, "A")


def test_quality_metrics_survive_globalization_and_ownership() -> None:
    chunk = AudioChunk(1, 25_000, 65_000, 30_000, 60_000)
    local = TranscriptionResult(
        (
            TranscriptionSegment(
                5_000,
                6_000,
                "x",
                avg_logprob=-1.3,
                no_speech_prob=0.7,
                compression_ratio=2.9,
            ),
            # Reaches past the 40 s of audio the chunk was given.
            TranscriptionSegment(10_000, 50_000, "Thank you.", avg_logprob=-0.2),
        ),
        "es",
    )

    first, overrun = globalize_chunk_result(chunk, local).segments
    (kept,) = owned_chunk_segments(chunk, (first,))

    assert (kept.avg_logprob, kept.no_speech_prob, kept.compression_ratio) == (
        -1.3,
        0.7,
        2.9,
    )
    assert not kept.exceeds_audio
    assert overrun.exceeds_audio
    assert owned_chunk_segments(chunk, (overrun,))[0].exceeds_audio
