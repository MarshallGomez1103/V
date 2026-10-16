"""Pure measurements for completed TTS renders; no hardware estimates."""

from __future__ import annotations

import math


def calculate_tts_metrics(
    *,
    frames: int,
    sample_rate: int,
    first_audio_seconds: float,
    wall_seconds: float,
) -> dict[str, float]:
    """First audio means the first completed chunk returned to the caller."""
    if (
        type(frames) is not int
        or frames <= 0
        or type(sample_rate) is not int
        or sample_rate <= 0
        or type(first_audio_seconds) not in (int, float)
        or type(wall_seconds) not in (int, float)
    ):
        raise ValueError("Invalid TTS benchmark observations.")
    try:
        duration = frames / sample_rate
        if (
            not all(
                math.isfinite(value)
                for value in (duration, first_audio_seconds, wall_seconds)
            )
            or wall_seconds <= 0
            or not 0 <= first_audio_seconds <= wall_seconds
        ):
            raise ValueError("Invalid TTS benchmark observations.")
        throughput = duration / wall_seconds
        if not math.isfinite(throughput):
            raise ValueError("Invalid TTS benchmark observations.")
    except OverflowError as error:
        raise ValueError("Invalid TTS benchmark observations.") from error
    return {
        "output_audio_seconds": duration,
        "wall_seconds": float(wall_seconds),
        "first_audio_seconds": float(first_audio_seconds),
        "throughput_audio_seconds_per_second": throughput,
    }
