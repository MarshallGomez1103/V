"""Project queue routes over real SQLite repositories, without the full app."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.job_runner import JobRunner
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.transcription_queue import (
    CancelTranscriptionQueue,
    CreateTranscriptionQueue,
    GetTranscriptionQueue,
)
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
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.infrastructure.persistence.transcription_queues import (
    SqliteTranscriptionQueueRepository,
)
from voz.interfaces.api.transcription_queue import create_transcription_queue_router

T0 = datetime(2026, 11, 11, 12, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16,),
        ComputePrecision.INT8,
    ),
)
OPTION = option_identity(MODEL)


class _Catalog:
    def __init__(self, cloud: bool) -> None:
        self.cloud = cloud

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                MODEL, InstallationStatus.REGISTERED, True, cloud=self.cloud
            ),
        )


class _Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        del provider_id
        return RuntimeAvailability(
            True,
            HardwareCapabilities(frozenset(), frozenset({ComputePrecision.INT8})),
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


def _never(*args: object) -> NoReturn:
    raise AssertionError("the worker is not started in these tests")


class _NoPreparer:
    def prepare(
        self,
        *,
        project_id: object,
        media_asset_id: object,
        cancellation: object = None,
        on_progress: object = None,
    ) -> None:
        _never()


class Env:
    def __init__(self, tmp_path: Path, *, cloud: bool = False) -> None:
        self.engine: Engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
        metadata.create_all(self.engine)
        self.projects = SqliteProjectRepository(self.engine)
        self.assets = SqliteMediaAssetRepository(self.engine)
        self.jobs = SqliteTranscriptionJobRepository(self.engine)
        queues = SqliteTranscriptionQueueRepository(self.engine)
        transcripts = SqliteTranscriptRepository(self.engine)
        create_job = CreateTranscriptionJob(
            GetTranscriptionOptions(_Catalog(cloud), _Runtime()),
            self.projects,
            self.assets,
            self.jobs,
            SqliteTranscriptionJobSelectionRepository(self.engine),
            job_writer=self.jobs,
        )
        # The worker is never started: queued jobs stay queued and cancel is instant.
        self.runner = JobRunner(
            jobs=self.jobs,
            selections=SqliteTranscriptionJobSelectionRepository(self.engine),
            media_assets=self.assets,
            transcripts=transcripts,
            segments=SqliteSegmentRepository(self.engine),
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=_never,
            audio_source_for=_never,
            audio_preparer=_NoPreparer(),
        )
        app = FastAPI()
        app.include_router(
            create_transcription_queue_router(
                CreateTranscriptionQueue(create_job, self.assets, self.jobs, queues),
                GetTranscriptionQueue(
                    self.projects, queues, self.jobs, self.assets, transcripts
                ),
                CancelTranscriptionQueue(queues, self.jobs, self.runner),
                self.runner,
            )
        )
        self.client = TestClient(app)

    def project(self, durations: list[int | None]) -> Project:
        project = Project("Curso")
        self.projects.add(project)
        for index, duration in enumerate(durations):
            self.assets.add(
                MediaAsset(
                    project.id,
                    f"{index:064x}",
                    f"clase-{index}.mp3",
                    10,
                    duration_ms=duration,
                    created_at=T0 + timedelta(seconds=index),
                )
            )
        return project

    def start(self, project: Project, **body: object) -> httpx.Response:
        return self.client.post(
            f"/api/projects/{project.id}/transcription-queue",
            json={"option_id": OPTION, **body},
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_post_creates_the_queue_and_enqueues_jobs_in_position_order(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued: list[UUID] = []

    def spy(self: JobRunner, job_id: UUID) -> None:
        enqueued.append(job_id)

    monkeypatch.setattr(JobRunner, "enqueue", spy)
    project = env.project([1_000, 2_000, 3_000])

    response = env.start(project, language="es")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {
        "id",
        "project_id",
        "created_at",
        "state",
        "progress",
        "counts",
        "items",
        "skipped",
    }
    assert body["state"] == "running"
    assert body["progress"] == 0.0
    assert body["counts"] == {
        "total": 3,
        "pending": 3,
        "running": 0,
        "done": 0,
        "error": 0,
        "cancelled": 0,
        "skipped": 0,
    }
    assert [item["position"] for item in body["items"]] == [0, 1, 2]
    assert [item["filename"] for item in body["items"]] == [
        "clase-0.mp3",
        "clase-1.mp3",
        "clase-2.mp3",
    ]
    assert {item["status"] for item in body["items"]} == {"pending"}
    assert {item["job_state"] for item in body["items"]} == {"QUEUED"}
    assert set(body["items"][0]) == {
        "position",
        "media_asset_id",
        "filename",
        "job_id",
        "status",
        "job_state",
        "progress",
        "error_code",
        "transcript_id",
    }
    assert [str(job_id) for job_id in enqueued] == [i["job_id"] for i in body["items"]]


def test_post_reports_skipped_recordings_with_reasons(env: Env) -> None:
    project = env.project([1_000, None, 3_000])
    asset = env.assets.list_by_project(project.id)[2]
    env.jobs.add(
        TranscriptionJob(
            id=uuid4(),
            project_id=project.id,
            media_asset_id=asset.id,
            state=TranscriptionJobState.COMPLETED,
            progress=1.0,
            created_at=T0,
            updated_at=T0,
        )
    )

    body = env.start(project).json()

    assert body["counts"]["total"] == 1
    assert body["counts"]["skipped"] == 2
    assert [(s["filename"], s["reason"]) for s in body["skipped"]] == [
        ("clase-1.mp3", "duration_unknown"),
        ("clase-2.mp3", "already_transcribed"),
    ]
    assert set(body["skipped"][0]) == {"media_asset_id", "filename", "reason"}


def test_post_conflicts_and_empty_queue(env: Env) -> None:
    project = env.project([None])

    empty = env.start(project)
    assert empty.status_code == 409
    detail = empty.json()["detail"]
    assert detail["code"] == "transcription_queue_empty"
    assert [(s["filename"], s["reason"]) for s in detail["skipped"]] == [
        ("clase-0.mp3", "duration_unknown")
    ]

    other = env.project([1_000])
    assert env.start(other).status_code == 201
    again = env.start(other)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "transcription_queue_active"


def test_post_rejects_cloud_option_without_creating_rows(tmp_path: Path) -> None:
    env = Env(tmp_path, cloud=True)
    project = env.project([1_000])

    response = env.start(project)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "transcription_queue_cloud_unsupported"
    assert env.jobs.list_by_project(project.id) == ()
    assert env.client.get(f"/api/projects/{project.id}/transcription-queue").json() == {
        "queue": None
    }


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"option_id": "option-v1-missing"}, 404, "option_unknown"),
        ({"option_id": OPTION, "profile": "nope"}, 422, "quality_profile_unknown"),
        ({"option_id": OPTION, "prompt": "x" * 601}, 422, "job_prompt_invalid"),
        (
            {"option_id": OPTION, "diarization": {"enabled": "yes"}},
            422,
            "diarization_options_invalid",
        ),
        (
            {"option_id": OPTION, "diarization": {"enabled": True}},
            409,
            "diarization_unavailable",
        ),
    ],
)
def test_post_validates_options_like_a_single_job(
    env: Env, body: dict[str, object], status: int, code: str
) -> None:
    project = env.project([1_000])

    response = env.client.post(
        f"/api/projects/{project.id}/transcription-queue", json=body
    )

    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert env.jobs.list_by_project(project.id) == ()


def test_post_and_get_on_unknown_project_are_404(env: Env) -> None:
    unknown = uuid4()

    posted = env.client.post(
        f"/api/projects/{unknown}/transcription-queue", json={"option_id": OPTION}
    )
    read = env.client.get(f"/api/projects/{unknown}/transcription-queue")

    assert posted.status_code == read.status_code == 404
    assert posted.json()["detail"]["code"] == "project_not_found"
    assert read.json()["detail"]["code"] == "project_not_found"


def test_get_returns_null_then_the_latest_queue(env: Env) -> None:
    project = env.project([1_000, 2_000])
    url = f"/api/projects/{project.id}/transcription-queue"
    assert env.client.get(url).json() == {"queue": None}

    created = env.start(project).json()

    assert env.client.get(url).json() == {"queue": created}


def test_cancel_cancels_every_pending_item_and_a_second_cancel_conflicts(
    env: Env,
) -> None:
    project = env.project([1_000, 2_000, 3_000])
    queue = env.start(project).json()

    cancelled = env.client.post(f"/api/transcription-queues/{queue['id']}/cancel")

    assert cancelled.status_code == 202, cancelled.text
    body = cancelled.json()
    assert body["state"] == "finished"
    assert {item["status"] for item in body["items"]} == {"cancelled"}
    assert body["counts"]["cancelled"] == 3
    again = env.client.post(f"/api/transcription-queues/{queue['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "transcription_queue_finished"
    # A finished queue frees the project: its recordings are eligible again.
    assert env.start(project).status_code == 201


def test_cancel_unknown_queue_is_404(env: Env) -> None:
    response = env.client.post(f"/api/transcription-queues/{uuid4()}/cancel")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "transcription_queue_not_found"


def test_responses_never_contain_host_paths(env: Env, tmp_path: Path) -> None:
    project = env.project([1_000, None])
    created = env.start(project)
    queue = created.json()
    reads = [
        created.text,
        env.client.get(f"/api/projects/{project.id}/transcription-queue").text,
        env.client.post(f"/api/transcription-queues/{queue['id']}/cancel").text,
        env.start(project).text,
    ]

    for text in reads:
        assert str(tmp_path) not in text
        assert str(Path.home()) not in text
        json.loads(text)
