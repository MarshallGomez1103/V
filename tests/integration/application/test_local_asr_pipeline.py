"""Integration of physical PCM clips with the Faster Whisper adapter boundary."""

from __future__ import annotations

import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.chunked_transcription import ChunkedTranscription
from voz.application.ports.transcription import TranscriptionOptions
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource

VALID_AUDIO = Path(__file__).parents[2] / "fixtures/media/synthetic-tone.wav"
DESCRIPTOR = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="integration-fixture",
    display_name="Integration fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
    source="example/faster-whisper-integration",
    revision="dddddddddddddddddddddddddddddddddddddddd",
)


@dataclass
class _Segment:
    start: float
    end: float
    text: str


@dataclass
class _Info:
    language: str | None


class _Engine:
    def __init__(self) -> None:
        self.durations_ms: list[int] = []
        self.clip_timestamps: list[str | list[float]] = []

    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
    ) -> tuple[Iterable[_Segment], _Info]:
        assert language is None
        assert word_timestamps is False
        self.clip_timestamps.append(clip_timestamps)
        with wave.open(audio, "rb") as clipped:
            assert clipped.getnchannels() == 1
            assert clipped.getsampwidth() == 2
            assert clipped.getframerate() == 16_000
            duration_ms = clipped.getnframes() * 1_000 // clipped.getframerate()
        self.durations_ms.append(duration_ms)
        return iter((_Segment(0.0, duration_ms / 1_000, "chunk"),)), _Info("es")


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        assert descriptor is DESCRIPTOR
        return self.path


def test_physical_clips_are_transcribed_locally_then_globalized(tmp_path: Path) -> None:
    project_id = uuid4()
    media_asset_id = uuid4()
    derivative = (
        tmp_path
        / "projects"
        / str(project_id)
        / "derivatives"
        / f"{media_asset_id}.inference.wav"
    )
    derivative.parent.mkdir(parents=True)
    derivative.write_bytes(VALID_AUDIO.read_bytes())
    engine = _Engine()
    factory_calls = 0

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path
        nonlocal factory_calls
        factory_calls += 1
        assert device == "cpu"
        assert compute_type == "int8"
        assert local_files_only
        return engine

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path / "model"),
        execution=ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8),
        engine_factory=factory,
    )
    result = ChunkedTranscription(
        provider,
        FileSystemInferenceAudioSource(tmp_path, project_id, media_asset_id),
    ).execute(
        duration_ms=250,
        options=TranscriptionOptions(model=DESCRIPTOR),
        chunk_duration_ms=100,
        overlap_ms=20,
    )

    assert factory_calls == 1
    assert engine.durations_ms == [120, 140, 70]
    assert engine.clip_timestamps == ["0", "0", "0"]
    assert [(segment.start_ms, segment.end_ms) for segment in result.segments] == [
        (0, 100),
        (100, 200),
        (200, 250),
    ]
    assert result.language == "es"
