"""Library, rename, delete and media metadata over SQLite and storage (CP-A1/A2)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from voz.application.job_runner import transcript_id_for
from voz.application.library import ListLibrary
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.projects import (
    CreateProject,
    DeleteProject,
    ListProjects,
    RenameProject,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.library import SqliteLibraryReader
from voz.infrastructure.persistence.migrate import upgrade_to_head
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
from voz.interfaces.api.library import create_library_router
from voz.interfaces.api.media_stream import create_media_stream_router
from voz.interfaces.api.projects import create_projects_router

T0 = datetime(2026, 10, 1, 12, tzinfo=UTC)
DELETE = {"X-VOZ-Action": "delete-project"}
MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="large-v3",
    display_name="Large v3",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/model",
    revision="f" * 40,
)


@dataclass(slots=True)
class Env:
    engine: Engine
    client: TestClient
    root: Path
    storage: FileSystemMediaStorage

    def project(self, name: str, minutes: int = 0) -> Project:
        project = Project(name, created_at=T0 + timedelta(minutes=minutes))
        SqliteProjectRepository(self.engine).add(project)
        return project

    def asset(
        self,
        project: Project,
        filename: str = "clase.m4a",
        media_type: str | None = None,
    ) -> MediaAsset:
        asset = MediaAsset(
            project.id,
            "a" * 64,
            filename,
            1_000,
            duration_ms=60_000,
            media_type=media_type,
            created_at=project.created_at,
        )
        SqliteMediaAssetRepository(self.engine).add(asset)
        original = self.storage.original_path_for(project.id, asset.id)
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"audio")
        os.chmod(original, 0o444)
        derivative = (
            original.parent.parent / "derivatives" / f"{asset.id}.inference.wav"
        )
        derivative.parent.mkdir(parents=True, exist_ok=True)
        derivative.write_bytes(b"wav")
        return asset

    def job(
        self,
        project: Project,
        asset: MediaAsset,
        state: TranscriptionJobState = TranscriptionJobState.COMPLETED,
        minutes: int = 1,
    ) -> TranscriptionJob:
        at = T0 + timedelta(minutes=minutes)
        job = TranscriptionJob(
            id=uuid4(),
            project_id=project.id,
            media_asset_id=asset.id,
            state=state,
            progress=1.0 if state is TranscriptionJobState.COMPLETED else 0.0,
            created_at=at,
            updated_at=at,
        )
        SqliteTranscriptionJobRepository(self.engine).add(job)
        SqliteTranscriptionJobSelectionRepository(self.engine).add(
            JobSelection(
                job_id=job.id,
                option_id="option-v1",
                model=MODEL,
                execution=None,
                language=None,
                created_at=at,
            )
        )
        return job

    def transcript(self, job: TranscriptionJob, project: Project) -> Transcript:
        """Two speakers, three segments, two turns."""
        transcript = Transcript(
            project.id, job.media_asset_id, id=transcript_id_for(job.id)
        )
        SqliteTranscriptRepository(self.engine).add(transcript)
        speakers = SqliteSpeakerRepository(self.engine)
        ana, beto = (Speaker(project.id, n, "#4e79a7") for n in ("Ana", "Beto"))
        ghost = Speaker(project.id, "Fantasma", "#4e79a7")  # turns only, no segment
        for speaker in (ana, beto, ghost):
            speakers.add(speaker)
        segments = SqliteSegmentRepository(self.engine)
        for index, owner in enumerate((ana, ana, beto)):
            segments.add(
                Segment(
                    transcript.id,
                    index * 100,
                    index * 100 + 90,
                    f"s{index}",
                    speaker_id=owner.id,
                )
            )
        SqliteSpeakerTurnRepository(self.engine).replace_for_transcript(
            transcript.id,
            (
                SpeakerTurn(transcript.id, "0", 0, 200, speaker_id=ana.id),
                SpeakerTurn(transcript.id, "9", 300, 400, speaker_id=ghost.id),
            ),
        )
        return transcript

    def count(self, table: str) -> int:
        with self.engine.connect() as connection:
            return int(
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            )


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    upgrade_to_head(engine)
    storage = FileSystemMediaStorage(tmp_path / "data")
    projects = SqliteProjectRepository(engine)
    jobs = SqliteTranscriptionJobRepository(engine)
    media = SqliteMediaAssetRepository(engine)
    app = FastAPI()
    app.include_router(
        create_projects_router(
            CreateProject(projects),
            ListProjects(projects),
            rename=RenameProject(projects),
            delete=DeleteProject(projects, jobs, storage, projects),
        )
    )
    app.include_router(create_library_router(ListLibrary(SqliteLibraryReader(engine))))
    app.include_router(create_media_stream_router(media, storage))
    yield Env(engine, TestClient(app), tmp_path / "data", storage)
    engine.dispose()


def test_library_lists_projects_by_recent_activity(env: Env) -> None:
    done = env.project("Clase de física", minutes=0)
    done_asset = env.asset(done, media_type="audio/aac")
    done_job = env.job(done, done_asset, minutes=5)
    transcript = env.transcript(done_job, done)
    running = env.project("Entrevista", minutes=1)
    running_job = env.job(
        running, env.asset(running, "voz.wav"), TranscriptionJobState.TRANSCRIBING, 2
    )
    empty = env.project("Vacío", minutes=4)

    response = env.client.get("/api/library")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["name"] for item in items] == [
        "Clase de física",
        "Vacío",
        "Entrevista",
    ]
    first = items[0]
    assert first["project_id"] == str(done.id)
    assert first["media"] == {
        "media_asset_id": str(done_asset.id),
        "filename": "clase.m4a",
        "media_type": "audio/aac",
        "duration_ms": 60_000,
    }
    assert first["latest_job"]["id"] == str(done_job.id)
    assert first["latest_job"]["state"] == "COMPLETED"
    assert first["latest_job"]["transcript_id"] == str(transcript.id)
    assert first["latest_job"]["model_id"] == "large-v3"
    assert (first["speaker_count"], first["segment_count"]) == (2, 3)
    assert first["updated_at"] > first["created_at"]
    entrevista = items[2]
    assert entrevista["latest_job"]["id"] == str(running_job.id)
    assert entrevista["latest_job"]["transcript_id"] is None
    assert (entrevista["speaker_count"], entrevista["segment_count"]) == (0, 0)
    vacio = items[1]
    assert (vacio["project_id"], vacio["media"], vacio["latest_job"]) == (
        str(empty.id),
        None,
        None,
    )


def test_library_keeps_the_probed_media_type_and_latest_job(env: Env) -> None:
    project = env.project("P")
    asset = env.asset(project, "x.bin", media_type="audio/ogg")
    env.job(project, asset, minutes=1)
    newer = env.job(project, asset, TranscriptionJobState.FAILED, minutes=3)

    item = env.client.get("/api/library").json()["items"][0]

    assert item["media"]["media_type"] == "audio/ogg"
    assert item["latest_job"]["id"] == str(newer.id)


def test_library_is_empty_without_projects(env: Env) -> None:
    assert env.client.get("/api/library").json() == {"items": []}


def test_media_info_returns_filename_and_type_without_paths(env: Env) -> None:
    project = env.project("P")
    asset = env.asset(project, "nota.mp3")

    body = env.client.get(f"/api/media/{asset.id}").json()

    assert body["filename"] == "nota.mp3"
    assert body["media_type"] == "audio/mpeg"  # not probed: from the extension
    assert body["duration_ms"] == 60_000
    assert env.client.get(f"/api/media/{uuid4()}").status_code == 404


def test_rename_trims_and_persists(env: Env) -> None:
    project = env.project("Viejo")

    response = env.client.patch(
        f"/api/projects/{project.id}", json={"name": "  Nuevo  "}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nuevo"
    stored = SqliteProjectRepository(env.engine).get(project.id)
    assert stored is not None and stored.name == "Nuevo"
    assert stored.created_at == project.created_at


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, "a\nb"])
def test_rename_rejects_invalid_names(env: Env, name: str) -> None:
    project = env.project("Viejo")

    response = env.client.patch(f"/api/projects/{project.id}", json={"name": name})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "project_name_invalid"
    stored = SqliteProjectRepository(env.engine).get(project.id)
    assert stored is not None and stored.name == "Viejo"


def test_rename_unknown_project_is_404(env: Env) -> None:
    response = env.client.patch(f"/api/projects/{uuid4()}", json={"name": "X"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_not_found"


def test_delete_needs_the_action_header(env: Env) -> None:
    project = env.project("P")

    response = env.client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "project_delete_forbidden"
    assert SqliteProjectRepository(env.engine).get(project.id) is not None


def test_delete_removes_rows_and_files_but_only_that_project(env: Env) -> None:
    doomed = env.project("Borrar")
    doomed_asset = env.asset(doomed)
    job = env.job(doomed, doomed_asset)
    env.transcript(job, doomed)
    SqliteProjectGlossaryRepository(env.engine).put(doomed.id, ("Mitocondria",))
    kept = env.project("Quedarse", minutes=1)
    kept_asset = env.asset(kept)
    kept_job = env.job(kept, kept_asset)
    env.transcript(kept_job, kept)
    original = env.storage.original_path_for(doomed.id, doomed_asset.id)
    assert original.is_file()

    response = env.client.delete(f"/api/projects/{doomed.id}", headers=DELETE)

    assert response.status_code == 204
    assert not (env.root / "projects" / str(doomed.id)).exists()
    assert env.storage.original_path_for(kept.id, kept_asset.id).is_file()
    assert SqliteProjectRepository(env.engine).get(doomed.id) is None
    assert [
        item["name"] for item in env.client.get("/api/library").json()["items"]
    ] == ["Quedarse"]
    # Everything that belonged to the deleted project is gone, the rest stays.
    assert env.count("projects") == 1
    assert env.count("media_assets") == 1
    assert env.count("transcription_jobs") == 1
    assert env.count("transcription_job_selections") == 1
    assert env.count("transcripts") == 1
    assert env.count("segments") == 3
    assert env.count("speakers") == 3
    assert env.count("speaker_turns") == 2
    assert env.count("project_glossaries") == 0
    assert env.count("words") == 0


def test_delete_cascades_checkpoints(env: Env) -> None:
    project = env.project("P")
    job = env.job(project, env.asset(project))
    SqliteTranscriptionCheckpointStore(env.engine)  # table exists after migration
    with env.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO transcription_checkpoints (id, job_id, chunk_index, "
                "process_start_ms, process_end_ms, owned_start_ms, owned_end_ms, "
                "provider_id, model_id, segments_json, progress, job_progress, "
                "completed_at) VALUES ('c1', :job, 0, 0, 10, 0, 10, 'p', 'm', '[]', "
                "0.5, 0.5, '2026-10-01T00:00:00+00:00')"
            ),
            {"job": str(job.id)},
        )

    env.client.delete(f"/api/projects/{project.id}", headers=DELETE)

    assert env.count("transcription_checkpoints") == 0


@pytest.mark.parametrize(
    "state",
    [
        TranscriptionJobState.QUEUED,
        TranscriptionJobState.TRANSCRIBING,
        TranscriptionJobState.DIARIZING,
        TranscriptionJobState.CANCELLING,
    ],
)
def test_delete_is_refused_while_a_job_runs(
    env: Env, state: TranscriptionJobState
) -> None:
    project = env.project("P")
    asset = env.asset(project)
    env.job(project, asset, state)

    response = env.client.delete(f"/api/projects/{project.id}", headers=DELETE)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "project_busy"
    assert env.storage.original_path_for(project.id, asset.id).is_file()
    assert SqliteProjectRepository(env.engine).get(project.id) is not None


def test_delete_allows_failed_and_cancelled_jobs(env: Env) -> None:
    project = env.project("P")
    asset = env.asset(project)
    env.job(project, asset, TranscriptionJobState.CANCELLED)

    response = env.client.delete(f"/api/projects/{project.id}", headers=DELETE)

    assert response.status_code == 204


def test_delete_unknown_project_is_404(env: Env) -> None:
    response = env.client.delete(f"/api/projects/{uuid4()}", headers=DELETE)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_not_found"


def test_delete_keeps_the_project_when_files_cannot_be_removed(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = env.project("P")
    env.asset(project)

    def fail(_: UUID) -> None:
        raise OSError("disk says no")

    monkeypatch.setattr(env.storage, "delete_project_files", fail)

    response = env.client.delete(f"/api/projects/{project.id}", headers=DELETE)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "project_delete_failed"
    assert SqliteProjectRepository(env.engine).get(project.id) is not None
    assert "disk says no" not in response.text
