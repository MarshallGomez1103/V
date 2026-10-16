from __future__ import annotations

import ast
from pathlib import Path

import pytest

from voz.application.tts_benchmark_metrics import calculate_tts_metrics


def test_known_first_chunk_and_throughput() -> None:
    metrics = calculate_tts_metrics(
        frames=128_000,
        sample_rate=16_000,
        first_audio_seconds=0.25,
        wall_seconds=2.0,
    )
    assert metrics == {
        "output_audio_seconds": 8.0,
        "wall_seconds": 2.0,
        "first_audio_seconds": 0.25,
        "throughput_audio_seconds_per_second": 4.0,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("frames", 0),
        ("frames", -1),
        ("frames", True),
        ("sample_rate", 0),
        ("sample_rate", -1),
        ("sample_rate", True),
        ("wall_seconds", 0.0),
        ("wall_seconds", -1.0),
        ("wall_seconds", float("nan")),
        ("wall_seconds", float("inf")),
        ("wall_seconds", True),
        ("first_audio_seconds", -1.0),
        ("first_audio_seconds", float("nan")),
        ("first_audio_seconds", float("inf")),
        ("first_audio_seconds", 3.0),
        ("first_audio_seconds", True),
    ],
)
def test_invalid_observations_cannot_produce_metrics(field: str, value: object) -> None:
    values: dict[str, object] = {
        "frames": 128_000,
        "sample_rate": 16_000,
        "first_audio_seconds": 0.25,
        "wall_seconds": 2.0,
    }
    values[field] = value
    with pytest.raises(ValueError):
        calculate_tts_metrics(**values)  # type: ignore[arg-type]


def test_zero_first_return_is_valid_when_the_clock_observes_it() -> None:
    metrics = calculate_tts_metrics(
        frames=16_000,
        sample_rate=16_000,
        first_audio_seconds=0.0,
        wall_seconds=1.0,
    )
    assert metrics["first_audio_seconds"] == 0.0


def test_metrics_module_has_only_standard_library_dependencies() -> None:
    source = Path(__file__).parents[3] / "src/voz/application/tts_benchmark_metrics.py"
    imports = [
        node
        for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    for node in imports:
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        assert all(name.split(".")[0] in {"__future__", "math"} for name in names)
