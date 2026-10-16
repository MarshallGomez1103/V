from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from voz.application.edge_lab import ExperimentDefinition, LabError, ResourceProfile
from voz.application.ports.speech_synthesis import (
    PcmAudio,
    PcmSampleFormat,
    SynthesisProviderInfo,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure import edge_lab_tts as benchmark
from voz.infrastructure.tts import sherpa_provider
from voz.infrastructure.tts.catalog import TTS_CATALOG
from voz.infrastructure.tts.model_store import TtsModelStore
from voz.infrastructure.tts.subprocess_provider import TtsModelManifest


class FakeProvider:
    def __init__(self, sample_format: PcmSampleFormat = PcmSampleFormat.INT16) -> None:
        self.closed = False
        self.calls: list[str] = []
        self.failure: Exception | None = None
        self.empty = False
        self.mixed_rates = False
        self.sample_format = sample_format
        self.on_describe: Callable[[], None] | None = None

    def describe(self) -> SynthesisProviderInfo:
        if self.on_describe is not None:
            self.on_describe()
        return SynthesisProviderInfo("sherpa-onnx-tts", "Fixture", max_chunk_chars=10)

    def synthesize(
        self, chunk: str, *, model: ModelDescriptor, voice_id: str, speed: float
    ) -> PcmAudio:
        assert model.model_id == TTS_CATALOG[0].model_id
        assert voice_id == "0" and speed == 1.0
        self.calls.append(chunk)
        if self.failure is not None:
            raise self.failure
        rate = 8000 if self.mixed_rates and len(self.calls) > 1 else 16_000
        audio = PcmAudio(
            bytes(64_000 * self.sample_format.width), rate, self.sample_format
        )
        if self.empty:
            # Simulate a broken provider bypassing the PCM constructor's invariant.
            object.__setattr__(audio, "samples", b"")
        return audio

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ExperimentDefinition, FakeProvider]:
    path = tmp_path / "input.txt"
    path.write_text("Hello. Again.", encoding="utf-8")
    fake_file = tmp_path / "fixture.onnx"
    fake_file.write_bytes(b"fixture")
    manifest = TtsModelManifest(
        "fake", {"model": fake_file}, (Voice("0", "Fixture", ("en",)),)
    )
    provider = FakeProvider()

    def get_manifest(_self: TtsModelStore, _model_id: str) -> TtsModelManifest:
        return manifest

    def create_provider(*_args: object, **options: object) -> FakeProvider:
        assert options["num_threads"] == 1
        assert options["timeout_seconds"] == 120.0
        return provider

    def rss(*, children: bool = False) -> tuple[float | None, str | None]:
        return (50.0 if children else 23.0), None

    monkeypatch.setattr(TtsModelStore, "manifest", get_manifest)
    monkeypatch.setattr(sherpa_provider, "sherpa_tts_provider", create_provider)
    monkeypatch.setattr(benchmark, "peak_rss_observation", rss)
    definition = ExperimentDefinition(
        "tts",
        ResourceProfile(),
        "sherpa-onnx-tts",
        TTS_CATALOG[0].model_id,
        path,
        voice_id="0",
    )
    return definition, provider


def clock(ticks: tuple[float, ...] = (0.0, 0.25, 2.0)) -> Callable[[], float]:
    values: Iterator[float] = iter(ticks)
    return lambda: next(values)


@pytest.mark.parametrize(
    "sample_format", [PcmSampleFormat.INT16, PcmSampleFormat.FLOAT32]
)
def test_first_completed_chunk_and_frame_based_throughput(
    harness: tuple[ExperimentDefinition, FakeProvider],
    sample_format: PcmSampleFormat,
) -> None:
    definition, provider = harness
    provider.sample_format = sample_format
    measured, observations = benchmark.run_tts_benchmark(definition, clock=clock())
    assert provider.calls == ["Hello.", "Again."] and provider.closed
    assert measured["first_audio_seconds"] == 0.25
    assert measured["wall_seconds"] == 2.0
    assert measured["output_audio_seconds"] == 8.0
    assert measured["throughput_audio_seconds_per_second"] == 4.0
    assert measured["frames"] == 128_000 and measured["sample_rate"] == 16_000
    assert measured["chunks"] == 2 and measured["input_characters"] == 13
    assert measured["memory"] == {
        "worker_peak_rss_mib": 23.0,
        "largest_child_peak_rss_mib": 50.0,
    }
    methods = measured["methods"]
    assert isinstance(methods, dict)
    assert (
        methods["first_audio"] == "first completed chunk returned; not sample streaming"
    )
    assert observations["voice_id"] == "0" and observations["threads"] == 1
    assert str(definition.input_path) not in json.dumps((measured, observations))
    assert "Hello" not in json.dumps((measured, observations))


