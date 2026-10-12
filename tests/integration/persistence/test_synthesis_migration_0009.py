"""Migration 0009: synthesis tables, applied over a 0008 database with data."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import (
    current_revision,
    head_revision,
    migrations_directory,
    upgrade_to_head,
)
from voz.infrastructure.persistence.schema import metadata

PREVIOUS = "0008_job_stage_prompt"
SYNTHESIS_TABLES = {"synthesis_jobs", "synthesized_audio"}
INSERT_JOB = (
    "INSERT INTO synthesis_jobs (id, state, chunks_done, chunks_total, created_at,"
    " updated_at, text, provider_id, model_id, voice_id, speed, output_format)"
    " VALUES (?, 'QUEUED', 0, ?, 'now', 'now', 'hola', 'p', 'm', 'v', 1.0,"
    " 'wav_pcm16_mono')"
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine(tmp_path / "voz.sqlite3")
    yield created
    created.dispose()


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    return config


def _migrate(engine: Engine, command_name: str, revision: str) -> None:
    config = _config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, command_name)(config, revision)


def _seed_0008(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p1', 'Previo', '2026-10-01T08:00:00+00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m1', 'p1', 'h', 'a.wav', 1, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_jobs (id, project_id, media_asset_id, state,"
            " progress, created_at, updated_at) VALUES ('j1', 'p1', 'm1', 'COMPLETED',"
            " 1.0, 'created', 'updated')"
        )


def test_upgrade_keeps_legacy_data_and_backs_up_the_0008_database(
    engine: Engine, tmp_path: Path
) -> None:
    _migrate(engine, "upgrade", PREVIOUS)
    _seed_0008(engine)
    backups = tmp_path / "backups"

    upgrade_to_head(engine, backups)

    assert current_revision(engine) == head_revision() == "0010_synthesis_request_hash"
    assert set(inspect(engine).get_table_names()) >= SYNTHESIS_TABLES
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT id FROM projects").all() == [("p1",)]
        assert connection.exec_driver_sql(
            "SELECT id, state FROM transcription_jobs"
        ).all() == [("j1", "COMPLETED")]
        for table in SYNTHESIS_TABLES:
            count = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}")
            assert count.scalar_one() == 0
    (backup,) = backups.glob("voz-*.sqlite3")
    assert backup.name.startswith(f"voz-{PREVIOUS}-")
    with sqlite3.connect(backup) as copy:
        assert copy.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (PREVIOUS,)
        ]
        tables = {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
        assert SYNTHESIS_TABLES.isdisjoint(tables)  # the backup predates 0009
        assert copy.execute("SELECT id FROM transcription_jobs").fetchall() == [("j1",)]


def test_migrated_schema_matches_the_metadata(engine: Engine) -> None:
    _migrate(engine, "upgrade", "head")

    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


def test_downgrade_drops_synthesis_and_keeps_legacy_data(engine: Engine) -> None:
    _migrate(engine, "upgrade", PREVIOUS)
    _seed_0008(engine)
    _migrate(engine, "upgrade", "head")
    with engine.begin() as connection:
        connection.exec_driver_sql(INSERT_JOB, ("s1", 2))

    _migrate(engine, "downgrade", PREVIOUS)

    assert current_revision(engine) == PREVIOUS
    assert SYNTHESIS_TABLES.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT id FROM projects").all() == [("p1",)]
        assert connection.exec_driver_sql(
            "SELECT id FROM transcription_jobs"
        ).all() == [("j1",)]
    _migrate(engine, "upgrade", "head")  # and it can be re-applied
    assert set(inspect(engine).get_table_names()) >= SYNTHESIS_TABLES


def test_history_index_exists_and_checks_reject_impossible_rows(
    engine: Engine,
) -> None:
    _migrate(engine, "upgrade", "head")

    indexes = inspect(engine).get_indexes("synthesis_jobs")
    assert ("ix_synthesis_jobs_state_created_at", ["state", "created_at"]) in [
        (i["name"], i["column_names"]) for i in indexes
    ]
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(INSERT_JOB, ("zero", 0))  # chunks_total >= 1
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO synthesized_audio VALUES ('ghost', 'a/b.wav', 1, 1, 1, 1, 'x')"
        )  # no such job
