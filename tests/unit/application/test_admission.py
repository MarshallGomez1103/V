"""V0-09c: check-then-act on active jobs is atomic under one admission gate.

Each test holds the first operation *inside* its critical section and starts the
second one from there. With the gate, the second blocks until the first is done;
without it, the second would finish within the probe window and interleave. The
probe only waits on the negative path (``JOIN_PROBE`` seconds), never on success.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from test_create_transcription_job import (
    ASSET,
    MODEL,
    NOW,
    PROJECT,
    Catalog,
    Jobs,
    MediaAssets,
    Projects,
    Runtime,
    Selections,
)

from voz.application.admission import AdmissionGate
from voz.application.create_transcription_job import (
    CreateJobError,
    CreateJobFailureCode,
    CreateTranscriptionJob,
)
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.job_runner import transcript_id_for
from voz.application.model_manager import (
    ModelManagementError,
    ModelManagementFailureCode,
    RemoveModel,
)
from voz.application.ports.diarization import DiarizationOptions
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.application.projects import DeleteProject, ProjectBusy
from voz.application.rediarize import RediarizeTranscript
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.model_registry import ManagedModel

JOIN_PROBE = 0.5


class Outcome:
    """Result or error of an operation run on its own thread."""

    def __init__(self, operation: Callable[[], object]) -> None:
        self.value: object = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(operation,))

    def _run(self, operation: Callable[[], object]) -> None:
        try:
            self.value = operation()
        except BaseException as error:
            self.error = error

    def start_and_probe(self) -> bool:
        """Start; True when it already finished (nothing held it back)."""
        self._thread.start()
        self._thread.join(JOIN_PROBE)
        return not self._thread.is_alive()

    def finish(self) -> None:
        self._thread.join(10)
        assert not self._thread.is_alive()


def build_create(
    gate: AdmissionGate,
    *,
    jobs: Jobs,
    catalog: Catalog | None = None,
    projects: Projects | None = None,
) -> CreateTranscriptionJob:
    return CreateTranscriptionJob(
        GetTranscriptionOptions(catalog or Catalog(), Runtime()),
        projects or Projects(PROJECT),
        MediaAssets(ASSET),
        jobs,
        Selections(),
        clock=lambda: NOW,
        admission=gate,
    )


def post(create: CreateTranscriptionJob) -> Callable[[], object]:
    return lambda: create.execute(
        project_id=PROJECT.id,
        media_asset_id=ASSET.id,
        option_id=option_identity(MODEL),
    )


def active(jobs: Jobs) -> list[TranscriptionJob]:
    return [job for job in jobs.items.values() if job.state.is_processable]


def test_two_concurrent_posts_for_one_media_create_one_job() -> None:
    gate = AdmissionGate()
    second: list[Outcome] = []

    class HoldingJobs(Jobs):
        """The first request pauses right after its active-job check."""

        started = False

        def list_by_media_asset(
            self, media_asset_id: UUID
        ) -> Sequence[TranscriptionJob]:
            seen = super().list_by_media_asset(media_asset_id)
            if not self.started:
                self.started = True
                second.append(Outcome(post(create)))
                assert not second[0].start_and_probe()  # blocked by the gate
            return seen

    jobs = HoldingJobs()
    create = build_create(gate, jobs=jobs)

    first = post(create)()
    second[0].finish()

    assert first is not None
    assert isinstance(second[0].error, CreateJobError)
    assert second[0].error.code is CreateJobFailureCode.JOB_ALREADY_ACTIVE
    assert len(active(jobs)) == 1


def test_job_created_while_a_project_is_deleted_is_refused_not_lost() -> None:
    gate = AdmissionGate()
    jobs, projects = Jobs(), Projects(PROJECT)
    create = build_create(gate, jobs=jobs, projects=projects)
    late = Outcome(post(create))
    finished_early: list[bool] = []

    class Files:
        def delete_project_files(self, project_id: UUID) -> None:
            finished_early.append(late.start_and_probe())  # POST arrives mid-delete

    class Records:
        def delete_project(self, project_id: UUID) -> bool:
            projects.items.pop(project_id)
            for job_id in [j.id for j in jobs.list_by_project(project_id)]:
                jobs.items.pop(job_id)  # ON DELETE CASCADE
            return True

    DeleteProject(projects, jobs, Files(), Records(), admission=gate).execute(
        PROJECT.id
    )
    late.finish()

    assert finished_early == [False]  # the POST waited for the delete
    assert isinstance(late.error, CreateJobError)
    assert late.error.code is CreateJobFailureCode.PROJECT_NOT_FOUND
    assert not jobs.items  # no 201 for a job that vanished


def test_project_deleted_while_a_job_is_created_is_busy() -> None:
    gate = AdmissionGate()
    projects = Projects(PROJECT)
    deletion: list[Outcome] = []

    class Files:
        def delete_project_files(self, project_id: UUID) -> None:
            raise AssertionError("the project is busy: nothing must be erased")

    class Records:
        def delete_project(self, project_id: UUID) -> bool:
            raise AssertionError("the project is busy: no row may be erased")

    class HoldingJobs(Jobs):
        """The POST pauses after its checks; a DELETE arrives meanwhile."""

        started = False

        def list_by_media_asset(
            self, media_asset_id: UUID
        ) -> Sequence[TranscriptionJob]:
            seen = super().list_by_media_asset(media_asset_id)
            if not self.started:
                self.started = True
                deletion.append(
                    Outcome(
                        lambda: DeleteProject(
                            projects, self, Files(), Records(), admission=gate
                        ).execute(PROJECT.id)
                    )
                )
                assert not deletion[0].start_and_probe()
            return seen

    jobs = HoldingJobs()
    created = post(build_create(gate, jobs=jobs, projects=projects))()
    deletion[0].finish()

    assert created is not None
    assert isinstance(deletion[0].error, ProjectBusy)
    assert PROJECT.id in projects.items


class StoreWithCatalog:
    """A model store whose catalog stops offering the model once removed."""

    def __init__(self) -> None:
        self.removed: list[object] = []

    def is_installed(self, descriptor: object) -> bool:
        return descriptor not in self.removed

    def disk_usage(self, descriptor: object) -> int:
        return 1

    def reclaimable_usage(self, descriptor: object) -> int:
        return 1

    def remove(self, descriptor: object) -> int:
        self.removed.append(descriptor)
        return 1


class InstalledOnlyCatalog(Catalog):
    def __init__(self, store: StoreWithCatalog) -> None:
        super().__init__()
        self.store = store

    def list_models(self) -> tuple[ModelRegistration, ...]:
        status = (
            InstallationStatus.NOT_REGISTERED
            if MODEL in self.store.removed
            else InstallationStatus.REGISTERED
        )
        return (ModelRegistration(MODEL, status, status.name == "REGISTERED"),)

    def entries(self) -> tuple[ManagedModel, ...]:
        return (ManagedModel(MODEL, (), "MIT", True),)


def test_job_created_while_the_asr_model_is_removed_is_refused_not_orphaned() -> None:
    gate = AdmissionGate()
    store = StoreWithCatalog()
    catalog = InstalledOnlyCatalog(store)
    selections = Selections()
    jobs = Jobs()
    create = build_create(gate, jobs=jobs, catalog=catalog)
    late = Outcome(post(create))
    finished_early: list[bool] = []

    class ProbingJobs(Jobs):
        """RemoveModel's in-use check; the POST arrives right after it."""

        def list_recoverable(self) -> Sequence[TranscriptionJob]:
            result = super().list_recoverable()
            finished_early.append(late.start_and_probe())
            return result

    probing = ProbingJobs()
    probing.items = jobs.items  # same store, so the POST sees what RemoveModel sees
    key = f"{MODEL.provider_id}:{MODEL.model_id}"

    RemoveModel(catalog, store, probing, selections, admission=gate).execute(key, key)
    late.finish()

    assert finished_early == [False]
    assert isinstance(late.error, CreateJobError)
    assert late.error.code in {
        CreateJobFailureCode.OPTION_UNKNOWN,
        CreateJobFailureCode.OPTION_NOT_STARTABLE,
    }
    assert not active(jobs)


