"""Application composition root.

Framework and infrastructure wiring belongs here so that the domain remains
independent of transport concerns.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Self
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
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.import_media import ImportMedia
from voz.application.projects import CreateProject, ListProjects
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.asr.options import (
    FasterWhisperRuntimeProbe,
    LocalTranscriptionModelCatalog,
)
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.paths import VozPaths, resolve_voz_paths
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.interfaces.api.health import router as health_router
from voz.interfaces.api.job_events import create_job_events_router
from voz.interfaces.api.media import create_media_router
from voz.interfaces.api.projects import create_projects_router
from voz.interfaces.api.transcription_options import create_transcription_options_router

STATIC_DIRECTORY = Path(__file__).with_name("static")
DATABASE_FILENAME = "voz.sqlite3"


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


def create_app(
    *,
    transcription_options: GetTranscriptionOptions | None = None,
    paths: VozPaths | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build the local VOZ HTTP application.

    Runtime data lives under XDG directories resolved from ``paths``; the
    SQLite schema is migrated to head on the first request lifecycle, never at
    import time. An injected ``engine`` is owned by the caller.
    """
    resolved_paths = resolve_voz_paths() if paths is None else paths
    owns_engine = engine is None
    resolved_engine = (
        create_sqlite_engine(resolved_paths.data / DATABASE_FILENAME)
        if engine is None
        else engine
    )

    class Lifespan:
        """Migrate on startup and dispose an owned engine on shutdown."""

        def __call__(self, _: FastAPI) -> Self:
            return self

        async def __aenter__(self) -> None:
            upgrade_to_head(resolved_engine)

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            if owns_engine:
                resolved_engine.dispose()

    lifespan = Lifespan()

    application = FastAPI(
        title="VOZ",
        description="Local-first transcription workspace API.",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(health_router)
    if transcription_options is None:
        transcription_options = GetTranscriptionOptions(
            LocalTranscriptionModelCatalog(
                FileSystemModelStore(
                    data_root=resolved_paths.data, cache_root=resolved_paths.cache
                )
            ),
            FasterWhisperRuntimeProbe(),
        )
    application.include_router(
        create_transcription_options_router(transcription_options)
    )

    projects = SqliteProjectRepository(resolved_engine)
    application.include_router(
        create_projects_router(CreateProject(projects), ListProjects(projects))
    )
    application.include_router(
        create_media_router(
            ImportMedia(
                media_probe=FfprobeMediaProbe(),
                media_storage=FileSystemMediaStorage(resolved_paths.data),
                media_assets=SqliteMediaAssetRepository(resolved_engine),
            ),
            projects,
            resolved_paths.cache / "uploads",
        )
    )
    application.include_router(
        create_job_events_router(SqliteTranscriptionJobRepository(resolved_engine))
    )
    if STATIC_DIRECTORY.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=STATIC_DIRECTORY, html=True),
            name="web",
        )
    return application


def __getattr__(name: str) -> object:
    # ponytail: keep ``uvicorn voz.bootstrap:app`` working without opening the
    # database at import time.
    if name == "app":
        return create_app()
    raise AttributeError(name)
