"""``GET /api/projects/{id}/recordings`` over real SQLite repositories."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from voz.application.job_runner import transcript_id_for
from voz.application.list_recordings import ListRecordings
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.interfaces.api.recordings import create_recordings_router

T0 = datetime(2026, 10, 1, 12, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="large-v3",
    display_name="Large v3",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/model",
    revision="f" * 40,
)


class Env:
    def __init__(self, engine: Engine, client: TestClient) -> None:
        self.engine = engine
        self.client = client
        self.projects = SqliteProjectRepository(engine)
        self.assets = SqliteMediaAssetRepository(engine)
        self.jobs = SqliteTranscriptionJobRepository(engine)

    def project(self, name: str = "Course") -> Project:
        project = Project(name)
        self.projects.add(project)
        return project

    def asset(self, project: Project, name: str, minutes: int) -> MediaAsset:
        asset = MediaAsset(
            project.id,
            "b" * 64,
            name,
            1_000,
            media_type="audio/wav",
            duration_ms=60_000,
            created_at=T0 + timedelta(minutes=minutes),
        )
        self.assets.add(asset)
        return asset

    def completed_job(self, asset: MediaAsset, minutes: int) -> TranscriptionJob:
        at = T0 + timedelta(minutes=minutes)
        job = TranscriptionJob(
            id=uuid4(),
            project_id=asset.project_id,
            media_asset_id=asset.id,
            state=TranscriptionJobState.COMPLETED,
            progress=1.0,
            created_at=at,
            updated_at=at,
        )
        self.jobs.add(job)
        SqliteTranscriptionJobSelectionRepository(self.engine).add(
            JobSelection(job.id, "option-v1", MODEL, None, None, at)
        )
        SqliteTranscriptRepository(self.engine).add(
            Transcript(asset.project_id, asset.id, id=transcript_id_for(job.id))
        )
        return job


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    upgrade_to_head(engine)
    app = FastAPI()
    app.include_router(
        create_recordings_router(
            ListRecordings(
                SqliteProjectRepository(engine),
                SqliteMediaAssetRepository(engine),
                SqliteTranscriptionJobRepository(engine),
                SqliteTranscriptionJobSelectionRepository(engine),
                SqliteTranscriptRepository(engine),
            )
        )
    )
    yield Env(engine, TestClient(app))
    engine.dispose()


def test_lists_recordings_in_import_order_with_their_latest_job(env: Env) -> None:
    project = env.project()
    second = env.asset(project, "second.wav", 2)
    first = env.asset(project, "first.wav", 1)
    third = env.asset(project, "third.wav", 3)
    job = env.completed_job(second, 5)
    env.project("Other")  # a second project does not leak in
    env.asset(env.project("Elsewhere"), "elsewhere.wav", 0)

    response = env.client.get(f"/api/projects/{project.id}/recordings")

    assert response.status_code == 200
    recordings = response.json()["recordings"]
    assert [r["media_asset_id"] for r in recordings] == [
        str(first.id),
        str(second.id),
        str(third.id),
    ]
    assert recordings[1] == {
        "media_asset_id": str(second.id),
        "filename": "second.wav",
        "media_type": "audio/wav",
        "duration_ms": 60_000,
        "created_at": second.created_at.isoformat(),
        "latest_job": {
            "id": str(job.id),
            "state": "COMPLETED",
            "transcript_id": str(transcript_id_for(job.id)),
            "model_id": "large-v3",
            "created_at": job.created_at.isoformat(),
        },
    }
    assert recordings[0]["latest_job"] is None
    assert recordings[2]["latest_job"] is None


def test_a_project_without_recordings_answers_an_empty_list(env: Env) -> None:
    project = env.project()

    response = env.client.get(f"/api/projects/{project.id}/recordings")

    assert (response.status_code, response.json()) == (200, {"recordings": []})


def test_unknown_project_is_a_stable_404(env: Env) -> None:
    response = env.client.get(f"/api/projects/{uuid4()}/recordings")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_not_found"


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in cast(dict[str, object], value).values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            yield from _strings(item)


def test_no_value_of_the_response_is_a_host_path(env: Env, tmp_path: Path) -> None:
    project = env.project()
    env.completed_job(env.asset(project, "first.wav", 1), 2)
    env.asset(project, "second.wav", 3)

    body = cast(object, env.client.get(f"/api/projects/{project.id}/recordings").json())

    values = list(_strings(body))
    assert values  # the walk found the strings it is meant to check
    for value in values:
        assert str(tmp_path) not in value
        assert not value.startswith("/")
        assert "\\" not in value
        assert "originals" not in value
