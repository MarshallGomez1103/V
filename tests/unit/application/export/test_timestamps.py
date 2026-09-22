"""Boundary tests for the pure subtitle timestamp formatters."""

import pytest

from voz.application.export.timestamps import (
    format_srt_timestamp,
    format_vtt_timestamp,
)


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "00:00:00,000"),
        (999, "00:00:00,999"),
        (1000, "00:00:01,000"),
        (3599999, "00:59:59,999"),
        (3600000, "01:00:00,000"),
        (86400000, "24:00:00,000"),
        (360000000, "100:00:00,000"),
    ],
)
def test_srt_timestamp_boundaries(ms: int, expected: str) -> None:
    assert format_srt_timestamp(ms) == expected


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "00:00:00.000"),
        (999, "00:00:00.999"),
        (3599999, "00:59:59.999"),
        (90061001, "25:01:01.001"),
    ],
)
def test_vtt_timestamp_boundaries(ms: int, expected: str) -> None:
    assert format_vtt_timestamp(ms) == expected


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_rejects_non_integer_or_negative(value: object) -> None:
    with pytest.raises(ValueError):
        format_srt_timestamp(value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        format_vtt_timestamp(value)  # type: ignore[arg-type]
