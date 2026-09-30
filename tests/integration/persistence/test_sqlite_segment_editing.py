"""Migration 0004 and the optimistic-concurrency segment update."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteTranscriptRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 9, 30, 8, tzinfo=UTC)
NEW_COLUMNS = {"speaker_id", "edited", "revision", "original_text"}


def _config(engine: Engine) -> Config:
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    return config


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine((tmp_path / "voz.sqlite3").absolute())
    yield created
    created.dispose()


def _seed_transcript(engine: Engine) -> tuple[Project, Transcript]:
    project = Project("Clase", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "clase.wav", 10, duration_ms=1_000)
    SqliteMediaAssetRepository(engine).add(asset)
    transcript = Transcript(project.id, asset.id, created_at=NOW)
    SqliteTranscriptRepository(engine).add(transcript)
    return project, transcript


def test_migration_0004_preserves_rows_and_downgrades(engine: Engine) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003_job_selections")
        assert NEW_COLUMNS.isdisjoint(
            {c["name"] for c in inspect(connection).get_columns("segments")}
        )
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p', 'P', '2026-09-30T08:00:00+00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m', 'p', 'h', 'a.wav', 1, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcripts VALUES ('t', 'p', 'm', NULL, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO segments (id, transcript_id, start_ms, end_ms, text)"
            " VALUES ('s', 't', 0, 10, 'hola')"
        )
        connection.exec_driver_sql(
            "INSERT INTO words (id, segment_id, start_ms, end_ms, text)"
            " VALUES ('w', 's', 0, 5, 'hola')"
        )
        connection.commit()

        command.upgrade(config, "0004_segment_editing")
        assert connection.execute(text("SELECT count(*) FROM words")).scalar_one() == 1
        row = connection.execute(
            text(
                "SELECT text, speaker_id, edited, revision, original_text FROM segments"
            )
        ).one()
        assert tuple(row) == ("hola", None, 0, 0, None)

        command.downgrade(config, "0003_job_selections")
        assert connection.execute(text("SELECT count(*) FROM words")).scalar_one() == 1
        columns = {c["name"] for c in inspect(connection).get_columns("segments")}
        assert NEW_COLUMNS.isdisjoint(columns)
        assert connection.execute(text("SELECT text FROM segments")).scalar_one() == (
            "hola"
        )
        command.upgrade(config, "head")
        assert {
            c["name"] for c in inspect(connection).get_columns("segments")
        } >= NEW_COLUMNS


def test_editing_fields_round_trip_and_speaker_delete_nulls_reference(
    engine: Engine,
) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    project, transcript = _seed_transcript(engine)
    speaker = Speaker(project.id, "Ana", "#112233")
    SqliteSpeakerRepository(engine).add(speaker)
    repository = SqliteSegmentRepository(engine)
    segment = Segment(transcript.id, 0, 500, "hola", speaker_id=speaker.id).edit_text(
        "Hola."
    )
    repository.add(segment)

    assert repository.get(segment.id) == segment
    assert repository.list_by_transcript(transcript.id) == (segment,)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM speakers"))
    reloaded = repository.get(segment.id)
    assert reloaded is not None
    assert reloaded.speaker_id is None
    assert reloaded.text == "Hola."


def test_update_text_if_revision_is_conditional(engine: Engine) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    _, transcript = _seed_transcript(engine)
    repository = SqliteSegmentRepository(engine)
    segment = Segment(transcript.id, 0, 500, "asr")
    repository.add(segment)

    first = segment.edit_text("uno")
    assert repository.update_text_if_revision(first, 0) is True
    stored = repository.get(segment.id)
    assert stored == first
    assert stored is not None and stored.original_text == "asr"

    stale = segment.edit_text("otro")
    assert repository.update_text_if_revision(stale, 0) is False
    assert repository.get(segment.id) == first

    assert repository.update_text_if_revision(first.edit_text("dos"), 1) is True
    missing = Segment(transcript.id, 0, 1, "x", id=uuid4())
    assert repository.update_text_if_revision(missing.edit_text("y"), 0) is False
