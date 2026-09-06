"""Opt-in smoke for a user-installed real Faster Whisper CPU model."""

import os
from pathlib import Path

import pytest

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.ports.transcription import (
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider

VALID_AUDIO = Path(__file__).parents[2] / "fixtures/media/synthetic-tone.wav"
MODEL_DIRECTORY = os.environ.get("VOZ_FASTER_WHISPER_MODEL_DIR")
MODEL_SOURCE = os.environ.get("VOZ_FASTER_WHISPER_MODEL_SOURCE")
MODEL_REVISION = os.environ.get("VOZ_FASTER_WHISPER_MODEL_REVISION")


class _OptInResolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        del descriptor
        return self.path


@pytest.mark.skipif(
    MODEL_DIRECTORY is None or MODEL_SOURCE is None or MODEL_REVISION is None,
    reason="set the explicit Faster Whisper model path, source and revision",
)
def test_real_faster_whisper_cpu_smoke_uses_only_local_model() -> None:
    assert MODEL_DIRECTORY is not None
    assert MODEL_SOURCE is not None
    assert MODEL_REVISION is not None
    model_path = Path(MODEL_DIRECTORY).absolute()
    if not model_path.is_dir():
        pytest.fail("VOZ_FASTER_WHISPER_MODEL_DIR must name an installed directory")
    descriptor = ModelDescriptor(
        provider_id="faster-whisper",
        model_id="opt-in-local",
        display_name="Opt-in local model",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
        source=MODEL_SOURCE,
        revision=MODEL_REVISION,
    )
    provider = FasterWhisperProvider(
        model_resolver=_OptInResolver(model_path),
        execution=ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8),
    )

    with VALID_AUDIO.open("rb") as audio:
        result = provider.transcribe(
            audio=audio,
            options=TranscriptionOptions(model=descriptor),
        )

    assert isinstance(result, TranscriptionResult)
