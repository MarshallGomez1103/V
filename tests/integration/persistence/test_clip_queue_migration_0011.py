"""Migration 0011: per-job clip columns and the transcription queue tables."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import (
    current_revision,
    head_revision,
    migrations_directory,
    upgrade_to_head,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

PREVIOUS = "0010_synthesis_request_hash"
REVISION = "0011_transcription_clip_and_queue"
QUEUE_TABLES = {"transcription_queues", "transcription_queue_items"}
CLIP_COLUMNS = {"clip_start_ms", "clip_end_ms"}
JOB = "00000000-0000-4000-8000-000000000001"
MODEL_JSON = (
    '{"capabilities":["transcription"],"display_name":"Y","model_id":"y",'
    '"profile":null,"provider_id":"x","revision":null,"source":null}'
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine(tmp_path / "voz.sqlite3")
    yield created
    created.dispose()


def _migrate(engine: Engine, command_name: str, revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, command_name)(config, revision)


def _seed_job(engine: Engine, job_id: str = JOB, *, selection: bool = True) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO projects VALUES ('p1', 'P', '2026-11-11T08:00:00Z')"
        )
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO media_assets (id, project_id, content_sha256,"
            " display_name, size_bytes, created_at)"
            " VALUES ('m1', 'p1', 'h', 'a.wav', 1, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_jobs (id, project_id, media_asset_id, state,"
            " progress, created_at, updated_at) VALUES (?, 'p1', 'm1', 'QUEUED',"
            " 0.0, 'created', 'updated')",
            (job_id,),
        )
        if selection:
            connection.exec_driver_sql(
                "INSERT INTO transcription_job_selections (job_id, option_id,"
                " provider_id, model_id, model_json, created_at)"
                " VALUES (?, 'o', 'x', 'y', ?, '2026-11-11T08:00:00+00:00')",
                (job_id, MODEL_JSON),
            )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        result = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}")
        return int(result.scalar_one())


def test_upgrade_keeps_existing_selections_as_whole_recording(
    engine: Engine, tmp_path: Path
) -> None:
    _migrate(engine, "upgrade", PREVIOUS)
    _seed_job(engine)
    backups = tmp_path / "backups"

    upgrade_to_head(engine, backups)

    assert current_revision(engine) == head_revision() == REVISION
    selection = SqliteTranscriptionJobSelectionRepository(engine).get(UUID(JOB))
    assert selection is not None
    assert selection.clip is None
    assert set(inspect(engine).get_table_names()) >= QUEUE_TABLES
    assert {
        c["name"] for c in inspect(engine).get_columns("transcription_job_selections")
    } >= CLIP_COLUMNS
    for table in QUEUE_TABLES:
        assert _count(engine, table) == 0
    (backup,) = backups.glob("voz-*.sqlite3")
    assert backup.name.startswith(f"voz-{PREVIOUS}-")
    with sqlite3.connect(backup) as copy:
        tables = {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
        assert QUEUE_TABLES.isdisjoint(tables)  # the backup predates 0011


def test_downgrade_drops_tables_and_columns_keeping_rows(engine: Engine) -> None:
    _migrate(engine, "upgrade", PREVIOUS)
    _seed_job(engine)
    _migrate(engine, "upgrade", "head")

    _migrate(engine, "downgrade", PREVIOUS)

    assert current_revision(engine) == PREVIOUS
    assert QUEUE_TABLES.isdisjoint(inspect(engine).get_table_names())
    assert CLIP_COLUMNS.isdisjoint(
        c["name"] for c in inspect(engine).get_columns("transcription_job_selections")
    )
    assert _count(engine, "transcription_jobs") == 1
    assert _count(engine, "transcription_job_selections") == 1
    _migrate(engine, "upgrade", "head")  # and it can be re-applied
    assert _count(engine, "transcription_job_selections") == 1


def test_project_delete_cascades_queue_rows(engine: Engine) -> None:
    _migrate(engine, "upgrade", "head")
    _seed_job(engine, selection=False)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO transcription_queues VALUES ('q1', 'p1', 'now', '[]')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_queue_items VALUES ('q1', 0, ?)", (JOB,)
        )

    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM projects WHERE id = 'p1'")

    for table in ("transcription_jobs", *QUEUE_TABLES):
        assert _count(engine, table) == 0


def test_job_and_queue_delete_cascade_to_items(engine: Engine) -> None:
    _migrate(engine, "upgrade", "head")
    other = "00000000-0000-4000-8000-000000000002"
    _seed_job(engine, selection=False)
    _seed_job(engine, other, selection=False)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO transcription_queues VALUES ('q1', 'p1', 'now', '[]')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_queue_items VALUES ('q1', 0, ?), ('q1', 1, ?)",
            (JOB, other),
        )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM transcription_jobs WHERE id = ?", (JOB,)
        )
    assert _count(engine, "transcription_queue_items") == 1
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM transcription_queues WHERE id = 'q1'")
    assert _count(engine, "transcription_queue_items") == 0
    assert _count(engine, "transcription_jobs") == 1  # jobs outlive their queue


def test_queue_items_reject_negative_positions_and_a_job_in_two_queues(
    engine: Engine,
) -> None:
    _migrate(engine, "upgrade", "head")
    _seed_job(engine, selection=False)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO transcription_queues VALUES ('q1', 'p1', 'now', '[]'),"
            " ('q2', 'p1', 'now', '[]')"
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO transcription_queue_items VALUES ('q1', -1, ?)", (JOB,)
        )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO transcription_queue_items VALUES ('q1', 0, ?)", (JOB,)
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO transcription_queue_items VALUES ('q2', 0, ?)", (JOB,)
        )
