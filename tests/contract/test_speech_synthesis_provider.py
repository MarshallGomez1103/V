"""Reusable behavioral contract for every speech synthesis engine (ADR-0010).

A new engine joins by adding one case to ``provider_case``: a factory, a model
descriptor it accepts and a valid voice id. Everything else must pass unchanged.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from _pytest.fixtures import FixtureRequest

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    SpeechSynthesisProvider,
    SynthesisError,
    SynthesisFailureCode,
    SynthesisProviderInfo,
    SynthesisRequirements,
)
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure.tts.fake import FakeSpeechSynthesisProvider, fake_tts_descriptor
from voz.infrastructure.tts.subprocess_provider import (
    SubprocessSynthesisProvider,
    TtsModelManifest,
)

TEXT = "Hola, esto es una prueba de voz."


@dataclass(frozen=True)
class _Case:
    factory: Callable[[], SpeechSynthesisProvider]
    model: ModelDescriptor
    voice_id: str


class _CancelAfter:
    """Reports ``False`` for the first ``allowed`` polls, then ``True``."""

    def __init__(self, allowed: int) -> None:
        self.allowed = allowed
        self.polls = 0

    def is_cancelled(self) -> bool:
        self.polls += 1
        return self.polls > self.allowed


@dataclass(frozen=True)
class _Engine:
    provider: SpeechSynthesisProvider
    model: ModelDescriptor
    voice_id: str

    def say(self, text: str = TEXT, **kwargs: object) -> PcmAudio:
        options: dict[str, object] = {"voice_id": self.voice_id, **kwargs}
        return self.provider.synthesize(text, model=self.model, **options)  # type: ignore[arg-type]


_FAKE_WORKER = Path(__file__).parents[1] / "fixtures" / "tts" / "fake_tts_worker.py"


def _subprocess_case(tmp_path: Path) -> _Case:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"x")
    manifest = TtsModelManifest(
        family="fake",
        files={"model": model_file},
        voices=(Voice("0", "Zero", ("es",)), Voice("1", "One", ("en", "es"))),
        languages=("es", "en"),
    )
    info = SynthesisProviderInfo(
        "subprocess-tts", "Subprocess TTS", max_chunk_chars=400
    )
    model = ModelDescriptor(
        provider_id="subprocess-tts",
        model_id="m1",
        display_name="Fake child",
        capabilities=frozenset({ModelCapability.SYNTHESIS}),
    )
    return _Case(
        lambda: SubprocessSynthesisProvider(
            info=info,
            argv=[sys.executable, str(_FAKE_WORKER)],
            manifests={"m1": manifest},
        ),
        model,
        "0",
    )


@pytest.fixture(params=("fake", "subprocess"))
def engine(request: FixtureRequest, tmp_path: Path) -> Iterator[_Engine]:
    cases = {
        "fake": _Case(FakeSpeechSynthesisProvider, fake_tts_descriptor(), "tone-low"),
        "subprocess": _subprocess_case(tmp_path),
    }
    case = cases[request.param]
    provider = case.factory()
    yield _Engine(provider, case.model, case.voice_id)
    provider.close()


def _code(error: pytest.ExceptionInfo[SynthesisError]) -> SynthesisFailureCode:
    return error.value.code


def test_provider_conforms_structurally_and_registers(engine: _Engine) -> None:
    info = engine.provider.describe()

    assert isinstance(engine.provider, SpeechSynthesisProvider)
    assert isinstance(info, SynthesisProviderInfo)
    assert info.provider_id == engine.model.provider_id
    assert info.max_chunk_chars > 0
    registry = SynthesisProviderRegistry((engine.provider,))
    assert registry.get(info.provider_id) is engine.provider


def test_voices_are_non_empty_unique_and_stable(engine: _Engine) -> None:
    first = engine.provider.voices(engine.model)
    second = engine.provider.voices(engine.model)

    assert first
    assert first == second
    assert all(isinstance(voice, Voice) for voice in first)
    assert len({voice.id for voice in first}) == len(first)
    assert engine.voice_id in {voice.id for voice in first}


def test_languages_and_requirements_use_canonical_types(engine: _Engine) -> None:
    languages = engine.provider.languages(engine.model)
    requirements = engine.provider.requirements(engine.model)

    assert isinstance(languages, tuple)
    assert all(isinstance(language, str) and language for language in languages)
    assert isinstance(requirements, SynthesisRequirements)


def test_valid_text_renders_non_empty_audio_and_reports_progress(
    engine: _Engine,
) -> None:
    progress: list[float] = []

    audio = engine.say(on_progress=progress.append)

    assert isinstance(audio, PcmAudio)
    assert audio.sample_rate > 0
    assert audio.frame_count > 0
    assert not hasattr(audio, "path")
    assert all(0.0 <= value <= 1.0 for value in progress)
    assert progress == sorted(progress)


def test_every_voice_renders(engine: _Engine) -> None:
    for voice in engine.provider.voices(engine.model):
        audio = engine.provider.synthesize(TEXT, model=engine.model, voice_id=voice.id)
        assert audio.frame_count > 0


def test_faster_speed_produces_shorter_audio(engine: _Engine) -> None:
    normal = engine.say(speed=1.0)
    fast = engine.say(speed=2.0)
    slow = engine.say(speed=0.5)

    assert fast.duration_seconds < normal.duration_seconds < slow.duration_seconds


def test_unknown_voice_is_voice_not_found(engine: _Engine) -> None:
    with pytest.raises(SynthesisError) as raised:
        engine.say(voice_id="no-such-voice")

    assert _code(raised) is SynthesisFailureCode.VOICE_NOT_FOUND


def test_text_over_the_declared_limit_is_text_too_long(engine: _Engine) -> None:
    limit = engine.provider.describe().max_chunk_chars

    with pytest.raises(SynthesisError) as raised:
        engine.say("a" * (limit + 1))

    assert _code(raised) is SynthesisFailureCode.TEXT_TOO_LONG


def test_cancellation_before_start_is_cancelled_without_progress(
    engine: _Engine,
) -> None:
    progress: list[float] = []

    with pytest.raises(SynthesisError) as raised:
        engine.say(cancellation=_CancelAfter(0), on_progress=progress.append)

    assert _code(raised) is SynthesisFailureCode.CANCELLED
    assert progress == []


def test_cancellation_during_rendering_is_cancelled(engine: _Engine) -> None:
    with pytest.raises(SynthesisError) as raised:
        engine.say(cancellation=_CancelAfter(1))

    assert _code(raised) is SynthesisFailureCode.CANCELLED


def test_close_is_idempotent(engine: _Engine) -> None:
    engine.say()

    engine.provider.close()
    engine.provider.close()


def test_pcm_audio_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        PcmAudio(b"\x00\x00", 0)
    with pytest.raises(ValueError, match="whole sample"):
        PcmAudio(b"", 16_000)
    with pytest.raises(ValueError, match="whole sample"):
        PcmAudio(b"\x00", 16_000)
    with pytest.raises(AttributeError):
        PcmAudio(b"\x00\x00", 16_000).sample_rate = 8_000  # type: ignore[misc]
