"""Migration 0008: stage timing/progress of jobs and the style prompt."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 10, 3, 8, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="turbo",
    display_name="Turbo",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine((tmp_path / "voz.sqlite3").absolute())
    yield created
    created.dispose()


def _config(engine: Engine) -> Config:
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    return config


def test_upgrade_backfills_and_caps_legacy_progress_then_downgrades(
    engine: Engine,
) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0007_project_glossary")
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p', 'P', '2026-10-03T08:00:00+00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m', 'p', 'h', 'a.wav', 1, 'now')"
        )
        for job_id, state, progress in (
            ("queued", "QUEUED", 0.0),
            ("diar", "DIARIZING", 1.0),  # old scheme: transcription made it 1.0
            ("persist", "PERSISTING", 1.0),
            ("trans", "TRANSCRIBING", 0.5),
        ):
            connection.exec_driver_sql(
                "INSERT INTO transcription_jobs VALUES (?, 'p', 'm', ?, ?,"
                " 'created', 'updated', NULL)",
                (job_id, state, progress),
            )
        connection.exec_driver_sql(
            "INSERT INTO transcription_job_selections (job_id, option_id, provider_id,"
            " model_id, model_json, created_at)"
            " VALUES ('diar', 'o', 'x', 'y', '{}', 'now')"
        )
        connection.commit()

        command.upgrade(config, "head")

        rows = {
            row[0]: tuple(row[1:])
            for row in connection.execute(
                text(
                    "SELECT id, progress, started_at, stage_started_at, stage_progress"
                    " FROM transcription_jobs"
                )
            )
        }
        assert rows["queued"] == (0.0, None, "updated", None)
        assert rows["diar"] == (0.8, "created", "updated", None)
        assert rows["persist"] == (0.98, "created", "updated", None)
        assert rows["trans"] == (0.5, "created", "updated", None)
        assert (
            connection.execute(
                text("SELECT prompt FROM transcription_job_selections")
            ).scalar_one()
            is None
        )

        command.downgrade(config, "0007_project_glossary")
        job_columns = {
            c["name"] for c in inspect(connection).get_columns("transcription_jobs")
        }
        assert {"started_at", "stage_started_at", "stage_progress"}.isdisjoint(
            job_columns
        )
        selection_columns = {
            c["name"]
            for c in inspect(connection).get_columns("transcription_job_selections")
        }
        assert "prompt" not in selection_columns


def test_new_job_fields_and_prompt_round_trip(engine: Engine) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    project = Project("Clase", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "a.wav", 10, duration_ms=1000)
    SqliteMediaAssetRepository(engine).add(asset)
    jobs = SqliteTranscriptionJobRepository(engine)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
    )
    jobs.add(job)
    for step, state in enumerate(
        (
            TranscriptionJobState.PROBING,
            TranscriptionJobState.PREPROCESSING,
            TranscriptionJobState.TRANSCRIBING,
        ),
        start=1,
    ):
        job = job.transition_to(state, at=NOW + timedelta(seconds=step))
    job = job.with_stage_progress(0.25, progress=0.3, at=NOW + timedelta(seconds=9))
    jobs.save(job)

    assert jobs.get(job.id) == job
    assert job.started_at == NOW + timedelta(seconds=1)

    selections = SqliteTranscriptionJobSelectionRepository(engine)
    selections.add(
        JobSelection(
            job_id=job.id,
            option_id="o",
            model=MODEL,
            execution=None,
            language=None,
            created_at=NOW,
            prompt="Conferencia de biología. Usa tildes.",
        )
    )
    stored = selections.get(job.id)
    assert stored is not None
    assert stored.prompt == "Conferencia de biología. Usa tildes."
