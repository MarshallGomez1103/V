"""CreateTranscriptionJob revalidates the option and snapshots the selection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from voz.application.asr_device_selection import (
    ComputeDevice,
    HardwareCapabilities,
)
from voz.application.create_transcription_job import (
    CreateJobError,
    CreateJobFailureCode,
    CreateTranscriptionJob,
)
from voz.application.get_transcription_options import (
    BlockingReason,
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.ports.diarization import DiarizationOptions
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.quality_profiles import ACADEMIC_PROFILE, DEFAULT_PROFILE
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)

NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="local-asr",
    model_id="model",
    display_name="Known model",
    source="publisher/model",
    revision="a" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16,),
        ComputePrecision.INT8,
    ),
    capabilities=frozenset(
        {ModelCapability.TRANSCRIPTION, ModelCapability.TRANSLATION}
    ),
)


class Catalog:
    def __init__(
        self,
        registered: bool = True,
        model: ModelDescriptor = MODEL,
        cloud: bool = False,
    ) -> None:
        self.registered = registered
        self.model = model
        self.cloud = cloud

    def list_models(self) -> tuple[ModelRegistration, ...]:
        status = (
            InstallationStatus.REGISTERED
            if self.registered
            else InstallationStatus.NOT_REGISTERED
        )
        return (
            ModelRegistration(self.model, status, self.registered, cloud=self.cloud),
        )


class Runtime:
    def __init__(self, hardware: HardwareCapabilities | None = None) -> None:
        self.hardware = hardware or HardwareCapabilities(
            frozenset(), frozenset({ComputePrecision.INT8})
        )

    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            True,
            self.hardware,
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


class Projects:
    def __init__(self, *items: Project) -> None:
        self.items = {item.id: item for item in items}

    def add(self, project: Project) -> None:
        self.items[project.id] = project

    def save(self, project: Project) -> None:
        self.items[project.id] = project

    def get(self, project_id: UUID) -> Project | None:
        return self.items.get(project_id)

    def list_all(self) -> Sequence[Project]:
        return tuple(self.items.values())


class MediaAssets:
    def __init__(self, *items: MediaAsset) -> None:
        self.items = {item.id: item for item in items}

    def add(self, media_asset: MediaAsset) -> None:
        self.items[media_asset.id] = media_asset

    def save(self, media_asset: MediaAsset) -> None:
        self.items[media_asset.id] = media_asset

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        return self.items.get(media_asset_id)

    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]:
        return tuple(i for i in self.items.values() if i.project_id == project_id)


class Jobs:
    def __init__(self) -> None:
        self.items: dict[UUID, TranscriptionJob] = {}

    def add(self, job: TranscriptionJob) -> None:
        self.items[job.id] = job

    def save(self, job: TranscriptionJob) -> None:
        self.items[job.id] = job

    def get(self, job_id: UUID) -> TranscriptionJob | None:
        return self.items.get(job_id)

    def list_by_project(self, project_id: UUID) -> Sequence[TranscriptionJob]:
        return tuple(i for i in self.items.values() if i.project_id == project_id)

    def list_by_media_asset(self, media_asset_id: UUID) -> Sequence[TranscriptionJob]:
        return tuple(
            i for i in self.items.values() if i.media_asset_id == media_asset_id
        )

    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        return tuple(i for i in self.items.values() if not i.state.is_terminal)


class Selections:
    def __init__(self) -> None:
        self.items: dict[UUID, JobSelection] = {}

    def add(self, selection: JobSelection) -> None:
        self.items[selection.job_id] = selection

    def get(self, job_id: UUID) -> JobSelection | None:
        return self.items.get(job_id)

    def record_diarization_error(self, job_id: UUID, code: str) -> None:
        del job_id, code

    def replace_diarization(self, job_id: UUID, options: DiarizationOptions) -> None:
        del job_id, options


PROJECT = Project("Demo", id=uuid4(), created_at=NOW)
ASSET = MediaAsset(PROJECT.id, "b" * 64, "tone.wav", 8_044, duration_ms=250)


def use_case(
    *,
    registered: bool = True,
    jobs: Jobs | None = None,
    model: ModelDescriptor = MODEL,
    hardware: HardwareCapabilities | None = None,
    cloud: bool = False,
) -> tuple[CreateTranscriptionJob, Jobs, Selections]:
    jobs = jobs or Jobs()
    selections = Selections()
    create = CreateTranscriptionJob(
        GetTranscriptionOptions(Catalog(registered, model, cloud), Runtime(hardware)),
        Projects(PROJECT),
        MediaAssets(ASSET),
        jobs,
        selections,
        clock=lambda: NOW,
    )
    return create, jobs, selections


def test_creates_queued_job_with_full_reproducible_snapshot() -> None:
    create, jobs, selections = use_case()

    created = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
        language="es",
    )

    assert created.job.state is TranscriptionJobState.QUEUED
    assert created.job.progress == 0.0
    assert jobs.get(created.job.id) == created.job
    snapshot = selections.get(created.job.id)
    assert snapshot == created.selection
    assert snapshot is not None
    assert snapshot.model == MODEL
    assert snapshot.option_id == option_identity(MODEL)
    assert snapshot.language == "es"
    assert snapshot.execution is not None
    assert snapshot.execution.device is ComputeDevice.CPU
    assert snapshot.created_at == NOW


def test_unknown_option_is_rejected_before_persisting() -> None:
    create, jobs, selections = use_case()

    with pytest.raises(CreateJobError) as error:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id="option-v1-missing",
        )

    assert error.value.code is CreateJobFailureCode.OPTION_UNKNOWN
    assert not jobs.items
    assert not selections.items


def test_non_startable_option_reports_current_blocking_reasons() -> None:
    create, jobs, _ = use_case(registered=False)

    with pytest.raises(CreateJobError) as error:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
        )

    assert error.value.code is CreateJobFailureCode.OPTION_NOT_STARTABLE
    assert BlockingReason.MODEL_NOT_REGISTERED in error.value.blocking_reasons
    assert not jobs.items


def test_missing_project_and_foreign_media_asset_are_typed() -> None:
    create, _, _ = use_case()

    with pytest.raises(CreateJobError) as missing_project:
        create.execute(
            project_id=uuid4(),
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
        )
    assert missing_project.value.code is CreateJobFailureCode.PROJECT_NOT_FOUND

    other = Project("Other", id=uuid4(), created_at=NOW)
    create.projects.add(other)
    with pytest.raises(CreateJobError) as foreign_asset:
        create.execute(
            project_id=other.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
        )
    assert foreign_asset.value.code is CreateJobFailureCode.MEDIA_ASSET_NOT_FOUND


def test_second_job_for_active_media_asset_is_rejected() -> None:
    create, jobs, _ = use_case()
    create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
    )

    with pytest.raises(CreateJobError) as error:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
        )
    assert error.value.code is CreateJobFailureCode.JOB_ALREADY_ACTIVE

    (active,) = jobs.items.values()
    jobs.save(active.transition_to(TranscriptionJobState.FAILED, error_code="x"))
    second = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
    )
    assert second.job.id != active.id


LARGE = replace(MODEL, model_id="large-v3")
CUDA = frozenset({ComputePrecision.FLOAT16})
CPU = frozenset({ComputePrecision.INT8})


def _job_in(state: TranscriptionJobState) -> TranscriptionJob:
    return TranscriptionJob(
        id=uuid4(),
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        state=state,
        progress=1.0 if state is TranscriptionJobState.COMPLETED else 0.0,
        created_at=NOW,
        updated_at=NOW,
        error_code="ASR_PROVIDER_ERROR"
        if state is TranscriptionJobState.FAILED
        else None,
    )


@pytest.mark.parametrize("state", list(TranscriptionJobState))
def test_media_asset_admits_a_new_job_only_when_no_job_is_unfinished(
    state: TranscriptionJobState,
) -> None:
    # A CANCELLING job may still use the engine and the files of its media asset,
    # so it blocks admission exactly like a running one until it is CANCELLED.
    create, jobs, _ = use_case()
    jobs.add(_job_in(state))

    def attempt() -> None:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
        )

    if state.is_terminal:
        attempt()
        assert sum(not j.state.is_terminal for j in jobs.items.values()) == 1
        return
    with pytest.raises(CreateJobError) as error:
        attempt()
    assert error.value.code is CreateJobFailureCode.JOB_ALREADY_ACTIVE
    assert len(jobs.items) == 1


def test_a_cancelling_job_blocks_the_media_asset_until_it_is_cancelled() -> None:
    create, jobs, _ = use_case()
    running = _job_in(TranscriptionJobState.TRANSCRIBING)
    jobs.add(running)
    cancelling = running.transition_to(TranscriptionJobState.CANCELLING, at=NOW)
    jobs.save(cancelling)

    with pytest.raises(CreateJobError) as error:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
        )
    assert error.value.code is CreateJobFailureCode.JOB_ALREADY_ACTIVE

    jobs.save(cancelling.transition_to(TranscriptionJobState.CANCELLED, at=NOW))
    created = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
    )
    assert created.job.state is TranscriptionJobState.QUEUED


def _start(create: CreateTranscriptionJob, model: ModelDescriptor) -> None:
    create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(model),
    )


def test_insufficient_free_vram_is_refused_before_persisting() -> None:
    hardware = HardwareCapabilities(
        CUDA, CPU, "GPU", vram_total_mib=8188, vram_free_mib=1200
    )
    create, jobs, selections = use_case(model=LARGE, hardware=hardware)

    with pytest.raises(CreateJobError) as error:
        _start(create, LARGE)

    assert error.value.code is CreateJobFailureCode.INSUFFICIENT_VRAM
    assert error.value.available_mib == 1200
    assert error.value.required_mib == 5000
    assert "RTX" not in error.value.user_message
    assert not jobs.items
    assert not selections.items


def test_insufficient_free_ram_is_refused_on_cpu() -> None:
    hardware = HardwareCapabilities(
        frozenset(), CPU, ram_total_mib=8000, ram_available_mib=900
    )
    create, jobs, _ = use_case(model=LARGE, hardware=hardware)

    with pytest.raises(CreateJobError) as error:
        _start(create, LARGE)

    assert error.value.code is CreateJobFailureCode.INSUFFICIENT_RAM
    assert error.value.available_mib == 900
    assert not jobs.items


def test_enough_free_memory_creates_the_job() -> None:
    hardware = HardwareCapabilities(
        CUDA, CPU, "GPU", vram_total_mib=8188, vram_free_mib=7000
    )
    create, jobs, _ = use_case(model=LARGE, hardware=hardware)

    _start(create, LARGE)

    assert len(jobs.items) == 1


def test_unmeasured_memory_never_blocks() -> None:
    create, jobs, _ = use_case(model=LARGE)

    _start(create, LARGE)

    assert len(jobs.items) == 1


# --- S13.01/S13.02: quality profile and glossary snapshot ---------------------


class Glossaries:
    def __init__(self, terms: tuple[str, ...]) -> None:
        self.terms = terms

    def get(self, project_id: UUID) -> tuple[str, ...]:
        return self.terms if project_id == PROJECT.id else ()

    def put(self, project_id: UUID, terms: tuple[str, ...]) -> None:
        self.terms = terms


def test_default_profile_and_project_glossary_are_frozen_into_the_selection() -> None:
    create, _, selections = use_case()
    glossaries = Glossaries(("Mitocondria", "VOZ"))
    create = replace(create, glossaries=glossaries)

    created = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
    )

    assert created.selection.quality_profile == DEFAULT_PROFILE
    assert created.selection.glossary == ("Mitocondria", "VOZ")
    # Editing the glossary later does not change what this job used.
    glossaries.put(PROJECT.id, ("otro",))
    snapshot = selections.get(created.job.id)
    assert snapshot is not None and snapshot.glossary == ("Mitocondria", "VOZ")


def test_named_profile_is_stored_with_its_effective_parameters() -> None:
    create, _, selections = use_case()

    created = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
        profile="academic",
    )

    assert created.selection.quality_profile == ACADEMIC_PROFILE
    assert created.selection.glossary == ()  # no glossary wired
    stored = selections.get(created.job.id)
    assert stored is not None and stored.quality_profile is not None
    assert stored.quality_profile.vad is not None


def test_unknown_profile_is_rejected_before_persisting() -> None:
    create, jobs, selections = use_case()

    with pytest.raises(CreateJobError) as error:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(MODEL),
            profile="turbo-ultra",
        )

    assert error.value.code is CreateJobFailureCode.QUALITY_PROFILE_UNKNOWN
    assert not jobs.items and not selections.items


def test_job_writer_persists_job_and_selection_in_one_call() -> None:
    written: list[tuple[TranscriptionJob, JobSelection]] = []

    class Writer:
        def add_with_selection(
            self, job: TranscriptionJob, selection: JobSelection
        ) -> None:
            written.append((job, selection))

    create, jobs, selections = use_case()
    create.job_writer = Writer()

    created = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
        language=None,
    )

    assert written == [(created.job, created.selection)]
    assert jobs.items == {} and selections.items == {}


@pytest.mark.parametrize("profile", [None, "default"])
def test_native_asr_snapshots_engine_defaults_without_faster_whisper_recipe(
    profile: str | None,
) -> None:
    native = replace(MODEL, provider_id="sherpa-onnx-asr")
    create, _, _ = use_case(model=native)
    result = create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(native),
        profile=profile,
    )
    assert result.selection.quality_profile is None


@pytest.mark.parametrize("option", ["academic", "prompt", "glossary"])
def test_native_asr_rejects_unsupported_options_before_persisting(option: str) -> None:
    native = replace(MODEL, provider_id="sherpa-onnx-asr")
    create, jobs, selections = use_case(model=native)
    if option == "glossary":
        create = replace(create, glossaries=Glossaries(("Private term",)))
    with pytest.raises(CreateJobError) as failure:
        create.execute(
            project_id=PROJECT.id,
            media_asset_id=ASSET.id,
            option_id=option_identity(native),
            profile="academic" if option == "academic" else None,
            prompt="Private hint" if option == "prompt" else None,
        )
    assert failure.value.code.value == "job_options_unsupported"
    assert not jobs.items and not selections.items
    assert "Private" not in str(failure.value)


# --- V10-07Z: cloud consent fails closed ---------------------------------------


def _start_cloud(create: CreateTranscriptionJob, *, consent: bool = False) -> None:
    create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
        cloud_consent=consent,
    )


def test_cloud_option_without_consent_is_refused_before_persisting() -> None:
    create, jobs, selections = use_case(cloud=True)

    with pytest.raises(CreateJobError) as error:
        _start_cloud(create)

    assert error.value.code is CreateJobFailureCode.CLOUD_CONSENT_REQUIRED
    assert not jobs.items
    assert not selections.items


def test_cloud_option_with_explicit_consent_is_created() -> None:
    create, jobs, _ = use_case(cloud=True)

    _start_cloud(create, consent=True)

    assert len(jobs.items) == 1


def test_local_option_never_needs_consent() -> None:
    create, jobs, _ = use_case()

    _start_cloud(create)

    assert len(jobs.items) == 1
