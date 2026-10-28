"""Which speech models the person can pick right now, and with which voices."""

from __future__ import annotations

from dataclasses import dataclass

from voz.application.ports.speech_synthesis import SynthesisError, SynthesisProviderInfo
from voz.application.ports.transcription_options import InstallationStatus
from voz.application.synthesis.create_synthesis_job import SynthesisModelCatalog
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice


@dataclass(frozen=True, slots=True)
class SynthesisModelOption:
    descriptor: ModelDescriptor
    runtime_ready: bool
    languages: tuple[str, ...]
    voices: tuple[Voice, ...]


@dataclass(frozen=True, slots=True)
class SynthesisOptions:
    providers: tuple[SynthesisProviderInfo, ...]
    models: tuple[SynthesisModelOption, ...]


def list_synthesis_options(
    providers: SynthesisProviderRegistry, catalog: SynthesisModelCatalog
) -> SynthesisOptions:
    """Installed speech models of a registered engine, ready to be described."""
    registered = {
        provider.describe().provider_id: provider for provider in providers.list_all()
    }
    models: list[SynthesisModelOption] = []
    for item in catalog.list_models():
        model = item.descriptor
        provider = registered.get(model.provider_id)
        if (
            provider is None
            or not model.supports(ModelCapability.SYNTHESIS)
            or item.installation_status is not InstallationStatus.REGISTERED
            or not item.files_available
        ):
            continue
        try:
            ready = provider.requirements(model).runtime_ready
            voices = provider.voices(model)
            languages = provider.languages(model)
        except SynthesisError:
            continue  # broken install: the Model Manager shows why
        models.append(SynthesisModelOption(model, ready, tuple(languages), voices))
    return SynthesisOptions(
        tuple(provider.describe() for provider in registered.values()), tuple(models)
    )


__all__ = ["SynthesisModelOption", "SynthesisOptions", "list_synthesis_options"]
