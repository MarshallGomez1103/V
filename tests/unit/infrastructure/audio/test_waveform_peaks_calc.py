"""Pure bucket math for waveform peaks (no FFmpeg, no filesystem)."""

from __future__ import annotations

import math
from array import array

import pytest

from voz.infrastructure.audio.waveform_peaks import (
    PeakAccumulator,
    duration_ms_from_samples,
    normalize_peaks,
)


def _feed_in_chunks(
    accumulator: PeakAccumulator, samples: array[int], size: int
) -> None:
    for start in range(0, len(samples), size):
        accumulator.feed(samples[start : start + size])


def test_returns_exactly_the_requested_number_of_buckets() -> None:
    accumulator = PeakAccumulator(100)
    accumulator.feed(array("h", range(-500, 500)))

    assert len(accumulator.finish()) == 100


def test_short_audio_repeats_blocks_instead_of_returning_fewer_buckets() -> None:
    accumulator = PeakAccumulator(100)
    accumulator.feed(array("h", [-10, 20, -30, 40]))

    result = accumulator.finish()

    assert len(result) == 100
    assert set(result) == {(-30, 40)}


def test_no_samples_yields_no_peaks() -> None:
    assert PeakAccumulator(100).finish() == []


def test_global_extremes_survive_merging() -> None:
    samples = array("h", [0] * 200_000)
    samples[123_456] = 32_000
    samples[7] = -32_768
    accumulator = PeakAccumulator(100)
    accumulator.feed(samples)

    result = accumulator.finish()

    assert min(low for low, _ in result) == -32_768
    assert max(high for _, high in result) == 32_000
    assert all(low <= 0 <= high for low, high in result)


def test_result_is_independent_of_chunking() -> None:
    samples = array("h", (int(20_000 * math.sin(i / 37)) for i in range(150_001)))
    whole = PeakAccumulator(250)
    whole.feed(samples)
    odd = PeakAccumulator(250)
    _feed_in_chunks(odd, samples, 977)
    tiny = PeakAccumulator(250)
    _feed_in_chunks(tiny, samples, 1)

    assert odd.finish() == whole.finish() == tiny.finish()
    assert odd.total_samples == tiny.total_samples == 150_001


def test_memory_is_bounded_by_the_bucket_count() -> None:
    accumulator = PeakAccumulator(100)
    for _ in range(40):
        accumulator.feed(array("h", [1, -1] * 50_000))

    assert accumulator.block_count <= 200
    assert accumulator.total_samples == 4_000_000


def test_peaks_follow_time_order() -> None:
    quiet = array("h", [10] * 64_000)
    loud = array("h", [30_000] * 64_000)
    accumulator = PeakAccumulator(100)
    accumulator.feed(quiet + loud)

    result = accumulator.finish()

    assert result[10][1] == 10
    assert result[90][1] == 30_000


def test_invalid_bucket_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        PeakAccumulator(0)


def test_normalize_scales_loudest_sample_to_one_with_three_decimals() -> None:
    result = normalize_peaks([(-16_384, 8_192), (-32_768, 100)])

    assert result[0] == (-0.5, 0.25)
    assert result[1] == (-1.0, 0.003)
    assert all(-1.0 <= value <= 1.0 for pair in result for value in pair)


def test_normalize_silence_stays_zero() -> None:
    assert normalize_peaks([(0, 0), (0, 0)]) == ((0.0, 0.0), (0.0, 0.0))


def test_duration_from_sample_count() -> None:
    assert duration_ms_from_samples(8_000) == 1_000
    assert duration_ms_from_samples(2_000) == 250
