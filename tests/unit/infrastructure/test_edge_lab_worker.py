from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from typing import BinaryIO

import pytest

from voz.application.edge_lab import (
    ExperimentDefinition,
    LabError,
    ResourceProfile,
    definition_payload,
)
from voz.application.ports.speech_synthesis import PcmAudio, SynthesisProviderInfo
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure import edge_lab_worker as worker
from voz.infrastructure.tts.subprocess_provider import TtsModelManifest


def ignore_signal(*_args: object) -> None:
    pass


def fake_host(_engine: str) -> dict[str, object]:
    return {"device": "cpu"}


def test_stt_reuses_real_bench_scoring_with_fake_installed_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from voz.interfaces.cli import bench

    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "manifest.json").write_text(
        json.dumps({"items": [{"audio": "clip.wav", "reference": "hello world"}]})
    )
    with wave.open(str(dataset / "clip.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(bytes(32_000))

    class FakeProvider:
        provider_id = "faster-whisper"
        calls = 0
        closed = False

        def transcribe(
            self,
            *,
            audio: BinaryIO,
            options: TranscriptionOptions,
            cancellation: TranscriptionCancellationToken | None = None,
        ) -> TranscriptionResult:
            self.calls += 1
            return TranscriptionResult(
                (TranscriptionSegment(0, 1000, "hello world"),), "en"
            )

        def close(self) -> None:
            self.closed = True

    provider = FakeProvider()

    def build_provider(*_args: object, **_kwargs: object) -> FakeProvider:
        assert _kwargs["device"] == "cpu" and _kwargs["compute_type"] == "int8"
        return provider

    monkeypatch.setattr(bench, "build_provider", build_provider)

    def no_gpu() -> None:
        raise AssertionError("CPU experiments must not query a GPU")

    monkeypatch.setattr(bench, "read_vram_used_mib", no_gpu)
    definition = ExperimentDefinition(
        "stt", ResourceProfile(), "faster-whisper", "tiny", dataset, tmp_path
    )
    measured, observations = worker.run_stt(definition)
    totals = measured["totals"]
    assert isinstance(totals, dict)
    assert totals["audio_seconds"] == 1.0 and totals["wer"] == totals["cer"] == 0.0
    assert provider.calls == 2 and provider.closed
    assert measured["bench_schema_version"] == 1
    assert observations["precision"] == "int8"
    assert str(tmp_path) not in json.dumps((measured, observations))


def test_tts_renders_every_chunk_with_existing_store_and_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from voz.infrastructure.tts import sherpa_provider
    from voz.infrastructure.tts.catalog import TTS_CATALOG
    from voz.infrastructure.tts.model_store import TtsModelStore

    text = tmp_path / "input.txt"
    text.write_text("Hello world. Hello again.")
    model_file = tmp_path / "fake.onnx"
    model_file.write_bytes(b"fixture")
    manifest = TtsModelManifest(
        "fake", {"model": model_file}, (Voice("0", "Fixture", ("en",)),)
    )

    def get_manifest(_self: TtsModelStore, _model_id: str) -> TtsModelManifest:
        return manifest

    monkeypatch.setattr(TtsModelStore, "manifest", get_manifest)

    class FakeProvider:
        closed = False
        chunks: list[str]

        def __init__(self) -> None:
            self.chunks = []

        def describe(self) -> SynthesisProviderInfo:
            return SynthesisProviderInfo(
                "sherpa-onnx-tts", "Fixture", max_chunk_chars=10
            )

        def synthesize(
            self, chunk: str, *, model: ModelDescriptor, voice_id: str, speed: float
        ) -> PcmAudio:
            assert model.model_id == TTS_CATALOG[0].model_id
            assert voice_id == "0" and speed == 1.0
            self.chunks.append(chunk)
            return PcmAudio(bytes(3200), 16_000)

        def close(self) -> None:
            self.closed = True

    provider = FakeProvider()

    def build_provider(*_args: object, **_kwargs: object) -> FakeProvider:
        assert _kwargs["num_threads"] == 1
        return provider

    monkeypatch.setattr(sherpa_provider, "sherpa_tts_provider", build_provider)
    definition = ExperimentDefinition(
        "tts",
        ResourceProfile(),
        "sherpa-onnx-tts",
        TTS_CATALOG[0].model_id,
        text,
        voice_id="0",
    )
    measured, observations = worker.run_tts(definition)
    assert measured["chunks"] == len(provider.chunks) > 1
    assert measured["frames"] == 1600 * len(provider.chunks)
    duration = measured["output_audio_seconds"]
    assert isinstance(duration, float)
    assert abs(duration - 0.1 * len(provider.chunks)) < 1e-9
    assert provider.closed and all(len(chunk) <= 10 for chunk in provider.chunks)
    assert observations["voice_id"] == "0"
    assert "Hello" not in json.dumps((measured, observations))


def test_limits_precede_work_and_engine_failure_never_becomes_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, ready, result = (
        tmp_path / name for name in ("request.json", "ready.json", "result.json")
    )
    definition = ExperimentDefinition(
        "tts",
        ResourceProfile(),
        "sherpa-onnx-tts",
        "fixture",
        tmp_path / "text",
        voice_id="0",
    )
    request.write_text(json.dumps(definition_payload(definition)))
    order: list[str] = []

    def limits(_profile: ResourceProfile) -> dict[str, object]:
        order.append("limits")
        return {"device": "cpu"}

    def fail(
        _definition: ExperimentDefinition,
    ) -> tuple[dict[str, object], dict[str, object]]:
        assert ready.exists()
        order.append("work")
        raise RuntimeError("private error at " + str(tmp_path))

    monkeypatch.setattr(worker, "apply_limits", limits)
    monkeypatch.setattr(worker, "observe_host", fake_host)
    monkeypatch.setattr(worker, "run_tts", fail)
    monkeypatch.setattr(worker.signal, "signal", ignore_signal)
    monkeypatch.setattr(sys, "argv", ["worker", str(request), str(ready), str(result)])
    assert worker.main() == 1
    assert order == ["limits", "work"]
    assert json.loads(result.read_text()) == {
        "status": "failed",
        "code": "lab_worker_failed",
    }
    assert str(tmp_path) not in result.read_text()


def test_unsupported_control_fails_before_model_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, ready, result = (
        tmp_path / name for name in ("request.json", "ready.json", "result.json")
    )
    definition = ExperimentDefinition(
        "stt",
        ResourceProfile(systemd=True),
        "faster-whisper",
        "tiny",
        tmp_path,
        tmp_path,
    )
    request.write_text(json.dumps(definition_payload(definition)))
    monkeypatch.setattr(worker.signal, "signal", ignore_signal)
    monkeypatch.setattr(sys, "argv", ["worker", str(request), str(ready), str(result)])
    assert worker.main() == 1 and not ready.exists()
    assert json.loads(result.read_text())["code"] == "lab_limit_unsupported"


def test_observations_do_not_load_native_runtimes() -> None:
    before = set(sys.modules)
    observed = worker.observe_host("sherpa-onnx-tts")
    assert observed["device"] == "cpu"
    assert "sherpa_onnx" not in set(sys.modules) - before


def test_worker_rejects_cuda_instead_of_using_cpu() -> None:
    with pytest.raises(LabError) as raised:
        worker.apply_limits(ResourceProfile(device="cuda"))
    assert raised.value.code == "lab_device_unavailable"


def test_tts_worker_delegates_to_benchmark_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from voz.infrastructure import edge_lab_tts

    definition = ExperimentDefinition(
        "tts",
        ResourceProfile(),
        "sherpa-onnx-tts",
        "fixture",
        tmp_path / "text",
        voice_id="0",
    )
    expected: tuple[dict[str, object], dict[str, object]] = (
        {"first_audio_seconds": 0.25, "throughput_audio_seconds_per_second": 4.0},
        {"device": "cpu"},
    )

    def render(
        value: ExperimentDefinition,
    ) -> tuple[dict[str, object], dict[str, object]]:
        assert value is definition
        return expected

    monkeypatch.setattr(edge_lab_tts, "run_tts_benchmark", render)
    assert worker.run_tts(definition) is expected
