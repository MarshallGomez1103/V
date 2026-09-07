"""Application composition root.

Framework and infrastructure wiring belongs here so that the domain remains
independent of transport concerns.
"""

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from voz import __version__
from voz.application.asr_device_selection import (
    ExecutionDecision,
    HardwareCapabilities,
    select_execution,
)
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.paths import VozPaths, resolve_voz_paths
from voz.infrastructure.persistence.repositories import (
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.interfaces.api.health import router as health_router

STATIC_DIRECTORY = Path(__file__).with_name("static")


@dataclass(frozen=True, slots=True)
class LocalAsrRuntime:
    """Explicitly composed local ASR services with no model download side effect."""

    descriptor: ModelDescriptor
    paths: VozPaths
    model_store: FileSystemModelStore
    execution: ExecutionDecision
    providers: TranscriptionProviderRegistry
    _provider: FasterWhisperProvider = field(repr=False)

    def close(self) -> None:
        """Release the concrete ASR adapter when its infrastructure owner exits."""
        self._provider.close()

    def recoverable_transcription(
        self,
        *,
        engine: Engine,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> RecoverableTranscription:
        """Wire one persisted job to its safe normalized-audio source."""
        return RecoverableTranscription(
            provider=self.providers.get(self.descriptor.provider_id),
            audio_source=FileSystemInferenceAudioSource(
                self.paths.data,
                project_id,
                media_asset_id,
            ),
            checkpoints=SqliteTranscriptionCheckpointStore(engine),
            jobs=SqliteTranscriptionJobRepository(engine),
        )


def create_local_asr_runtime(
    descriptor: ModelDescriptor,
    *,
    paths: VozPaths | None = None,
    hardware: HardwareCapabilities | None = None,
) -> LocalAsrRuntime:
    """Compose Faster Whisper from an explicit descriptor and detected hardware."""
    if descriptor.provider_id != FasterWhisperProvider.provider_id:
        raise ValueError("local ASR runtime requires a Faster Whisper descriptor")
    if descriptor.profile is None:
        raise ValueError("a local ASR descriptor must include a processing profile")
    resolved_paths = resolve_voz_paths() if paths is None else paths
    model_store = FileSystemModelStore(
        data_root=resolved_paths.data,
        cache_root=resolved_paths.cache,
    )
    capabilities = CTranslate2HardwareProbe().probe() if hardware is None else hardware
    execution = select_execution(descriptor.profile, capabilities)
    provider = FasterWhisperProvider(
        model_resolver=model_store,
        execution=execution,
        configured_model=descriptor,
    )
    return LocalAsrRuntime(
        descriptor=descriptor,
        paths=resolved_paths,
        model_store=model_store,
        execution=execution,
        providers=TranscriptionProviderRegistry((provider,)),
        _provider=provider,
    )


def create_app() -> FastAPI:
    """Build the local VOZ HTTP application."""
    application = FastAPI(
        title="VOZ",
        description="Local-first transcription workspace API.",
        version=__version__,
    )
    application.include_router(health_router)
    if STATIC_DIRECTORY.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=STATIC_DIRECTORY, html=True),
            name="web",
        )
    return application


app = create_app()
