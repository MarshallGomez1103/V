"""Application composition root.

Framework and infrastructure wiring belongs here so that the domain remains
independent of transport concerns.
"""

from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from voz import __version__
from voz.application.admission import AdmissionGate
from voz.application.asr_device_selection import (
    ExecutionDecision,
    HardwareCapabilities,
    select_execution,
)
from voz.application.assign_speakers import AssignProviderSpeakers, AssignSpeakers
from voz.application.compute_slot import ComputeKind, ComputeSlot, SlotWaitCancelled
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.edit_segment import EditSegmentText
from voz.application.estimate_cloud_cost import EstimateCloudTranscription
from voz.application.export.service import ExportTranscript
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.import_custom_model import ImportCustomModel
from voz.application.import_external_model import ImportExternalModel
from voz.application.import_media import ImportMedia
from voz.application.job_runner import JobRunner
from voz.application.library import ListLibrary
from voz.application.model_manager import ListModels, RemoveModel
from voz.application.model_tasks import ModelTaskRunner
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.custom_models import CustomModelError, CustomModelPlan
from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationProvider,
)
from voz.application.ports.model_installation import CancelCheck
from voz.application.ports.speech_synthesis import SpeechSynthesisProvider
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
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
from voz.application.synthesis import (
    CreateSynthesisJob,
    DeleteSynthesisResult,
    ListSynthesisHistory,
    SynthesisModelCatalog,
)
from voz.application.synthesis.runner import SynthesisRunner
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.application.waveform_peaks import GetWaveformPeaks
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.asr.catalog import FasterWhisperModelCatalog
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.asr.options import (
    FasterWhisperRuntimeProbe,
    LocalTranscriptionModelCatalog,
)
from voz.infrastructure.asr.runtime_cache import SingleRuntimeCache
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
from voz.infrastructure.cloud.compatible_store import FileCompatibleEndpointStore
from voz.infrastructure.cloud.elevenlabs_pricing import (
    ELEVENLABS_DEFAULT_MODELS,
    ELEVENLABS_PRICES,
)
from voz.infrastructure.cloud.elevenlabs_scribe import (
    ElevenLabsScribeProvider,
    elevenlabs_scribe_descriptor,
)
from voz.infrastructure.cloud.openai_compatible import (
    CLOUD_PROVIDER_ID as COMPATIBLE_CLOUD_ID,
)
from voz.infrastructure.cloud.openai_compatible import (
    PROVIDER_IDS as COMPATIBLE_PROVIDER_IDS,
)
from voz.infrastructure.cloud.openai_compatible import (
    CompatibleModels,
    CompatibleRuntimeProbe,
    CompatibleSpeechProvider,
    CompatibleTranscriptionProvider,
    HttpConnectionTester,
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
from voz.infrastructure.custom_model_upload import FileSystemCustomModelUpload
from voz.infrastructure.custom_model_worker import SubprocessModelValidator
from voz.infrastructure.custom_models import CustomModelCatalog, CustomModelStore
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
from voz.infrastructure.model_registry import (
    DIARIZATION_DESCRIPTOR,
    ManagedModelCatalog,
    RoutingModelStore,
)
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
from voz.infrastructure.persistence.synthesis import (
    SqliteSynthesisJobRepository,
    SqliteSynthesizedAudioRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.infrastructure.secrets import ProviderSecrets
from voz.infrastructure.synthesis_storage import FileSystemSynthesisStorage
from voz.infrastructure.tts.installed_models import InstalledTtsModels
from voz.infrastructure.tts.model_store import TtsModelStore
from voz.infrastructure.tts.sherpa_provider import sherpa_tts_provider
from voz.interfaces.api.custom_model_uploads import create_custom_model_uploads_router
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
from voz.interfaces.api.synthesis import create_synthesis_router
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


ASR_IDLE_SECONDS = 60.0
"""Quiet time after which the local ASR runtime hands its memory back."""


class _ResidentProvider:
    """Borrow the cached runtime per call, so an idle close never strands a job."""

    def __init__(
        self,
        provider_id: str,
        borrow: Callable[[], AbstractContextManager[LocalAsrRuntime]],
    ) -> None:
        self.provider_id = provider_id
        self._borrow = borrow

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        with self._borrow() as runtime:
            return runtime.providers.get(self.provider_id).transcribe(
                audio=audio, options=options, cancellation=cancellation
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
    synthesis_providers: Sequence[SpeechSynthesisProvider] | None = None,
    synthesis_catalog: SynthesisModelCatalog | None = None,
) -> FastAPI:
    """Build the local VOZ HTTP application.

    Runtime data lives under XDG directories resolved from ``paths``; the
    SQLite schema is migrated to head on the first request lifecycle, never at
    import time. An injected ``engine`` is owned by the caller.
    ``request_shutdown`` stops the hosting server (``POST /api/shutdown``);
    without it that endpoint answers 501. Requests must carry a loopback
    ``Host`` (any port) or one of ``allowed_hosts`` (the explicit bind host);
    anything else gets 400 ``host_not_allowed`` (DNS rebinding, ADR-0006).
    ``synthesis_providers``/``synthesis_catalog`` replace the TTS engines and
    their installed models (tests pass the fake engine); by default they are
    the sherpa-onnx engine (when ``sherpa_onnx`` is importable) and the models
    installed in the TTS store, both read live after an install or delete.
    """
    resolved_paths = resolve_voz_paths() if paths is None else paths
    owns_engine = engine is None
    resolved_engine = (
        create_sqlite_engine(resolved_paths.data / DATABASE_FILENAME)
        if engine is None
        else engine
    )

    projects = SqliteProjectRepository(resolved_engine)
    # One gate for every check-then-act on active jobs (V0-09c).
    admission = AdmissionGate()
    compute_slot = ComputeSlot()
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
    custom_uploads = FileSystemCustomModelUpload(
        resolved_paths.cache / "custom-model-uploads",
        require_space=model_store.require_custom_space,
    )
    custom_models = CustomModelStore(model_store, cache_root=resolved_paths.cache)
    tts_store = TtsModelStore(
        data_root=resolved_paths.data, custom_manifest=custom_models.manifest
    )

    def sherpa_available() -> bool:  # diarization and TTS share the runtime
        return find_spec("sherpa_onnx") is not None

    # The Model Manager lists every local engine under namespaced keys.
    managed_catalog = ManagedModelCatalog(
        whisper_cpp_available=lambda: whisper_cpp_probe.availability().available,
        diarization_runtime_available=sherpa_available,
        tts_runtime_available=sherpa_available,
        custom_models=custom_models.managed_entries,
    )
    managed_store = RoutingModelStore(
        model_store, diarization_store, tts_store, custom=custom_models
    )
    model_catalog = FasterWhisperModelCatalog()
    buzz_cache = BuzzModelCache()
    # Cloud providers exist only as explicit, key-gated options (ADR-0006);
    # they are never recommended nor used as a fallback.
    secrets = ProviderSecrets(resolved_paths.config)
    cloud_descriptors = (*openai_descriptors(), elevenlabs_scribe_descriptor())
    cloud_probe = CloudRuntimeProbe(secrets, cloud_descriptors)
    # User-declared OpenAI-compatible servers (V4-04): read live from the
    # config file; non-loopback ones are cloud and saved only with consent.
    compatible_store = FileCompatibleEndpointStore(resolved_paths.config)
    compatible_probe = CompatibleRuntimeProbe()
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
                    CompatibleModels(compatible_store, ModelCapability.TRANSCRIPTION),
                    CustomModelCatalog(custom_models, ModelCapability.TRANSCRIPTION),
                )
            ),
            RoutingRuntimeProbe(
                FasterWhisperRuntimeProbe(),
                {
                    "whisper-cpp": whisper_cpp_probe,
                    **{pid: cloud_probe for pid in cloud_probe.provider_ids},
                    **{pid: compatible_probe for pid in COMPATIBLE_PROVIDER_IDS},
                },
            ),
        )

    # ponytail: one resident local runtime; another model closes it first and it
    # is closed after ASR_IDLE_SECONDS without use (next job reloads the model).
    # The snapshot's execution decision is informative, hardware is re-probed
    # at load time.
    runtimes = SingleRuntimeCache[ModelDescriptor, LocalAsrRuntime](
        idle_seconds=ASR_IDLE_SECONDS
    )

    @contextmanager
    def validation_context(cancelled: CancelCheck) -> Generator[None]:
        class Cancellation:
            def is_cancelled(self) -> bool:
                return cancelled()

        try:
            with compute_slot.hold(
                ComputeKind.MODEL_VALIDATION, uuid4(), cancellation=Cancellation()
            ):
                runtimes.release()
                yield
        except SlotWaitCancelled:
            raise CustomModelError(
                "model_installation_cancelled", "The import was cancelled."
            ) from None

    def staging_context(plan: CustomModelPlan) -> AbstractContextManager[None]:
        source = plan.files[0].local_path if plan.files else None
        return custom_uploads.hold_source(source.parent) if source else nullcontext()

    custom_import = ImportCustomModel(
        custom_models,
        SubprocessModelValidator(),
        validation_context=validation_context,
        staging_context=staging_context,
    )
    model_tasks = ModelTaskRunner(
        managed_catalog,
        managed_store,
        ImportExternalModel(buzz_cache, model_store, model_catalog.entries()),
        custom=custom_import,
    )

    other_providers: dict[str, TranscriptionProvider] = {}

    def provider_for(selection: JobSelection) -> TranscriptionProvider:
        provider_id = selection.model.provider_id
        if provider_id in other_providers:
            return other_providers[provider_id]
        if provider_id == "openai":
            provider: TranscriptionProvider = OpenAITranscriptionProvider(
                secrets=secrets, transport=urllib_transport
            )
        elif provider_id in COMPATIBLE_PROVIDER_IDS:
            provider = CompatibleTranscriptionProvider(
                store=compatible_store,
                secrets=secrets,
                transport=urllib_transport,
                cloud=provider_id == COMPATIBLE_CLOUD_ID,
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
        descriptor = selection.model
        return _ResidentProvider(
            descriptor.provider_id,
            lambda: runtimes.use(
                descriptor,
                lambda: create_local_asr_runtime(descriptor, paths=resolved_paths),
            ),
        )

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

    def drop_diarization_engine(descriptor: ModelDescriptor) -> None:
        # The cached engine points at the files RemoveModel just deleted.
        if descriptor.provider_id != DIARIZATION_DESCRIPTOR.provider_id:
            return
        for diarization_engine in diarization_engines:
            diarization_engine.close()
        diarization_engines.clear()

    def release_asr(selection: JobSelection) -> None:
        # S6.15/S14.07: free ASR memory before diarization; recreated lazily.
        runtimes.release()

    # One slot for every heavy job in the process: ASR, diarization and TTS.
    runner = JobRunner(
        compute_slot=compute_slot,
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

    desktop_shortcut = LocalDesktopShortcut(state_directory=resolved_paths.state)

    if synthesis_providers is None:
        # The engines ask their store per call: installs, deletes and endpoint
        # edits are live.
        synthesis_providers = (
            *((sherpa_tts_provider(tts_store.manifest),) if sherpa_available() else ()),
            *(
                CompatibleSpeechProvider(
                    store=compatible_store,
                    secrets=secrets,
                    transport=urllib_transport,
                    cloud=cloud,
                )
                for cloud in (False, True)
            ),
        )
    synthesis_registry = SynthesisProviderRegistry(synthesis_providers)
    tts_catalog = (
        CompositeCatalog(
            (
                InstalledTtsModels(tts_store),
                CompatibleModels(compatible_store, ModelCapability.SYNTHESIS),
                CustomModelCatalog(custom_models, ModelCapability.SYNTHESIS),
            )
        )
        if synthesis_catalog is None
        else synthesis_catalog
    )
    synthesis_jobs = SqliteSynthesisJobRepository(resolved_engine)
    synthesized_audio = SqliteSynthesizedAudioRepository(resolved_engine)
    synthesis_storage = FileSystemSynthesisStorage(resolved_paths.data)
    synthesis_runner = SynthesisRunner(
        jobs=synthesis_jobs,
        audio=synthesized_audio,
        storage=synthesis_storage,
        providers=synthesis_registry,
        catalog=tts_catalog,
        compute_slot=compute_slot,
        release_other_runtimes=runtimes.release,
    )

    class Lifespan:
        """Migrate on startup and dispose an owned engine on shutdown."""

        def __call__(self, _: FastAPI) -> Self:
            return self

        async def __aenter__(self) -> None:
            upgrade_to_head(resolved_engine, resolved_paths.state / BACKUPS_DIRECTORY)
            runner.recover()
            runner.start()
            synthesis_runner.recover()
            synthesis_runner.start()
            # Re-point a broken or pre-V shortcut; never creates one (V1-05).
            desktop_shortcut.refresh()
            model_tasks.start()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            model_tasks.stop()
            custom_uploads.close()
            runner.stop()
            synthesis_runner.stop()
            synthesis_registry.close_all()
            runtimes.close()
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
    application.include_router(create_desktop_shortcut_router(desktop_shortcut))
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
            delete=DeleteProject(
                projects, jobs, media_storage, projects, admission=admission
            ),
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
                admission=admission,
            ),
            jobs,
            selections,
            transcripts,
            segments,
            runner,
            SqliteSpeakerTurnRepository(resolved_engine),
            checkpoints=SqliteTranscriptionCheckpointStore(resolved_engine),
            rediarize=RediarizeTranscript(
                transcripts,
                jobs,
                selections,
                diarization_availability,
                admission=admission,
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
            RemoveModel(
                managed_catalog,
                managed_store,
                jobs,
                selections,
                on_removed=drop_diarization_engine,
                admission=admission,
                synthesis_jobs=synthesis_jobs,
            ),
            custom=custom_import,
        )
    )
    application.include_router(
        create_custom_model_uploads_router(
            custom_uploads,
            custom_import,
            runtime_available=custom_models.runtime_available,
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
            endpoints=compatible_store,
            tester=HttpConnectionTester(urllib_transport),
        )
    )
    application.include_router(
        create_export_router(
            ExportTranscript(transcripts, segments, speakers, projects, media_assets)
        )
    )
    application.include_router(
        create_synthesis_router(
            providers=synthesis_registry,
            catalog=tts_catalog,
            create=CreateSynthesisJob(
                synthesis_registry,
                tts_catalog,
                synthesis_jobs,
                synthesized_audio,
                admission=admission,
            ),
            history=ListSynthesisHistory(synthesis_jobs, synthesized_audio),
            delete=DeleteSynthesisResult(
                synthesis_jobs,
                synthesized_audio,
                synthesis_storage,
                admission=admission,
            ),
            jobs=synthesis_jobs,
            audio=synthesized_audio,
            storage=synthesis_storage,
            runner=synthesis_runner,
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
