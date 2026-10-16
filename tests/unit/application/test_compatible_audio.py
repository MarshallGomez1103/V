"""Compatible orchestration with real use cases and fake persistence/runners."""

from __future__ import annotations

import io
from collections.abc import Callable, Collection
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.compatible_audio import LocalCompatibleAudioService
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.import_media import ImportMedia
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.compatible_audio import (
    CompatibleAudioError,
    CompatibleAudioService,
    CompatibleSpeech,
    CompatibleTranscription,
)
from voz.application.ports.media_probe import (
    MediaProbePort,
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)
from voz.application.ports.media_storage import ImportedOriginal, MediaStoragePort
from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    SegmentRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
)
from voz.application.ports.speech_synthesis import (
    SpeechSynthesisProvider,
    SynthesisLocality,
    SynthesisProviderInfo,
    SynthesisRequirements,
)
from voz.application.ports.synthesis_audio_storage import SynthesisAudioStorage
from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.application.ports.transcription_job_selection import (
    TranscriptionJobSelectionRepository,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.projects import CreateProject
from voz.application.synthesis.create_synthesis_job import (
    CreateSynthesisJob,
    request_hash,
)
from voz.application.synthesis.runner import SynthesisRunner
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.voice import Voice

STT = ModelDescriptor(
    "fake-asr",
    "tiny",
    "Tiny",
    frozenset({ModelCapability.TRANSCRIPTION}),
    source="test/model",
    revision="a" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST, DevicePreference.CPU_ONLY, (), ComputePrecision.INT8
    ),
)
TTS = ModelDescriptor(
    "fake-tts", "voice", "Voice", frozenset({ModelCapability.SYNTHESIS})
)


class Catalog:
    def __init__(self, model: ModelDescriptor) -> None:
        self.items = (ModelRegistration(model, InstallationStatus.REGISTERED, True),)

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return self.items


class Runtime:
    ready = True

    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            self.ready,
            hardware=HardwareCapabilities(
                frozenset(), frozenset({ComputePrecision.INT8})
            ),
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        )