def test_model_in_use_by_a_job_created_first_is_not_removed() -> None:
    gate = AdmissionGate()
    store = StoreWithCatalog()
    catalog = InstalledOnlyCatalog(store)
    removal: list[Outcome] = []
    key = f"{MODEL.provider_id}:{MODEL.model_id}"
    selections = Selections()

    class HoldingJobs(Jobs):
        started = False

        def list_by_media_asset(
            self, media_asset_id: UUID
        ) -> Sequence[TranscriptionJob]:
            seen = super().list_by_media_asset(media_asset_id)
            if not self.started:
                self.started = True
                removal.append(
                    Outcome(
                        lambda: RemoveModel(
                            catalog, store, self, selections, admission=gate
                        ).execute(key, key)
                    )
                )
                assert not removal[0].start_and_probe()
            return seen

    jobs = HoldingJobs()
    create = build_create(gate, jobs=jobs, catalog=catalog)
    create.selections = selections  # RemoveModel reads the job's snapshot

    post(create)()
    removal[0].finish()

    assert isinstance(removal[0].error, ModelManagementError)
    assert removal[0].error.code is ModelManagementFailureCode.IN_USE
    assert store.removed == []


class Transcripts:
    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript

    def get(self, transcript_id: UUID) -> Transcript | None:
        return self.transcript if transcript_id == self.transcript.id else None


