"""Reusable behavioral contract for every transcription provider."""

import wave
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest
from _pytest.fixtures import FixtureRequest

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider

DESCRIPTOR = ModelDescriptor(
    provider_id="contract-asr",
    model_id="fixture-v1",
    display_name="Contract fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
)
VALID_AUDIO = Path(__file__).parents[1] / "fixtures/media/synthetic-tone.wav"
FASTER_DESCRIPTOR = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="contract-fixture",
    display_name="Faster Whisper contract fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
    source="example/faster-whisper-contract",
    revision="cccccccccccccccccccccccccccccccccccccccc",
)


class _Cancellation:
    def __init__(self, requested: bool) -> None:
        self.requested = requested

    def is_cancelled(self) -> bool:
        return self.requested


class _ContractProvider:
    @property
    def provider_id(self) -> str:
        return "contract-asr"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        if cancellation is not None and cancellation.is_cancelled():
            raise TranscriptionError(
                TranscriptionFailureCode.CANCELLED,
                "Transcription was cancelled.",
            )
        payload = audio.read()
        try:
            with wave.open(BytesIO(payload), "rb") as normalized:
                if (
                    normalized.getnchannels() != 1
                    or normalized.getframerate() != 16_000
                    or normalized.getsampwidth() != 2
                ):
                    raise wave.Error("audio is not normalized PCM")
        except (EOFError, wave.Error) as error:
            raise TranscriptionError(
                TranscriptionFailureCode.INVALID_AUDIO,
                "The selected audio is invalid.",
            ) from error
        assert options.model is DESCRIPTOR
        return TranscriptionResult(
            segments=(
                TranscriptionSegment(start_ms=0, end_ms=100, text="hola"),
                TranscriptionSegment(start_ms=100, end_ms=250, text=" mundo"),
            ),
            language="es",
        )


class _InvalidAudioError(Exception):
    pass


@dataclass
class _EngineSegment:
    start: float
    end: float
    text: str


@dataclass
class _EngineInfo:
    language: str | None


class _ContractEngine:
    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
    ) -> tuple[Iterable[_EngineSegment], _EngineInfo]:
        del language
        assert word_timestamps is False
        assert clip_timestamps == "0"
        try:
            with wave.open(BytesIO(audio.read()), "rb") as normalized:
                if (
                    normalized.getnchannels() != 1
                    or normalized.getframerate() != 16_000
                    or normalized.getsampwidth() != 2
                ):
                    raise wave.Error("audio is not normalized PCM")
        except (EOFError, wave.Error) as error:
            raise _InvalidAudioError from error
        return (
            iter(
                (
                    _EngineSegment(0.0, 0.1, "hola"),
                    _EngineSegment(0.1, 0.25, " mundo"),
                )
            ),
            _EngineInfo("es"),
        )


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        assert descriptor is FASTER_DESCRIPTOR
        return self.path


@dataclass(frozen=True)
class _ProviderContractCase:
    provider: TranscriptionProvider
    options: TranscriptionOptions


@pytest.fixture(params=("structural", "faster-whisper"))
def provider_case(
    request: FixtureRequest,
    tmp_path: Path,
) -> _ProviderContractCase:
    if request.param == "structural":
        return _ProviderContractCase(
            provider=_ContractProvider(),
            options=TranscriptionOptions(model=DESCRIPTOR, language="es"),
        )

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _ContractEngine:
        assert model_path == str(tmp_path)
        assert device == "cpu"
        assert compute_type == "int8"
        assert local_files_only
        return _ContractEngine()

    return _ProviderContractCase(
        provider=FasterWhisperProvider(
            model_resolver=_Resolver(tmp_path),
            execution=ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8),
            engine_factory=factory,
            invalid_audio_errors=(_InvalidAudioError,),
        ),
        options=TranscriptionOptions(model=FASTER_DESCRIPTOR, language="es"),
    )


