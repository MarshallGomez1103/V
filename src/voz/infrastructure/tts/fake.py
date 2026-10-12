"""Deterministic offline TTS engine for tests and UI work without models.

It renders a sine tone (or silence) whose length is proportional to the text
and inversely proportional to ``speed``; no model files, no native code.
"""

from __future__ import annotations

import math
import sys
from array import array
from typing import Final

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    PcmSampleFormat,
    SynthesisCancellationToken,
    SynthesisError,
    SynthesisFailureCode,
    SynthesisProgressCallback,
    SynthesisProviderInfo,
    SynthesisRequirements,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.synthesis_request import (
    MAX_SYNTHESIS_SPEED,
    MIN_SYNTHESIS_SPEED,
)
from voz.domain.entities.voice import Voice

FAKE_TTS_PROVIDER_ID: Final = "fake-tts"
_SAMPLE_RATE: Final = 16_000
_SECONDS_PER_CHAR: Final = 0.06
_BLOCK: Final = 1_600  # 0.1 s: cancellation and progress granularity
_AMPLITUDE: Final = 8_000
_VOICES: Final = (
    Voice(id="tone-low", name="Low tone", languages=("en", "es")),
    Voice(id="tone-high", name="High tone", languages=("en", "es")),
    Voice(id="silence", name="Silence", languages=("en", "es")),
)
_FREQUENCY_HZ: Final = {"tone-low": 220.0, "tone-high": 440.0, "silence": 0.0}


class FakeSpeechSynthesisProvider:
    """Fixed voices, 16 kHz int16 mono output, cooperative cancellation."""

    def __init__(self, *, max_chunk_chars: int = 400) -> None:
        self._info = SynthesisProviderInfo(
            provider_id=FAKE_TTS_PROVIDER_ID,
            display_name="Fake TTS (test tone)",
            max_chunk_chars=max_chunk_chars,
        )
        self.closed = False

    def describe(self) -> SynthesisProviderInfo:
        return self._info

    def voices(self, model: ModelDescriptor) -> tuple[Voice, ...]:
        self._require_model(model)
        return _VOICES

    def languages(self, model: ModelDescriptor) -> tuple[str, ...]:
        self._require_model(model)
        return ("en", "es")

    def requirements(self, model: ModelDescriptor) -> SynthesisRequirements:
        self._require_model(model)
        return SynthesisRequirements(runtime_ready=True, ram_bytes=0, disk_bytes=0)

    def synthesize(
        self,
        chunk_text: str,
        *,
        model: ModelDescriptor,
        voice_id: str,
        speed: float = 1.0,
        cancellation: SynthesisCancellationToken | None = None,
        on_progress: SynthesisProgressCallback | None = None,
    ) -> PcmAudio:
        self._require_model(model)
        _check_cancelled(cancellation)
        text = chunk_text.strip()
        if not text:
            raise ValueError("chunk_text must not be blank")
        if len(text) > self._info.max_chunk_chars:
            raise SynthesisError(
                SynthesisFailureCode.TEXT_TOO_LONG,
                "The text chunk is longer than this engine accepts.",
            )
        if not MIN_SYNTHESIS_SPEED <= speed <= MAX_SYNTHESIS_SPEED:
            raise ValueError("speed is out of range")
        if voice_id not in _FREQUENCY_HZ:
            raise SynthesisError(
                SynthesisFailureCode.VOICE_NOT_FOUND,
                "The selected voice does not exist in this model.",
            )
        if self.closed:
            raise SynthesisError(
                SynthesisFailureCode.RUNTIME_UNAVAILABLE,
                "The synthesis engine is closed.",
            )

        total = max(_BLOCK, round(len(text) * _SECONDS_PER_CHAR / speed * _SAMPLE_RATE))
        step = 2 * math.pi * _FREQUENCY_HZ[voice_id] / _SAMPLE_RATE
        samples = array("h")
        for start in range(0, total, _BLOCK):
            _check_cancelled(cancellation)
            end = min(start + _BLOCK, total)
            samples.extend(
                round(_AMPLITUDE * math.sin(step * i)) for i in range(start, end)
            )
            if on_progress is not None:
                on_progress(end / total)
        if sys.byteorder == "big":  # PcmAudio is little-endian
            samples.byteswap()
        return PcmAudio(samples.tobytes(), _SAMPLE_RATE, PcmSampleFormat.INT16)

    def close(self) -> None:
        self.closed = True

    def _require_model(self, model: ModelDescriptor) -> None:
        if model.provider_id != FAKE_TTS_PROVIDER_ID or not model.supports(
            ModelCapability.SYNTHESIS
        ):
            raise SynthesisError(
                SynthesisFailureCode.MODEL_NOT_INSTALLED,
                "The selected model is not installed for this engine.",
            )


def fake_tts_descriptor() -> ModelDescriptor:
    """The single model the fake engine accepts."""
    return ModelDescriptor(
        provider_id=FAKE_TTS_PROVIDER_ID,
        model_id="tone",
        display_name="Test tone",
        capabilities=frozenset({ModelCapability.SYNTHESIS, ModelCapability.CPU}),
    )


def _check_cancelled(cancellation: SynthesisCancellationToken | None) -> None:
    if cancellation is not None and cancellation.is_cancelled():
        raise SynthesisError(
            SynthesisFailureCode.CANCELLED, "Speech synthesis was cancelled."
        )