def test_end_clock_includes_provider_close(
    harness: tuple[ExperimentDefinition, FakeProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, provider = harness
    times = iter((0.0, 0.25, 2.0))

    def observed_clock() -> float:
        value = next(times)
        if value == 2.0:
            assert provider.closed
        return value

    measured, _ = benchmark.run_tts_benchmark(definition, clock=observed_clock)
    assert measured["wall_seconds"] == 2.0


@pytest.mark.parametrize(
    "failure",
    [
        LabError("lab_cancelled"),
        LabError("lab_timeout"),
        RuntimeError("private native failure"),
    ],
)
def test_failed_and_interrupted_render_closes_provider(
    harness: tuple[ExperimentDefinition, FakeProvider],
    failure: Exception,
) -> None:
    definition, provider = harness
    provider.failure = failure
    with pytest.raises(LabError) as raised:
        benchmark.run_tts_benchmark(definition, clock=clock())
    assert provider.closed
    assert raised.value.code == (
        failure.code if isinstance(failure, LabError) else "lab_worker_failed"
    )
    assert "private native" not in str(raised.value)


@pytest.mark.parametrize("fault", ["empty", "mixed_rates", "bad_clock", "describe"])
def test_invalid_pcm_timing_or_setup_cannot_report_success(
    harness: tuple[ExperimentDefinition, FakeProvider],
    fault: str,
) -> None:
    definition, provider = harness
    provider.empty = fault == "empty"
    provider.mixed_rates = fault == "mixed_rates"
    if fault == "describe":

        def fail() -> None:
            raise RuntimeError("private setup failure")

        provider.on_describe = fail
    with pytest.raises(LabError) as raised:
        benchmark.run_tts_benchmark(
            definition,
            clock=clock((0.0, 0.25, 0.0) if fault == "bad_clock" else (0.0, 0.25, 2.0)),
        )
    assert raised.value.code == "lab_worker_failed" and provider.closed


def test_missing_rss_is_null_with_a_reason(
    harness: tuple[ExperimentDefinition, FakeProvider], monkeypatch: pytest.MonkeyPatch
) -> None:
    definition, _ = harness

    def unavailable(*, children: bool = False) -> tuple[float | None, str | None]:
        return None, "read_failed" if children else "unsupported_platform"

    monkeypatch.setattr(benchmark, "peak_rss_observation", unavailable)
    measured, _ = benchmark.run_tts_benchmark(definition, clock=clock())
    assert measured["memory"] == {
        "worker_peak_rss_mib": None,
        "largest_child_peak_rss_mib": None,
        "unavailable_reasons": {
            "worker_peak_rss_mib": "unsupported_platform",
            "largest_child_peak_rss_mib": "read_failed",
        },
    }


def test_non_tts_definition_is_rejected_before_provider(
    harness: tuple[ExperimentDefinition, FakeProvider],
) -> None:
    definition, provider = harness
    with pytest.raises(LabError) as raised:
        benchmark.run_tts_benchmark(replace(definition, workload="stt"), clock=clock())
    assert raised.value.code == "lab_invalid_definition" and not provider.calls


@pytest.mark.parametrize("platform,expected", [("linux", 2.0), ("darwin", 2.0 / 1024)])
def test_rss_uses_platform_units_and_separate_accounting(
    monkeypatch: pytest.MonkeyPatch, platform: str, expected: float
) -> None:
    resource = pytest.importorskip("resource")
    seen: list[int] = []

    def usage(who: int) -> SimpleNamespace:
        seen.append(who)
        return SimpleNamespace(ru_maxrss=2048.0)

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(resource, "getrusage", usage)
    assert benchmark.peak_rss_observation() == (expected, None)
    assert benchmark.peak_rss_observation(children=True) == (expected, None)
    assert seen == [resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN]


@pytest.mark.parametrize("peak", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_rss_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, peak: float
) -> None:
    resource = pytest.importorskip("resource")

    def usage(_who: int) -> SimpleNamespace:
        return SimpleNamespace(ru_maxrss=peak)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(resource, "getrusage", usage)
    assert benchmark.peak_rss_observation() == (None, "no_valid_observation")


def test_rss_failure_and_unsupported_platform_are_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = pytest.importorskip("resource")

    def failed(_who: int) -> SimpleNamespace:
        raise OSError("private host details")

    monkeypatch.setattr(resource, "getrusage", failed)
    monkeypatch.setattr(sys, "platform", "linux")
    assert benchmark.peak_rss_observation() == (None, "read_failed")
    monkeypatch.setattr(sys, "platform", "win32")
    assert benchmark.peak_rss_observation(children=True) == (
        None,
        "unsupported_platform",
    )
