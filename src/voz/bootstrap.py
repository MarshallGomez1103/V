"""Application composition root.

Framework and infrastructure wiring belongs here so that the domain remains
independent of transport concerns.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib.util import find_spec
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
from voz.application.assign_speakers import AssignProviderSpeakers, AssignSpeakers
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.edit_segment import EditSegmentText
from voz.application.estimate_cloud_cost import EstimateCloudTranscription
from voz.application.export.service import ExportTranscript
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.import_external_model import ImportExternalModel
from voz.application.import_media import ImportMedia
from voz.application.job_runner import JobRunner
from voz.application.library import ListLibrary
from voz.application.model_manager import ListModels, RemoveModel
from voz.application.model_tasks import ModelTaskRunner
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationProvider,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionProvider,
)
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.prepare_inference_audio import PrepareInferenceAudio
from voz.application.project_glossary import ProjectGlossary
from voz.application.projects import (
    CreateProject,
    DeleteProject,
    ListProjects,
    RenameProject,
)
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.application.rediarize import RediarizeTranscript
from voz.application.speakers import (
    AssignSegmentSpeaker,
    ListTranscriptSpeakers,
    MergeSpeakers,
    UpdateSpeaker,
)
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.application.waveform_peaks import GetWaveformPeaks
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.asr.catalog import FasterWhisperModelCatalog
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.asr.options import (
    FasterWhisperRuntimeProbe,
    LocalTranscriptionModelCatalog,
)
from voz.infrastructure.asr.whisper_cpp import WhisperCppProvider
from voz.infrastructure.asr.whisper_cpp_options import (
    WhisperCppRuntimeProbe,
    WhisperCppTranscriptionModelCatalog,
)
from voz.infrastructure.audio.ffmpeg import FfmpegMediaNormalizer
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.audio.waveform_peaks import FfmpegWaveformPeaks
from voz.infrastructure.buzz_cache import BuzzModelCache
from voz.infrastructure.cloud.catalog import (
    CloudRuntimeProbe,
    CloudTranscriptionCatalog,
    CompositeCatalog,
    RoutingRuntimeProbe,
)
from voz.infrastructure.cloud.elevenlabs_pricing import (
    ELEVENLABS_DEFAULT_MODELS,
    ELEVENLABS_PRICES,
)
from voz.infrastructure.cloud.elevenlabs_scribe import (
    ElevenLabsScribeProvider,
    elevenlabs_scribe_descriptor,
)
from voz.infrastructure.cloud.openai_limits import (
    DEFAULT_MODEL_ID as OPENAI_DEFAULT_MODEL_ID,
)
from voz.infrastructure.cloud.openai_limits import openai_descriptors, openai_prices
from voz.infrastructure.cloud.openai_transcription import OpenAITranscriptionProvider
from voz.infrastructure.cloud.openai_transport import urllib_transport
from voz.infrastructure.cloud.provider_info import (
    CLOUD_PROVIDER_INFO,
    CLOUD_PROVIDER_LABELS,
)
from voz.infrastructure.desktop_shortcut import LocalDesktopShortcut
from voz.infrastructure.diarization.availability import SherpaDiarizationAvailability
from voz.infrastructure.diarization.models import DiarizationModelStore
from voz.infrastructure.diarization.sherpa import (
    SherpaOnnxDiarizationProvider,
    default_diarization_threads,
)
from voz.infrastructure.disk_space import ShutilDiskSpace
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.model_registry import ManagedModelCatalog, RoutingModelStore
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.paths import VozPaths, resolve_voz_paths
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.library import SqliteLibraryReader
from voz.infrastructure.persistence.migrate import BACKUPS_DIRECTORY, upgrade_to_head
from voz.infrastructure.persistence.project_glossaries import (
    SqliteProjectGlossaryRepository,
)
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.infrastructure.secrets import ProviderSecrets
from voz.interfaces.api.desktop_shortcut import create_desktop_shortcut_router
from voz.interfaces.api.export import create_export_router
from voz.interfaces.api.health import router as health_router
from voz.interfaces.api.host_guard import LOOPBACK_HOSTS, HostGuardMiddleware
from voz.interfaces.api.job_events import create_job_events_router
from voz.interfaces.api.job_views import job_view as job_view_without_selection
from voz.interfaces.api.jobs import create_jobs_router, job_has_transcript, job_view
from voz.interfaces.api.library import create_library_router
from voz.interfaces.api.media import create_media_router
from voz.interfaces.api.media_stream import create_media_stream_router
from voz.interfaces.api.model_tasks import create_model_tasks_router
from voz.interfaces.api.models import create_models_router
from voz.interfaces.api.projects import create_projects_router
from voz.interfaces.api.providers import create_providers_router
from voz.interfaces.api.quality_profiles import create_quality_profiles_router
from voz.interfaces.api.segments import create_segments_router
from voz.interfaces.api.shutdown import create_shutdown_router
from voz.interfaces.api.speakers import create_speakers_router
from voz.interfaces.api.transcription_options import create_transcription_options_router
from voz.interfaces.api.waveform import create_waveform_router

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
    request_shutdown: Callable[[], None] | None = None,
    allowed_hosts: Iterable[str] = (),
) -> FastAPI:
    """Build the local VOZ HTTP application.

    Runtime data lives under XDG directories resolved from ``paths``; the
    SQLite schema is migrated to head on the first request lifecycle, never at
    import time. An injected ``engine`` is owned by the caller.
    ``request_shutdown`` stops the hosting server (``POST /api/shutdown``);
    without it that endpoint answers 501. Requests must carry a loopback
    ``Host`` (any port) or one of ``allowed_hosts`` (the explicit bind host);
    anything else gets 400 ``host_not_allowed`` (DNS rebinding, ADR-0006).
    """
    resolved_paths = resolve_voz_paths() if paths is None else paths
    owns_engine = engine is None
    resolved_engine = (
        create_sqlite_engine(resolved_paths.data / DATABASE_FILENAME)
        if engine is None
        else engine
    )

    projects = SqliteProjectRepository(resolved_engine)
    glossaries = SqliteProjectGlossaryRepository(resolved_engine)
    media_assets = SqliteMediaAssetRepository(resolved_engine)
    jobs = SqliteTranscriptionJobRepository(resolved_engine)
    selections = SqliteTranscriptionJobSelectionRepository(resolved_engine)
    transcripts = SqliteTranscriptRepository(resolved_engine)
    segments = SqliteSegmentRepository(resolved_engine)
    speakers = SqliteSpeakerRepository(resolved_engine)
    media_storage = FileSystemMediaStorage(resolved_paths.data)
    media_probe = FfprobeMediaProbe()
    disk_space = ShutilDiskSpace(resolved_paths.data)
    model_store = FileSystemModelStore(
        data_root=resolved_paths.data,
        cache_root=resolved_paths.cache,
        disk_space=disk_space,
    )
    whisper_cpp_probe = WhisperCppRuntimeProbe()
    diarization_store = DiarizationModelStore(data_root=resolved_paths.data)
    # The Model Manager lists every local engine under namespaced keys.
    managed_catalog = ManagedModelCatalog(
        whisper_cpp_available=lambda: whisper_cpp_probe.availability().available,
        diarization_runtime_available=lambda: find_spec("sherpa_onnx") is not None,
    )
    managed_store = RoutingModelStore(model_store, diarization_store)
    model_catalog = FasterWhisperModelCatalog()
    buzz_cache = BuzzModelCache()
    model_tasks = ModelTaskRunner(
        managed_catalog,
        managed_store,
        ImportExternalModel(buzz_cache, model_store, model_catalog.entries()),
    )
    # Cloud providers exist only as explicit, key-gated options (ADR-0006);
    # they are never recommended nor used as a fallback.
    secrets = ProviderSecrets(resolved_paths.config)
    cloud_descriptors = (*openai_descriptors(), elevenlabs_scribe_descriptor())
    cloud_probe = CloudRuntimeProbe(secrets, cloud_descriptors)
    if transcription_options is None:
        local_catalogs = (
            LocalTranscriptionModelCatalog(model_store),
            # ponytail: whisper.cpp options appear only when whisper-cli exists.
            *(
                (WhisperCppTranscriptionModelCatalog(model_store),)
                if whisper_cpp_probe.availability().available
                else ()
            ),
        )
        transcription_options = GetTranscriptionOptions(
            CompositeCatalog(
                (
                    *local_catalogs,
                    CloudTranscriptionCatalog(cloud_descriptors, CLOUD_PROVIDER_LABELS),
                )
            ),
            RoutingRuntimeProbe(
                FasterWhisperRuntimeProbe(),
                {
                    "whisper-cpp": whisper_cpp_probe,
                    **{pid: cloud_probe for pid in cloud_probe.provider_ids},
                },
            ),
        )

    # ponytail: one runtime per descriptor, closed on shutdown; the snapshot's
    # execution decision is informative, hardware is re-probed at load time.
    runtimes: dict[ModelDescriptor, LocalAsrRuntime] = {}

    other_providers: dict[str, TranscriptionProvider] = {}

    def provider_for(selection: JobSelection) -> TranscriptionProvider:
        provider_id = selection.model.provider_id
        if provider_id in other_providers:
            return other_providers[provider_id]
        if provider_id == "openai":
            provider: TranscriptionProvider = OpenAITranscriptionProvider(
                secrets=secrets, transport=urllib_transport
            )
        elif provider_id == "elevenlabs":
            provider = ElevenLabsScribeProvider(secrets=secrets)
        elif provider_id == "whisper-cpp":
            binary = whisper_cpp_probe.availability().binary
            if binary is None:
                raise TranscriptionError(
                    TranscriptionFailureCode.PROVIDER_FAILED,
                    "The whisper.cpp executable is not available.",
                )
            provider = WhisperCppProvider(
                binary=binary,
                model_resolver=model_store,
                force_cpu=True,
                temp_root=resolved_paths.cache,
            )
        else:
            return _local_provider(selection)
        other_providers[provider_id] = provider
        return provider

    def _local_provider(selection: JobSelection) -> TranscriptionProvider:
        runtime = runtimes.get(selection.model)
        if runtime is None:
            runtime = create_local_asr_runtime(selection.model, paths=resolved_paths)
            runtimes[selection.model] = runtime
        return runtime.providers.get(selection.model.provider_id)

    def audio_source_for(
        project_id: UUID, media_asset_id: UUID
    ) -> FileSystemInferenceAudioSource:
        return FileSystemInferenceAudioSource(
            resolved_paths.data, project_id, media_asset_id
        )

    diarization_availability = SherpaDiarizationAvailability(diarization_store)
    # ponytail: one cached sherpa engine (~30 MB of ONNX), released on shutdown.
    diarization_engines: list[SherpaOnnxDiarizationProvider] = []

    def diarization_provider_for() -> DiarizationProvider:
        if not diarization_engines:
            model_paths = diarization_store.paths()
            if model_paths is None:
                raise DiarizationError(
                    DiarizationFailureCode.MODEL_UNAVAILABLE,
                    "The local diarization models are not installed.",
                )
            diarization_engines.append(
                SherpaOnnxDiarizationProvider(
                    segmentation_model=model_paths.segmentation,
                    embedding_model=model_paths.embedding,
                    num_threads=default_diarization_threads(),
                )
            )
        return diarization_engines[0]

    def release_asr(selection: JobSelection) -> None:
        # S6.15/S14.07: free ASR memory before diarization; recreated lazily.
        runtime = runtimes.pop(selection.model, None)
        if runtime is not None:
            runtime.close()

    runner = JobRunner(
        jobs=jobs,
        selections=selections,
        media_assets=media_assets,
        transcripts=transcripts,
        segments=segments,
        checkpoints=SqliteTranscriptionCheckpointStore(resolved_engine),
        provider_for=provider_for,
        diarization_provider_for=diarization_provider_for,
        assign_speakers=AssignSpeakers(
            transcripts,
            segments,
            speakers,
            SqliteSpeakerTurnRepository(resolved_engine),
        ),
        assign_provider_speakers=AssignProviderSpeakers(speakers, segments),
        release_asr=release_asr,
        audio_source_for=audio_source_for,
        audio_preparer=PrepareInferenceAudio(
            media_storage=media_storage,
            media_probe=media_probe,
            media_assets=media_assets,
            normalize=NormalizeImportedMedia(
                media_storage=media_storage,
                media_normalization=FfmpegMediaNormalizer(resolved_paths.data),
                disk_space=disk_space,
            ),
        ),
    )

    def view(job: TranscriptionJob) -> dict[str, object]:
        selection = selections.get(job.id)
        if selection is None:
            return job_view_without_selection(job)
        return job_view(
            job, selection, has_transcript=job_has_transcript(job, transcripts)
        )

    class Lifespan:
        """Migrate on startup and dispose an owned engine on shutdown."""

        def __call__(self, _: FastAPI) -> Self:
            return self

        async def __aenter__(self) -> None:
            upgrade_to_head(resolved_engine, resolved_paths.state / BACKUPS_DIRECTORY)
            runner.recover()
            runner.start()
            model_tasks.start()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            model_tasks.stop()
            runner.stop()
            for runtime in runtimes.values():
                runtime.close()
            runtimes.clear()
            for diarization_engine in diarization_engines:
                diarization_engine.close()
            diarization_engines.clear()
            if owns_engine:
                resolved_engine.dispose()

    lifespan = Lifespan()

    application = FastAPI(
        title="VOZ",
        description="Local-first transcription workspace API.",
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(
        HostGuardMiddleware, allowed_hosts=(*LOOPBACK_HOSTS, *allowed_hosts)
    )
    application.include_router(health_router)
    application.include_router(create_shutdown_router(request_shutdown))
    application.include_router(
        create_desktop_shortcut_router(
            LocalDesktopShortcut(state_directory=resolved_paths.state)
        )
    )
    application.include_router(
        create_transcription_options_router(transcription_options)
    )
    application.include_router(
        create_projects_router(
            CreateProject(projects),
            ListProjects(projects),
            ProjectGlossary(
                projects, glossaries, providers=("faster-whisper", "elevenlabs")
            ),
            rename=RenameProject(projects),
            delete=DeleteProject(projects, jobs, media_storage, projects),
        )
    )
    application.include_router(
        create_library_router(ListLibrary(SqliteLibraryReader(resolved_engine)))
    )
    application.include_router(create_quality_profiles_router())
    application.include_router(
        create_media_router(
            ImportMedia(
                media_probe=media_probe,
                media_storage=media_storage,
                media_assets=media_assets,
                disk_space=disk_space,
            ),
            projects,
            resolved_paths.cache / "uploads",
        )
    )
    application.include_router(
        create_jobs_router(
            CreateTranscriptionJob(
                transcription_options,
                projects,
                media_assets,
                jobs,
                selections,
                diarization_availability=diarization_availability,
                glossaries=glossaries,
                job_writer=jobs,
            ),
            jobs,
            selections,
            transcripts,
            segments,
            runner,
            SqliteSpeakerTurnRepository(resolved_engine),
            checkpoints=SqliteTranscriptionCheckpointStore(resolved_engine),
            rediarize=RediarizeTranscript(
                transcripts, jobs, selections, diarization_availability
            ),
        )
    )
    application.include_router(create_job_events_router(jobs, view=view))
    application.include_router(create_media_stream_router(media_assets, media_storage))
    application.include_router(
        create_segments_router(EditSegmentText(segments), segments)
    )
    application.include_router(
        create_speakers_router(
            ListTranscriptSpeakers(transcripts, segments, speakers),
            UpdateSpeaker(segments, speakers),
            MergeSpeakers(segments, speakers),
            AssignSegmentSpeaker(segments, speakers),
        )
    )
    application.include_router(
        create_waveform_router(
            GetWaveformPeaks(
                media_assets,
                FfmpegWaveformPeaks(
                    storage_root=resolved_paths.data,
                    cache_root=resolved_paths.cache,
                    media_storage=media_storage,
                ),
            )
        )
    )
    application.include_router(
        create_models_router(
            ListModels(
                managed_catalog,
                managed_store,
                disk_space=disk_space,
                external=buzz_cache,
            ),
            RemoveModel(managed_catalog, managed_store, jobs, selections),
        )
    )
    application.include_router(create_model_tasks_router(model_tasks))
    application.include_router(
        create_providers_router(
            secrets,
            CLOUD_PROVIDER_INFO,
            EstimateCloudTranscription(
                media_assets,
                {**openai_prices(), **ELEVENLABS_PRICES},
                {"openai": OPENAI_DEFAULT_MODEL_ID, **ELEVENLABS_DEFAULT_MODELS},
            ),
        )
    )
    application.include_router(
        create_export_router(
            ExportTranscript(transcripts, segments, speakers, projects, media_assets)
        )
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