class Harness:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.on_sleep: Callable[[], None] = lambda: None
        self.projects: dict[UUID, Project] = {}
        self.media: dict[UUID, MediaAsset] = {}
        self.jobs: dict[UUID, TranscriptionJob] = {}
        self.tts_jobs: dict[UUID, SynthesisJob] = {}
        self.transcripts: dict[UUID, Transcript] = {}
        self.audio: dict[UUID, SynthesizedAudio] = {}
        self.catalog = Catalog(STT)
        self.tts_catalog = Catalog(TTS)
        self.runtime = Runtime()
        project_repo = MagicMock(spec=ProjectRepository)
        project_repo.add.side_effect = self.add_project
        project_repo.get.side_effect = self.projects.get
        media_repo = MagicMock(spec=MediaAssetRepository)
        media_repo.add.side_effect = self.add_media
        media_repo.get.side_effect = self.media.get
        self.job_repo = MagicMock(spec=TranscriptionJobRepository)
        self.job_repo.add.side_effect = self.add_job
        self.job_repo.get.side_effect = self.jobs.get
        self.job_repo.list_by_media_asset.return_value = ()
        self.selections = MagicMock(spec=TranscriptionJobSelectionRepository)
        self.transcript_repo = MagicMock(spec=TranscriptRepository)
        self.transcript_repo.get.side_effect = self.transcripts.get
        self.segment_repo = MagicMock(spec=SegmentRepository)
        self.segment_repo.list_by_transcript.return_value = ()
        self.media_storage = MagicMock(spec=MediaStoragePort)
        self.media_storage.import_original.side_effect = self.import_original
        self.media_storage.open_original.side_effect = self.open_original
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = MediaProbeResult(
            ("wav",),
            (ProbedMediaStream(0, MediaStreamKind.AUDIO, "pcm_s16le", True),),
            2000,
        )
        self.provider = MagicMock(spec=SpeechSynthesisProvider)
        self.provider.describe.return_value = SynthesisProviderInfo(
            "fake-tts", "Fake TTS"
        )
        self.provider.requirements.return_value = SynthesisRequirements(True)
        self.provider.voices.return_value = (Voice("0", "Voice"),)
        self.provider.synthesize.side_effect = AssertionError("inference forbidden")
        self.tts_job_repo = MagicMock(spec=SynthesisJobRepository)
        self.tts_job_repo.add.side_effect = self.add_tts_job
        self.tts_job_repo.get.side_effect = self.tts_jobs.get
        self.tts_job_repo.find_by_hash.side_effect = self.find_tts_job
        audio_repo = MagicMock(spec=SynthesizedAudioRepository)
        audio_repo.get_by_job.side_effect = self.audio.get
        self.storage = MagicMock(spec=SynthesisAudioStorage)
        self.storage.open_for_reading.side_effect = self.open_audio
        self.runner = MagicMock(spec=JobRunner)
        self.runner.enqueue.side_effect = self.complete_stt
        self.tts_runner = MagicMock(spec=SynthesisRunner)
        self.tts_runner.enqueue.side_effect = self.complete_tts
        self.service = LocalCompatibleAudioService(
            create_project=CreateProject(cast(ProjectRepository, project_repo)),
            import_media=ImportMedia(
                cast(MediaProbePort, probe),
                cast(MediaStoragePort, self.media_storage),
                cast(MediaAssetRepository, media_repo),
            ),
            create_transcription=CreateTranscriptionJob(
                GetTranscriptionOptions(self.catalog, self.runtime),
                cast(ProjectRepository, project_repo),
                cast(MediaAssetRepository, media_repo),
                cast(TranscriptionJobRepository, self.job_repo),
                cast(TranscriptionJobSelectionRepository, self.selections),
            ),
            transcription_runner=cast(JobRunner, self.runner),
            create_synthesis=CreateSynthesisJob(
                SynthesisProviderRegistry(
                    (cast(SpeechSynthesisProvider, self.provider),)
                ),
                self.tts_catalog,
                cast(SynthesisJobRepository, self.tts_job_repo),
                cast(SynthesizedAudioRepository, audio_repo),
            ),
            synthesis_runner=cast(SynthesisRunner, self.tts_runner),
            transcripts=cast(TranscriptRepository, self.transcript_repo),
            segments=cast(SegmentRepository, self.segment_repo),
            synthesis_storage=cast(SynthesisAudioStorage, self.storage),
            monotonic=self.monotonic,
            sleep=self.sleep,
            timeout_seconds=0.2,
        )

    def monotonic(self) -> float:
        return self.elapsed

    def open_original(self, **_kwargs: object) -> io.BytesIO:
        return io.BytesIO(b"fake")

    def open_audio(self, _path: str) -> io.BytesIO:
        return io.BytesIO(b"RIFFfakeWAV")

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds
        self.on_sleep()

    def add_project(self, project: Project) -> None:
        self.projects[project.id] = project

    def add_media(self, asset: MediaAsset) -> None:
        self.media[asset.id] = asset

    def add_job(self, job: TranscriptionJob) -> None:
        self.jobs[job.id] = job

    def add_tts_job(self, job: SynthesisJob) -> None:
        self.tts_jobs[job.id] = job

    def find_tts_job(
        self, digest: str, states: Collection[SynthesisJobState]
    ) -> SynthesisJob | None:
        return next(
            (
                job
                for job in self.tts_jobs.values()
                if job.state in states and request_hash(job.request) == digest
            ),
            None,
        )

    def import_original(
        self, *, source: Path, project_id: UUID, media_asset_id: UUID
    ) -> ImportedOriginal:
        return ImportedOriginal(
            MediaAsset(project_id, "a" * 64, "upload.wav", 4, id=media_asset_id), 4
        )

    def complete_stt(self, job_id: UUID) -> None:
        job = self.jobs[job_id]
        self.jobs[job_id] = replace(
            job, state=TranscriptionJobState.COMPLETED, progress=1.0
        )
        transcript = Transcript(
            job.project_id,
            job.media_asset_id,
            id=transcript_id_for(job_id),
            language="es",
        )
        self.transcripts[transcript.id] = transcript
        self.segment_repo.list_by_transcript.return_value = (
            Segment(transcript.id, 1000, 1500, "world"),
            Segment(transcript.id, 0, 500, "Hello"),
        )

    def complete_tts(self, job_id: UUID) -> None:
        job = self.tts_jobs[job_id]
        self.tts_jobs[job_id] = replace(
            job, state=SynthesisJobState.COMPLETED, chunks_done=job.chunks_total
        )
        self.audio[job_id] = SynthesizedAudio(
            job_id, f"{job_id}/audio.wav", 1000, 16000, 1, "b" * 64, 46
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


def never_cancelled() -> bool:
    return False


def test_port_and_local_model_ids(harness: Harness) -> None:
    service: CompatibleAudioService = harness.service
    models = service.models()
    assert [(model.id, model.owned_by, model.capabilities) for model in models] == [
        ("fake-asr:tiny", "fake-asr", ("transcription",)),
        ("fake-tts:voice", "fake-tts", ("synthesis",)),
    ]
    assert not harness.jobs and not harness.tts_jobs
    harness.provider.synthesize.assert_not_called()


@pytest.mark.parametrize(
    "cloud,remote,installed,files",
    [
        (True, False, True, True),
        (False, True, True, True),
        (False, False, False, True),
        (False, False, True, False),
    ],
)
def test_nonlocal_and_uninstalled_models_are_never_exposed_or_imported(
    harness: Harness, cloud: bool, remote: bool, installed: bool, files: bool
) -> None:
    for catalog in (harness.catalog, harness.tts_catalog):
        catalog.items = (
            replace(
                catalog.items[0],
                cloud=cloud,
                remote=remote,
                installation_status=InstallationStatus.REGISTERED
                if installed
                else InstallationStatus.NOT_REGISTERED,
                files_available=files,
            ),
        )
    assert harness.service.models() == ()
    with pytest.raises(CompatibleAudioError) as caught:
        harness.service.transcribe(
            CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
            cancelled=never_cancelled,
        )
    assert caught.value.code == "model_not_found" and caught.value.param == "model"
    assert not harness.projects
    harness.media_storage.import_original.assert_not_called()
    harness.provider.requirements.assert_not_called()


def test_unavailable_runtimes_and_cloud_tts_are_not_startable(harness: Harness) -> None:
    harness.runtime.ready = False
    harness.provider.requirements.return_value = SynthesisRequirements(False)
    assert harness.service.models() == ()
    harness.provider.requirements.return_value = SynthesisRequirements(True)
    harness.provider.describe.return_value = SynthesisProviderInfo(
        "fake-tts", "Cloud", SynthesisLocality.CLOUD
    )
    assert harness.service.models() == ()


def test_transcribe_reuses_use_cases_and_persists_results(harness: Harness) -> None:
    result = harness.service.transcribe(
        CompatibleTranscription(
            Path("private.wav"), "fake-asr:tiny", language="es", prompt="Style"
        ),
        cancelled=never_cancelled,
    )
    assert result.text == "Hello world" and result.language == "es"
    assert result.duration_seconds == 2.0
    assert [span.start_ms for span in result.segments] == [0, 1000]
    assert (
        len(harness.projects)
        == len(harness.media)
        == len(harness.jobs)
        == len(harness.transcripts)
        == 1
    )
    harness.runner.enqueue.assert_called_once()
    harness.runner.run_job.assert_not_called()
    selection = harness.selections.add.call_args.args[0]
    assert selection.prompt == "Style" and selection.language == "es"


@pytest.mark.parametrize(
    "model,prompt,language,param",
    [
        ("unknown", None, None, "model"),
        ("fake-asr:tiny", "x" * 601, None, "prompt"),
        ("fake-asr:tiny", None, "../private", "language"),
    ],
)
def test_transcription_validation_precedes_import(
    harness: Harness, model: str, prompt: str | None, language: str | None, param: str
) -> None:
    with pytest.raises(CompatibleAudioError) as caught:
        harness.service.transcribe(
            CompatibleTranscription(Path("private.wav"), model, language, prompt),
            cancelled=never_cancelled,
        )
    assert caught.value.param == param
    assert not harness.projects and not harness.media and not harness.jobs


def test_speech_returns_caller_owned_handle_and_reuses_completed_job(
    harness: Harness,
) -> None:
    request = CompatibleSpeech("fake-tts:voice", "Hello", "0", 1.25)
    first = harness.service.speech(request, cancelled=never_cancelled)
    assert first.read() == b"RIFFfakeWAV" and not first.closed
    first.close()
    second = harness.service.speech(request, cancelled=never_cancelled)
    second.close()
    assert len(harness.tts_jobs) == len(harness.audio) == 1
    assert next(iter(harness.tts_jobs.values())).request.speed == 1.25
    harness.tts_runner.enqueue.assert_called_once()
    harness.tts_runner.run_job.assert_not_called()
    harness.provider.synthesize.assert_not_called()


@pytest.mark.parametrize(
    "voice,speed,text,param",
    [
        ("no-voice", 1.0, "Hello", "voice"),
        ("0", float("nan"), "Hello", "speed"),
        ("0", 3.0, "Hello", "speed"),
        ("0", True, "Hello", "speed"),
        ("0", 1.0, " ", "input"),
    ],
)
def test_speech_validation_creates_no_job(
    harness: Harness, voice: str, speed: float, text: str, param: str
) -> None:
    with pytest.raises(CompatibleAudioError) as caught:
        harness.service.speech(
            CompatibleSpeech("fake-tts:voice", text, voice, speed),
            cancelled=never_cancelled,
        )
    assert caught.value.param == param and not harness.tts_jobs


@pytest.mark.parametrize("synthesis", [False, True])
@pytest.mark.parametrize("disconnect", [False, True])
def test_bounded_wait_cancels_only_own_job(
    harness: Harness, synthesis: bool, disconnect: bool
) -> None:
    runner = harness.tts_runner if synthesis else harness.runner
    runner.enqueue.side_effect = None

    def cancelled() -> bool:
        return disconnect and harness.elapsed > 0

    with pytest.raises(CompatibleAudioError) as caught:
        if synthesis:
            harness.service.speech(
                CompatibleSpeech("fake-tts:voice", "Hello", "0"), cancelled=cancelled
            )
        else:
            harness.service.transcribe(
                CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
                cancelled=cancelled,
            )
    assert caught.value.code == (
        "request_cancelled" if disconnect else "request_timeout"
    )
    assert caught.value.status == (499 if disconnect else 504)
    jobs = harness.tts_jobs if synthesis else harness.jobs
    runner.cancel.assert_called_once_with(next(iter(jobs)))
    assert harness.elapsed <= 0.2


@pytest.mark.parametrize("disconnect", [False, True])
def test_reused_inflight_speech_is_never_enqueued_or_cancelled(
    harness: Harness, disconnect: bool
) -> None:
    existing = harness.service.create_synthesis.execute(
        text="Hello", provider_id="fake-tts", model_id="voice", voice_id="0"
    )

    def cancelled() -> bool:
        return disconnect and harness.elapsed > 0

    with pytest.raises(CompatibleAudioError):
        harness.service.speech(
            CompatibleSpeech("fake-tts:voice", "Hello", "0"), cancelled=cancelled
        )
    assert (
        len(harness.tts_jobs) == 1 and harness.tts_jobs[existing.job.id] == existing.job
    )
    harness.tts_runner.enqueue.assert_not_called()
    harness.tts_runner.cancel.assert_not_called()


def test_already_disconnected_request_creates_nothing(harness: Harness) -> None:
    with pytest.raises(CompatibleAudioError):
        harness.service.transcribe(
            CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
            cancelled=lambda: True,
        )
    assert not harness.projects


@pytest.mark.parametrize("synthesis", [False, True])
def test_unexpected_failures_are_fixed_safe_errors_and_cancel_owned_job(
    harness: Harness, synthesis: bool
) -> None:
    runner = harness.tts_runner if synthesis else harness.runner
    runner.enqueue.side_effect = RuntimeError("/private/file secret-provider-token")
    with pytest.raises(CompatibleAudioError) as caught:
        if synthesis:
            harness.service.speech(
                CompatibleSpeech("fake-tts:voice", "Hello", "0"),
                cancelled=never_cancelled,
            )
        else:
            harness.service.transcribe(
                CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
                cancelled=never_cancelled,
            )
    assert caught.value.code == "audio_processing_failed" and caught.value.status == 500
    assert "/private" not in str(caught.value) and "secret" not in str(caught.value)
    runner.cancel.assert_called_once()


@pytest.mark.parametrize("timeout", [0, -1, 301, float("inf"), float("nan"), True])
def test_deadline_configuration_is_bounded(harness: Harness, timeout: float) -> None:
    with pytest.raises(ValueError):
        replace(harness.service, timeout_seconds=timeout)


@pytest.mark.parametrize("synthesis", [False, True])
@pytest.mark.parametrize("cancelled_job", [False, True])
def test_terminal_failure_is_not_success_or_raw_provider_error(
    harness: Harness, synthesis: bool, cancelled_job: bool
) -> None:
    def finish(job_id: UUID) -> None:
        if synthesis:
            harness.tts_jobs[job_id] = replace(
                harness.tts_jobs[job_id],
                state=SynthesisJobState.CANCELLED
                if cancelled_job
                else SynthesisJobState.FAILED,
                error_code=None if cancelled_job else "/private/provider-secret",
            )
        else:
            harness.jobs[job_id] = replace(
                harness.jobs[job_id],
                state=TranscriptionJobState.CANCELLED
                if cancelled_job
                else TranscriptionJobState.FAILED,
                error_code=None if cancelled_job else "/private/provider-secret",
            )

    runner = harness.tts_runner if synthesis else harness.runner
    runner.enqueue.side_effect = finish
    with pytest.raises(CompatibleAudioError) as caught:
        if synthesis:
            harness.service.speech(
                CompatibleSpeech("fake-tts:voice", "Hello", "0"),
                cancelled=never_cancelled,
            )
        else:
            harness.service.transcribe(
                CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
                cancelled=never_cancelled,
            )
    assert caught.value.code == (
        "request_cancelled" if cancelled_job else "audio_processing_failed"
    )
    assert "/private" not in str(caught.value) and "secret" not in str(caught.value)
    runner.cancel.assert_not_called()


@pytest.mark.parametrize("synthesis", [False, True])
def test_completed_job_without_result_is_not_success(
    harness: Harness, synthesis: bool
) -> None:
    def finish(job_id: UUID) -> None:
        if synthesis:
            harness.complete_tts(job_id)
            harness.audio.clear()
        else:
            harness.complete_stt(job_id)
            harness.transcripts.clear()

    (harness.tts_runner if synthesis else harness.runner).enqueue.side_effect = finish
    with pytest.raises(CompatibleAudioError) as caught:
        if synthesis:
            harness.service.speech(
                CompatibleSpeech("fake-tts:voice", "Hello", "0"),
                cancelled=never_cancelled,
            )
        else:
            harness.service.transcribe(
                CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
                cancelled=never_cancelled,
            )
    assert caught.value.code == "audio_processing_failed"
    harness.storage.open_for_reading.assert_not_called()


def test_reused_inflight_speech_can_complete_without_owning_it(
    harness: Harness,
) -> None:
    existing = harness.service.create_synthesis.execute(
        text="Hello", provider_id="fake-tts", model_id="voice", voice_id="0"
    )

    def finish() -> None:
        harness.complete_tts(existing.job.id)

    harness.on_sleep = finish
    handle = harness.service.speech(
        CompatibleSpeech("fake-tts:voice", "Hello", "0"), cancelled=never_cancelled
    )
    handle.close()
    harness.tts_runner.enqueue.assert_not_called()
    harness.tts_runner.cancel.assert_not_called()


def test_cancellation_after_open_closes_handle(harness: Harness) -> None:
    handle = io.BytesIO(b"RIFFfakeWAV")

    def open_audio(_path: str) -> io.BytesIO:
        harness.elapsed = 1
        return handle

    harness.storage.open_for_reading.side_effect = open_audio
    with pytest.raises(CompatibleAudioError) as caught:
        harness.service.speech(
            CompatibleSpeech("fake-tts:voice", "Hello", "0"), cancelled=never_cancelled
        )
    assert caught.value.code == "request_timeout" and handle.closed
    harness.tts_runner.cancel.assert_not_called()


def test_import_timeout_preserves_history_without_creating_job(
    harness: Harness,
) -> None:
    def import_original(
        *, source: Path, project_id: UUID, media_asset_id: UUID
    ) -> ImportedOriginal:
        harness.elapsed = 1
        return harness.import_original(
            source=source, project_id=project_id, media_asset_id=media_asset_id
        )

    harness.media_storage.import_original.side_effect = import_original
    with pytest.raises(CompatibleAudioError) as caught:
        harness.service.transcribe(
            CompatibleTranscription(Path("private.wav"), "fake-asr:tiny"),
            cancelled=never_cancelled,
        )
    assert caught.value.code == "request_timeout"
    assert len(harness.projects) == len(harness.media) == 1 and not harness.jobs
    harness.runner.enqueue.assert_not_called()


def test_model_listing_error_is_safe(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> tuple[ModelRegistration, ...]:
        raise OSError("/private/catalog secret")

    monkeypatch.setattr(harness.catalog, "list_models", unavailable)
    with pytest.raises(CompatibleAudioError) as caught:
        harness.service.models()
    assert caught.value.status == 503 and "/private" not in str(caught.value)
