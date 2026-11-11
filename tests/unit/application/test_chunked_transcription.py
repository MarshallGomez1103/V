"""Tests for deterministic chunk planning, offsets and progress."""

from __future__ import annotations

from contextlib import AbstractContextManager
from io import BytesIO
from itertools import pairwise
from typing import BinaryIO

import pytest

from voz.application.chunked_transcription import (
    AudioChunk,
    ChunkedTranscription,
    plan_audio_chunks,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor

DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


class _AudioContext(AbstractContextManager[BinaryIO]):
    def __init__(self, clip: TranscriptionClip) -> None:
        self.audio = BytesIO(f"{clip.start_ms}:{clip.end_ms}".encode())

    def __enter__(self) -> BinaryIO:
        return self.audio

    def __exit__(self, *args: object) -> None:
        self.audio.close()


class _AudioSource:
    def __init__(self) -> None:
        self.open_count = 0
        self.clips: list[tuple[int, int]] = []

    def open(
        self,
        clip: TranscriptionClip | None = None,
    ) -> AbstractContextManager[BinaryIO]:
        assert clip is not None
        self.open_count += 1
        self.clips.append((clip.start_ms, clip.end_ms))
        return _AudioContext(clip)


class _Provider:
    provider_id = "fake-asr"

    def __init__(self) -> None:
        self.clips: list[tuple[int, int]] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del cancellation
        start_ms, end_ms = (int(value) for value in audio.read().decode().split(":"))
        assert options.clip is None
        self.clips.append((start_ms, end_ms))
        return TranscriptionResult(
            segments=(
                TranscriptionSegment(
                    start_ms=0,
                    end_ms=end_ms - start_ms,
                    text=f"chunk-{len(self.clips)}",
                ),
            ),
            language="es",
        )


def test_plan_uses_overlap_but_owns_timeline_exactly_once() -> None:
    chunks = plan_audio_chunks(
        65_000,
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    assert [
        (
            item.index,
            item.process_start_ms,
            item.process_end_ms,
            item.owned_start_ms,
            item.owned_end_ms,
        )
        for item in chunks
    ] == [
        (0, 0, 35_000, 0, 30_000),
        (1, 25_000, 65_000, 30_000, 60_000),
        (2, 55_000, 65_000, 60_000, 65_000),
    ]


def test_short_audio_produces_one_chunk_without_artificial_offsets() -> None:
    chunks = plan_audio_chunks(10_000)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert (chunk.process_start_ms, chunk.process_end_ms) == (0, 10_000)
    assert (chunk.owned_start_ms, chunk.owned_end_ms) == (0, 10_000)


def test_chunked_transcription_reports_monotonic_progress_and_global_offsets() -> None:
    source = _AudioSource()
    provider = _Provider()
    fractions: list[float] = []
    result = ChunkedTranscription(provider, source).execute(
        duration_ms=65_000,
        options=TranscriptionOptions(model=DESCRIPTOR),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
        on_progress=lambda progress: fractions.append(progress.fraction),
    )

    assert provider.clips == [(0, 35_000), (25_000, 65_000), (55_000, 65_000)]
    assert source.open_count == 3
    assert source.clips == provider.clips
    assert fractions == [1 / 3, 2 / 3, 1.0]
    assert [(item.start_ms, item.end_ms) for item in result.segments] == [
        (0, 30_000),
        (30_000, 60_000),
        (60_000, 65_000),
    ]
    assert result.language == "es"


@pytest.mark.parametrize(
    ("duration_ms", "chunk_duration_ms", "overlap_ms"),
    [(0, 30_000, 5_000), (1, 0, 0), (1, 10, 10), (1, 10, -1)],
)
def test_plan_rejects_invalid_bounds(
    duration_ms: int,
    chunk_duration_ms: int,
    overlap_ms: int,
) -> None:
    with pytest.raises(ValueError):
        plan_audio_chunks(
            duration_ms,
            chunk_duration_ms=chunk_duration_ms,
            overlap_ms=overlap_ms,
        )


def test_plan_without_clip_is_unchanged() -> None:
    expected = [
        (0, 0, 35_000, 0, 30_000),
        (1, 25_000, 65_000, 30_000, 60_000),
        (2, 55_000, 65_000, 60_000, 65_000),
    ]
    for chunks in (
        plan_audio_chunks(65_000, chunk_duration_ms=30_000, overlap_ms=5_000),
        plan_audio_chunks(
            65_000, clip=None, chunk_duration_ms=30_000, overlap_ms=5_000
        ),
    ):
        assert [
            (
                item.index,
                item.process_start_ms,
                item.process_end_ms,
                item.owned_start_ms,
                item.owned_end_ms,
            )
            for item in chunks
        ] == expected


def test_plan_with_clip_never_leaves_the_clip() -> None:
    clip = TranscriptionClip(600_000, 1_900_000)

    chunks = plan_audio_chunks(
        3_600_000, clip=clip, chunk_duration_ms=600_000, overlap_ms=5_000
    )

    assert [
        (
            item.process_start_ms,
            item.process_end_ms,
            item.owned_start_ms,
            item.owned_end_ms,
        )
        for item in chunks
    ] == [
        (600_000, 1_205_000, 600_000, 1_200_000),
        (1_195_000, 1_805_000, 1_200_000, 1_800_000),
        (1_795_000, 1_900_000, 1_800_000, 1_900_000),
    ]
    assert [item.index for item in chunks] == [0, 1, 2]
    for item in chunks:
        assert clip.start_ms <= item.process_start_ms
        assert item.process_end_ms <= clip.end_ms
    # Ownership covers the clip once: no gaps, no overlaps.
    assert chunks[0].owned_start_ms == clip.start_ms
    assert chunks[-1].owned_end_ms == clip.end_ms
    for before, after in pairwise(chunks):
        assert before.owned_end_ms == after.owned_start_ms


def test_plan_with_a_clip_shorter_than_one_chunk_has_one_chunk() -> None:
    chunks = plan_audio_chunks(
        60_000, clip=TranscriptionClip(10_000, 20_000), overlap_ms=5_000
    )

    assert [
        (item.process_start_ms, item.process_end_ms, item.owned_end_ms)
        for item in chunks
    ] == [(10_000, 20_000, 20_000)]


def test_plan_rejects_a_clip_beyond_the_duration() -> None:
    with pytest.raises(ValueError):
        plan_audio_chunks(10_000, clip=TranscriptionClip(5_000, 10_001))


def _bounds(chunks: tuple[AudioChunk, ...]) -> list[tuple[int, int, int, int]]:
    return [
        (c.process_start_ms, c.process_end_ms, c.owned_start_ms, c.owned_end_ms)
        for c in chunks
    ]


def test_one_second_clip_at_the_start_is_a_single_chunk() -> None:
    chunks = plan_audio_chunks(
        60_000, clip=TranscriptionClip(0, 1_000), overlap_ms=5_000
    )

    assert _bounds(chunks) == [(0, 1_000, 0, 1_000)]


def test_clip_reaching_the_duration_ends_exactly_there() -> None:
    chunks = plan_audio_chunks(
        65_000,
        clip=TranscriptionClip(30_000, 65_000),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    assert _bounds(chunks) == [
        (30_000, 65_000, 30_000, 60_000),
        (55_000, 65_000, 60_000, 65_000),
    ]


def test_overlap_larger_than_the_clip_never_leaves_it() -> None:
    chunks = plan_audio_chunks(
        60_000,
        clip=TranscriptionClip(10_000, 12_000),
        chunk_duration_ms=30_000,
        overlap_ms=5_000,
    )

    assert _bounds(chunks) == [(10_000, 12_000, 10_000, 12_000)]
