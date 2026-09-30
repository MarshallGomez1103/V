"""Local-only observations for the transcription options query; no model loads."""

import importlib
from dataclasses import dataclass, replace

from voz.application.ports.transcription import TranscriptionError
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
    TranscriptionOptionsUnavailable,
)
from voz.domain.entities.model_descriptor import ModelCapability
from voz.infrastructure.asr.catalog import faster_whisper_catalog
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.model_storage import FileSystemModelStore

# Capabilities reachable through the current VOZ adapter, not all upstream tasks.
_ADAPTER_CAPABILITIES = frozenset(
    {
        ModelCapability.TRANSCRIPTION,
        ModelCapability.LANGUAGE_DETECTION,
        ModelCapability.CPU,
        ModelCapability.GPU,
        ModelCapability.WORD_TIMESTAMPS,
    }
)


@dataclass(frozen=True, slots=True)
class LocalTranscriptionModelCatalog:
    store: FileSystemModelStore

    def list_models(self) -> tuple[ModelRegistration, ...]:
        try:
            registered = self.store.registered_descriptors()
            options: list[ModelRegistration] = []
            for entry in faster_whisper_catalog():
                # Vocabulary is vocabulary.txt or vocabulary.json depending on model.
                required = (
                    "model.bin",
                    "config.json",
                    "tokenizer.json",
                    *(f.name for f in entry.files if f.name.startswith("vocabulary.")),
                )
                matches: list[ModelRegistration] = []
                for local in registered:
                    if (
                        local.identity != entry.descriptor.identity
                        or local.source != entry.descriptor.source
                    ):
                        continue
                    candidate = replace(entry.descriptor, revision=local.revision)
                    directory = self.store.resolve_path(candidate)
                    files_available = all(
                        not (directory / name).is_symlink()
                        and (directory / name).is_file()
                        and (directory / name).stat().st_size > 0
                        for name in required
                    )
                    matches.append(
                        ModelRegistration(
                            candidate,
                            InstallationStatus.REGISTERED,
                            files_available,
                        )
                    )
                options.extend(
                    matches
                    or [
                        ModelRegistration(
                            entry.descriptor, InstallationStatus.NOT_REGISTERED
                        )
                    ]
                )
            return tuple(options)
        except (OSError, TranscriptionError) as error:
            raise TranscriptionOptionsUnavailable from error


class FasterWhisperRuntimeProbe:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        if provider_id != "faster-whisper":
            return RuntimeAvailability(False)
        try:
            module = importlib.import_module("faster_whisper")
            if not callable(vars(module).get("WhisperModel")):
                return RuntimeAvailability(False, capabilities=_ADAPTER_CAPABILITIES)
            hardware = CTranslate2HardwareProbe().probe()
        except (ImportError, OSError, RuntimeError, ValueError, TranscriptionError):
            return RuntimeAvailability(False, capabilities=_ADAPTER_CAPABILITIES)
        return RuntimeAvailability(True, hardware, _ADAPTER_CAPABILITIES)
