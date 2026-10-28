"""Which synthesis models are offered to the person (no FastAPI)."""

from __future__ import annotations

from dataclasses import replace

from synthesis_support import MemoryCatalog, installed_fake_model

from voz.application.ports.speech_synthesis import (
    SynthesisError,
    SynthesisFailureCode,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.application.synthesis.list_synthesis_options import list_synthesis_options
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
    fake_tts_descriptor,
)


def _registry() -> SynthesisProviderRegistry:
    return SynthesisProviderRegistry([FakeSpeechSynthesisProvider()])


def test_an_installed_model_of_a_registered_engine_is_offered() -> None:
    options = list_synthesis_options(_registry(), MemoryCatalog(installed_fake_model()))

    assert [info.provider_id for info in options.providers] == [FAKE_TTS_PROVIDER_ID]
    (model,) = options.models
    assert model.descriptor == fake_tts_descriptor()
    assert model.runtime_ready is True
    assert model.languages == ("en", "es")
    assert [voice.id for voice in model.voices] == ["tone-low", "tone-high", "silence"]


def test_models_that_cannot_synthesize_today_are_left_out() -> None:
    other_engine = ModelRegistration(
        replace(fake_tts_descriptor(), provider_id="other-engine"),
        InstallationStatus.REGISTERED,
        files_available=True,
    )
    not_installed = replace(
        installed_fake_model(), installation_status=InstallationStatus.NOT_REGISTERED
    )
    files_missing = replace(installed_fake_model(), files_available=False)
    transcription_only = ModelRegistration(
        ModelDescriptor(
            provider_id=FAKE_TTS_PROVIDER_ID,
            model_id="asr",
            display_name="Not speech",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        ),
        InstallationStatus.REGISTERED,
        files_available=True,
    )
    catalog = MemoryCatalog(
        other_engine, not_installed, files_missing, transcription_only
    )

    options = list_synthesis_options(_registry(), catalog)

    assert options.models == ()
    assert len(options.providers) == 1  # the engine is still listed


def test_a_model_the_engine_cannot_describe_is_skipped_not_fatal() -> None:
    class BrokenInstall(FakeSpeechSynthesisProvider):
        def voices(self, model: ModelDescriptor) -> tuple[Voice, ...]:
            raise SynthesisError(SynthesisFailureCode.MODEL_NOT_INSTALLED, "broken")

    registry = SynthesisProviderRegistry([BrokenInstall()])

    options = list_synthesis_options(registry, MemoryCatalog(installed_fake_model()))

    assert options.models == ()
