"""Quality profile and glossary reach the engine as keywords (S13.01-S13.03)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.ports.transcription import TranscriptionOptions
from voz.application.quality_profiles import ACADEMIC_PROFILE, DEFAULT_PROFILE
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider

DESCRIPTOR = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="fixture",
    display_name="Fixture model",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
    source="example/faster-whisper-fixture",
    revision="0123456789abcdef0123456789abcdef01234567",
)
CPU = ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8)


@dataclass
class _Segment:
    start: float = 0.0
    end: float = 1.0
    text: str = "hola"
    words: None = None


@dataclass
class _Info:
    language: str | None = "es"


class _Resolver:
    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        return Path("/unused")


class _Engine:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_first = fail_first

    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
        **extra: object,
    ) -> tuple[Iterable[_Segment], _Info]:
        del audio
        self.calls.append(
            {
                "language": language,
                "word_timestamps": word_timestamps,
                "clip_timestamps": clip_timestamps,
                **extra,
            }
        )
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("alignment failed")
        return iter([_Segment()]), _Info()


def _provider(engine: _Engine) -> FasterWhisperProvider:
    def factory(
        model_path: str, *, device: str, compute_type: str, local_files_only: bool
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        return engine

    return FasterWhisperProvider(
        model_resolver=_Resolver(), execution=CPU, engine_factory=factory
    )


def _transcribe(engine: _Engine, **options: object) -> None:
    provider = _provider(engine)
    provider.transcribe(
        audio=BytesIO(b"pcm"),
        options=TranscriptionOptions(model=DESCRIPTOR, **options),  # type: ignore[arg-type]
    )


def test_without_profile_or_glossary_the_engine_gets_no_extras() -> None:
    engine = _Engine()

    _transcribe(engine)

    assert set(engine.calls[0]) == {"language", "word_timestamps", "clip_timestamps"}


def test_default_profile_passes_the_engine_defaults_and_disables_vad() -> None:
    engine = _Engine()

    _transcribe(engine, quality_profile=DEFAULT_PROFILE)

    call = engine.calls[0]
    assert call["beam_size"] == 5
    assert call["temperature"] == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert call["condition_on_previous_text"] is True
    assert call["no_speech_threshold"] == 0.6
    assert call["vad_filter"] is False
    assert "vad_parameters" not in call
    assert "hotwords" not in call


def test_academic_profile_turns_on_vad_with_its_parameters() -> None:
    engine = _Engine()

    _transcribe(engine, quality_profile=ACADEMIC_PROFILE)

    call = engine.calls[0]
    assert call["condition_on_previous_text"] is False
    assert call["temperature"] == [0.0, 0.2, 0.4]
    assert call["vad_filter"] is True
    assert call["vad_parameters"] == {
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "min_silence_duration_ms": 1000,
        "speech_pad_ms": 400,
    }


def test_glossary_becomes_hotwords_and_the_text_is_untouched() -> None:
    engine = _Engine()
    provider = _provider(engine)

    result = provider.transcribe(
        audio=BytesIO(b"pcm"),
        options=TranscriptionOptions(model=DESCRIPTOR, glossary=("Mitocondria", "VOZ")),
    )

    assert engine.calls[0]["hotwords"] == "Mitocondria, VOZ"
    assert result.text == "hola"  # the glossary never rewrites the literal text


def test_the_word_timestamp_retry_keeps_profile_and_glossary() -> None:
    engine = _Engine(fail_first=True)

    _transcribe(
        engine,
        quality_profile=ACADEMIC_PROFILE,
        glossary=("VOZ",),
        word_timestamps=True,
    )

    assert [call["word_timestamps"] for call in engine.calls] == [True, False]
    assert engine.calls[0]["hotwords"] == engine.calls[1]["hotwords"] == "VOZ"
    assert engine.calls[0]["vad_filter"] is engine.calls[1]["vad_filter"] is True


def test_style_prompt_becomes_initial_prompt_next_to_the_glossary_hotwords() -> None:
    engine = _Engine()

    _transcribe(engine, glossary=("VOZ",), prompt="Habla formal. Usa tildes.")

    call = engine.calls[0]
    # Both coexist: hotwords are prepended to every window, the prompt seeds the first.
    assert call["hotwords"] == "VOZ"
    assert call["initial_prompt"] == "Habla formal. Usa tildes."


def test_no_prompt_adds_no_initial_prompt() -> None:
    engine = _Engine()

    _transcribe(engine, prompt=None)

    assert "initial_prompt" not in engine.calls[0]


def test_prompt_survives_the_word_timestamp_retry() -> None:
    engine = _Engine(fail_first=True)

    _transcribe(engine, prompt="Estilo", word_timestamps=True)

    assert [call["initial_prompt"] for call in engine.calls] == ["Estilo", "Estilo"]


def test_on_position_reports_the_end_of_every_decoded_segment() -> None:
    class Two(_Engine):
        def transcribe(self, audio: BinaryIO, **kwargs: object):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)
            return iter([_Segment(0.0, 1.5), _Segment(1.5, 4.0)]), _Info()

    positions: list[int] = []
    provider = _provider(Two())

    provider.transcribe(
        audio=BytesIO(b"pcm"),
        options=TranscriptionOptions(model=DESCRIPTOR, on_position=positions.append),
    )

    assert positions == [1_500, 4_000]