def _accept_provider(provider: TranscriptionProvider) -> TranscriptionProvider:
    return provider


def test_provider_accepts_valid_audio_and_uses_only_canonical_types(
    provider_case: _ProviderContractCase,
) -> None:
    provider = _accept_provider(provider_case.provider)

    with VALID_AUDIO.open("rb") as audio:
        result = provider.transcribe(
            audio=audio,
            options=provider_case.options,
        )

    assert isinstance(provider_case.provider, TranscriptionProvider)
    assert provider.provider_id == provider_case.options.model.provider_id
    assert result.text == "hola mundo"
    assert result.language == "es"
    assert not hasattr(result, "path")


def test_provider_returns_monotonic_non_negative_timestamps(
    provider_case: _ProviderContractCase,
) -> None:
    with VALID_AUDIO.open("rb") as audio:
        result = provider_case.provider.transcribe(
            audio=audio,
            options=provider_case.options,
        )

    assert all(segment.start_ms >= 0 for segment in result.segments)
    assert all(segment.end_ms > segment.start_ms for segment in result.segments)
    assert all(
        previous.end_ms <= current.start_ms
        for previous, current in zip(
            result.segments,
            result.segments[1:],
            strict=False,
        )
    )


def test_provider_maps_invalid_audio_to_a_typed_failure(
    provider_case: _ProviderContractCase,
) -> None:
    with pytest.raises(TranscriptionError) as raised:
        provider_case.provider.transcribe(
            audio=BytesIO(b"not-a-wave"),
            options=provider_case.options,
        )

    assert raised.value.code is TranscriptionFailureCode.INVALID_AUDIO
    assert raised.value.user_message == "The selected audio is invalid."


def test_provider_honors_cancellation_without_reading_audio(
    provider_case: _ProviderContractCase,
) -> None:
    unreadable = BytesIO(b"not-a-wave")

    with pytest.raises(TranscriptionError) as raised:
        provider_case.provider.transcribe(
            audio=unreadable,
            options=provider_case.options,
            cancellation=_Cancellation(True),
        )

    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert unreadable.tell() == 0


def test_options_require_a_transcription_capable_model() -> None:
    descriptor = ModelDescriptor(
        provider_id="diarizer",
        model_id="speakers-v1",
        display_name="Speaker model",
        capabilities=frozenset({ModelCapability.DIARIZATION}),
    )

    with pytest.raises(ValueError, match="transcription capability"):
        TranscriptionOptions(model=descriptor)


@pytest.mark.parametrize("language", ["", " es", "es ", "es\nprivate"])
def test_options_reject_ambiguous_language_hints(language: str) -> None:
    with pytest.raises(ValueError, match="language"):
        TranscriptionOptions(model=DESCRIPTOR, language=language)


def test_segment_rejects_invalid_offsets_and_empty_text() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TranscriptionSegment(start_ms=-1, end_ms=1, text="hola")
    with pytest.raises(ValueError, match="greater than start_ms"):
        TranscriptionSegment(start_ms=1, end_ms=1, text="hola")
    with pytest.raises(ValueError, match="cannot be empty"):
        TranscriptionSegment(start_ms=0, end_ms=1, text="")


def test_result_requires_ordered_non_overlapping_segments() -> None:
    first = TranscriptionSegment(start_ms=100, end_ms=200, text="primero")
    overlapping = TranscriptionSegment(start_ms=199, end_ms=300, text="segundo")

    with pytest.raises(ValueError, match="ordered and non-overlapping"):
        TranscriptionResult(segments=(first, overlapping))


def test_result_and_options_are_immutable() -> None:
    options = TranscriptionOptions(model=DESCRIPTOR)
    result = TranscriptionResult(
        segments=(TranscriptionSegment(start_ms=0, end_ms=1, text="a"),)
    )

    with pytest.raises(AttributeError):
        options.language = "en"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.language = "en"  # type: ignore[misc]