@dataclass
class HookedAvailability:
    """Runs ``on_check`` inside the re-diarization's critical section."""

    on_check: Callable[[], None]

    def runtime_available(self) -> bool:
        self.on_check()
        return True

    def models_installed(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True


def test_job_created_while_a_transcript_is_rediarized_sees_it_active() -> None:
    gate = AdmissionGate()
    jobs = Jobs()
    owner = TranscriptionJob.create(
        job_id=uuid4(), project_id=PROJECT.id, media_asset_id=ASSET.id, now=NOW
    )
    done = owner
    for state in (
        TranscriptionJobState.CANCELLING,
        TranscriptionJobState.CANCELLED,
    ):
        done = done.transition_to(state, at=NOW)
    jobs.add(done)
    selections = Selections()
    selections.add(
        JobSelection(
            job_id=owner.id,
            option_id=option_identity(MODEL),
            model=MODEL,
            execution=None,
            language=None,
            created_at=NOW,
            diarization=DiarizationOptions(),
        )
    )
    transcript = Transcript(PROJECT.id, ASSET.id, id=transcript_id_for(owner.id))
    create = build_create(gate, jobs=jobs)
    late = Outcome(post(create))
    finished_early: list[bool] = []
    rediarize = RediarizeTranscript(
        Transcripts(transcript),  # type: ignore[arg-type]
        jobs,
        selections,
        HookedAvailability(lambda: finished_early.append(late.start_and_probe())),
        clock=lambda: NOW,
        admission=gate,
    )

    rediarize.execute(transcript.id, DiarizationOptions())
    late.finish()

    assert finished_early == [False]
    assert isinstance(late.error, CreateJobError)
    assert late.error.code is CreateJobFailureCode.JOB_ALREADY_ACTIVE
    assert len(active(jobs)) == 1


def test_use_cases_work_without_an_explicit_gate() -> None:
    jobs = Jobs()
    create = CreateTranscriptionJob(
        GetTranscriptionOptions(Catalog(), Runtime()),
        Projects(PROJECT),
        MediaAssets(ASSET),
        jobs,
        Selections(),
        clock=lambda: NOW,
    )

    assert post(create)() is not None
    with pytest.raises(CreateJobError):
        post(create)()
