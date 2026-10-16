"""One Model Manager catalog and store across every local model family.

Aggregates the pinned faster-whisper and whisper.cpp catalogs, the sherpa
diarization models (ADR-0007) and the speech synthesis models (ADR-0010), and
routes store calls to the right backend.
Models are addressed by ``"<provider_id>:<model_id>"`` (``model_keys``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from voz.application.model_manager import ModelStore
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.asr.catalog import faster_whisper_catalog
from voz.infrastructure.asr.whisper_cpp_catalog import whisper_cpp_catalog
from voz.infrastructure.diarization.models import (
    EMBEDDING_MODEL,
    SEGMENTATION_ARCHIVE,
    DiarizationModelStore,
)
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.tts.catalog import (
    TTS_CATALOG,
    TTS_PROVIDER_ID,
    TTS_REQUIRES,
    TtsModelEntry,
)
from voz.infrastructure.tts.model_store import TtsModelStore

DIARIZATION_PROVIDER_ID = "diarization"
WHISPER_CPP_REQUIRES = "whisper-cli"
DIARIZATION_REQUIRES = "diarization"  # the optional ``diarization`` extra

_CPU = ModelCapability.CPU
_GPU = ModelCapability.GPU

# Invariant (ADR-0010 section 8): a catalog entry may only declare capabilities
# that the engine registered for its provider really implements. Add the entry
# for a new engine (TTS, wake word, aligner) in the same change that registers it.
# ``word_timestamps`` is native to both ASR engines (ADR-0008), so ``alignment``
# stays undeclared: it needs a separate ``AlignmentProvider`` that does not exist.
ENGINE_CAPABILITIES: Mapping[str, frozenset[ModelCapability]] = {
    "faster-whisper": frozenset(
        {
            ModelCapability.TRANSCRIPTION,
            ModelCapability.TRANSLATION,
            ModelCapability.LANGUAGE_DETECTION,
            ModelCapability.WORD_TIMESTAMPS,
            _CPU,
            _GPU,
        }
    ),
    "whisper-cpp": frozenset(
        {
            ModelCapability.TRANSCRIPTION,
            ModelCapability.LANGUAGE_DETECTION,
            ModelCapability.WORD_TIMESTAMPS,
            _CPU,
            _GPU,
        }
    ),
    "sherpa-onnx-asr": frozenset({ModelCapability.TRANSCRIPTION, _CPU}),
    "diarization": frozenset({ModelCapability.DIARIZATION, _CPU}),
    TTS_PROVIDER_ID: frozenset({ModelCapability.SYNTHESIS, _CPU}),
}


def undeclarable_capabilities(
    descriptor: ModelDescriptor,
) -> frozenset[ModelCapability]:
    """Capabilities the descriptor declares without an engine behind them."""

    return descriptor.capabilities - ENGINE_CAPABILITIES.get(
        descriptor.provider_id, frozenset()
    )


# ponytail: no upstream commit to pin (release assets, verified by SHA-256), so
# the descriptor carries no source/revision and is never matched to external caches.
DIARIZATION_DESCRIPTOR = ModelDescriptor(
    provider_id=DIARIZATION_PROVIDER_ID,
    model_id="sherpa-default",
    display_name="Separación de hablantes (sherpa-onnx)",
    capabilities=frozenset({ModelCapability.DIARIZATION, ModelCapability.CPU}),
)


@dataclass(frozen=True, slots=True)
class ManagedModel:
    """A catalog entry as the Model Manager sees it, whatever its provider."""

    descriptor: ModelDescriptor
    files: tuple[ModelFile, ...]
    license: str
    multilingual: bool
    kind: str = "asr"  # asr | diarization | tts
    requires: str | None = None
    runtime_available: bool = True


class ManagedModelCatalog:
    """faster-whisper, whisper.cpp (only with its runtime), diarization and TTS.

    The speech synthesis models are listed only when ``tts_runtime_available`` is
    given (the composition root passes it once the engine is registered).
    """

    def __init__(
        self,
        *,
        whisper_cpp_available: Callable[[], bool],
        diarization_runtime_available: Callable[[], bool],
        tts_runtime_available: Callable[[], bool] | None = None,
        tts_models: Sequence[TtsModelEntry] = TTS_CATALOG,
        custom_models: Callable[[], Sequence[ManagedModel]] | None = None,
    ) -> None:
        self._whisper_cpp_available = whisper_cpp_available
        self._diarization_runtime_available = diarization_runtime_available
        self._tts_runtime_available = tts_runtime_available
        self._tts_models = tuple(tts_models)
        self._custom_models = custom_models

    def entries(self) -> tuple[ManagedModel, ...]:
        models = [
            ManagedModel(e.descriptor, e.files, e.license, e.multilingual)
            for e in faster_whisper_catalog()
        ]
        if self._whisper_cpp_available():
            models.extend(
                ManagedModel(
                    e.descriptor,
                    e.files,
                    e.license,
                    e.multilingual,
                    requires=WHISPER_CPP_REQUIRES,
                )
                for e in whisper_cpp_catalog()
            )
        models.append(
            ManagedModel(
                DIARIZATION_DESCRIPTOR,
                # Sizes feed the progress total; the store downloads by itself.
                tuple(
                    ModelFile(a.name, a.size_bytes, a.sha256)
                    for a in (SEGMENTATION_ARCHIVE, EMBEDDING_MODEL)
                ),
                license=(
                    "MIT (pyannote segmentation)"
                    " · CC-BY-4.0 (WeSpeaker, VoxCeleb-trained)"
                ),
                multilingual=True,
                kind="diarization",
                requires=DIARIZATION_REQUIRES,
                runtime_available=self._diarization_runtime_available(),
            )
        )
        if self._tts_runtime_available is not None:
            runtime_available = self._tts_runtime_available()
            models.extend(
                ManagedModel(
                    e.descriptor,
                    (ModelFile(e.archive_name, e.size_bytes, e.sha256),),
                    e.license,
                    multilingual=len(e.languages) > 1,
                    kind="tts",
                    requires=TTS_REQUIRES,
                    runtime_available=runtime_available,
                )
                for e in self._tts_models
            )
        if self._custom_models is not None:
            models.extend(self._custom_models())
        return tuple(models)


class RoutingModelStore:
    """``ModelStore`` + download port: diarization and TTS to their stores."""

    def __init__(
        self,
        files: FileSystemModelStore,
        diarization: DiarizationModelStore,
        tts: TtsModelStore | None = None,
        custom: ModelStore | None = None,
    ) -> None:
        self._files = files
        self._diarization = diarization
        self._tts = tts
        self._custom = custom

    def _custom_store(self, descriptor: ModelDescriptor) -> ModelStore | None:
        return self._custom if descriptor.model_id.startswith("custom-") else None

    @staticmethod
    def _is_diarization(descriptor: ModelDescriptor) -> bool:
        return descriptor.provider_id == DIARIZATION_PROVIDER_ID

    @staticmethod
    def _is_tts(descriptor: ModelDescriptor) -> bool:
        return descriptor.provider_id == TTS_PROVIDER_ID

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        if custom := self._custom_store(descriptor):
            return custom.is_installed(descriptor)
        if self._is_diarization(descriptor):
            return self._diarization.is_installed()
        if self._is_tts(descriptor):
            return self._tts is not None and self._tts.is_installed(descriptor.model_id)
        return self._files.is_installed(descriptor)

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        if custom := self._custom_store(descriptor):
            return custom.disk_usage(descriptor)
        if self._is_tts(descriptor):
            return (
                None if self._tts is None else self._tts.disk_usage(descriptor.model_id)
            )
        if not self._is_diarization(descriptor):
            return self._files.disk_usage(descriptor)
        paths = self._diarization.paths()
        if paths is None:
            return None
        return sum(
            item.stat().st_size
            for item in paths.segmentation.parent.iterdir()
            if item.is_file()
        )

    def reclaimable_usage(self, descriptor: ModelDescriptor) -> int | None:
        if custom := self._custom_store(descriptor):
            return custom.reclaimable_usage(descriptor)
        if self._is_diarization(descriptor) or self._is_tts(descriptor):
            return self.disk_usage(descriptor)  # downloaded files are never shared
        return self._files.reclaimable_usage(descriptor)

    def remove(self, descriptor: ModelDescriptor) -> int:
        if custom := self._custom_store(descriptor):
            return custom.remove(descriptor)
        if self._is_diarization(descriptor):
            return self._diarization.remove()
        if self._is_tts(descriptor):
            return 0 if self._tts is None else self._tts.remove(descriptor.model_id)
        return self._files.remove(descriptor)

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> object:
        if self._is_diarization(descriptor):
            return self._diarization.install(progress=progress, cancelled=cancelled)
        if self._is_tts(descriptor):
            if self._tts is None:
                raise ModelInstallationError(
                    ModelInstallationFailureCode.NOT_INSTALLED,
                    "Speech synthesis models are not available.",
                )
            return self._tts.install(
                descriptor.model_id, progress=progress, cancelled=cancelled
            )
        return self._files.download(
            descriptor, files, progress=progress, cancelled=cancelled
        )


__all__ = [
    "DIARIZATION_DESCRIPTOR",
    "ENGINE_CAPABILITIES",
    "ManagedModel",
    "ManagedModelCatalog",
    "RoutingModelStore",
    "undeclarable_capabilities",
]
