"""Migration 0005 and the diarization fields of the job selection snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from voz.application.ports.diarization import DiarizationOptions, SpeakerCountHint
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import TranscriptionJob
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
NOW = datetime(2026, 9, 30, 10, tzinfo=UTC)
NEW_COLUMNS = {"diarization_json", "diarization_error_code"}
MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


def _config(engine: Engine) -> Config:
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    return config


def _columns(engine: Engine) -> set[str]:
    return {
        c["name"] for c in inspect(engine).get_columns("transcription_job_selections")
    }


def test_migration_0005_keeps_existing_selections_and_downgrades(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine((tmp_path / "m.db").absolute())
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0004_segment_editing")
        assert NEW_COLUMNS.isdisjoint(
            {
                c["name"]
                for c in inspect(connection).get_columns("transcription_job_selections")
            }
        )
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p', 'P', '2026-09-30T08:00:00+00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m', 'p', 'h', 'a.wav', 1, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_jobs VALUES"
            " ('j', 'p', 'm', 'QUEUED', 0.0, 'now', 'now', NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_job_selections (job_id, option_id, provider_id,"
            " model_id, model_json, created_at)"
            " VALUES ('j', 'o', 'fake', 'fx', '{}', 'now')"
        )
        connection.commit()

        command.upgrade(config, "0005_job_diarization")
        row = connection.execute(
            text(
                "SELECT option_id, diarization_json, diarization_error_code"
                " FROM transcription_job_selections"
            )
        ).one()
        assert tuple(row) == ("o", None, None)
        assert (
            connection.execute(
                text("SELECT count(*) FROM transcription_jobs")
            ).scalar_one()
            == 1
        )

        command.downgrade(config, "0004_segment_editing")
        assert NEW_COLUMNS.isdisjoint(
            {
                c["name"]
                for c in inspect(connection).get_columns("transcription_job_selections")
            }
        )
        assert (
            connection.execute(
                text("SELECT option_id FROM transcription_job_selections")
            ).scalar_one()
            == "o"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM transcription_jobs")
            ).scalar_one()
            == 1
        )
    engine.dispose()


@pytest.mark.parametrize(
    "options",
    [
        None,
        DiarizationOptions(),
        DiarizationOptions(SpeakerCountHint(exact=2)),
        DiarizationOptions(SpeakerCountHint(minimum=2, maximum=5)),
    ],
)
def test_diarization_request_round_trips_and_error_is_recorded(
    tmp_path: Path, options: DiarizationOptions | None
) -> None:
    engine = create_sqlite_engine((tmp_path / "s.db").absolute())
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    assert _columns(engine) >= NEW_COLUMNS

    project = Project("Demo", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 10, duration_ms=250)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
    )
    SqliteTranscriptionJobRepository(engine).add(job)
    repository = SqliteTranscriptionJobSelectionRepository(engine)
    selection = JobSelection(
        job_id=job.id,
        option_id="option-v1-abc",
        model=MODEL,
        execution=None,
        language=None,
        created_at=NOW,
        diarization=options,
    )
    repository.add(selection)

    assert repository.get(job.id) == selection

    repository.record_diarization_error(job.id, "diarization_provider_failed")

    reloaded = repository.get(job.id)
    assert reloaded is not None
    assert reloaded.diarization == options
    assert reloaded.diarization_error_code == "diarization_provider_failed"
    engine.dispose()
