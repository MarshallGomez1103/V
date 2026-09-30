"""S14.10: a consistent backup precedes any migration of an existing database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import (
    KEEP_BACKUPS,
    MigrationBackupError,
    backup_database,
    current_revision,
    head_revision,
    migrations_directory,
    upgrade_to_head,
)

OLD_REVISION = "0003_job_selections"


def _engine_at(tmp_path: Path, revision: str) -> Engine:
    engine = create_sqlite_engine(tmp_path / "voz.sqlite3")
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
    return engine


def _seed_project(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
            ("p1", "Proyecto previo", "2026-01-01T00:00:00+00:00"),
        )


def test_existing_database_behind_head_is_backed_up_before_migrating(
    tmp_path: Path,
) -> None:
    engine = _engine_at(tmp_path, OLD_REVISION)
    backups = tmp_path / "state" / "backups"
    try:
        _seed_project(engine)

        upgrade_to_head(engine, backups)

        assert current_revision(engine) == head_revision()
        (backup,) = backups.glob("voz-*.sqlite3")
        assert backup.name.startswith(f"voz-{OLD_REVISION}-")
        assert list(backups.glob(".*")) == []  # no partial file left behind
        with sqlite3.connect(backup) as copy:
            revision = copy.execute("SELECT version_num FROM alembic_version")
            assert revision.fetchone() == (OLD_REVISION,)
            names = copy.execute("SELECT name FROM projects").fetchall()
            assert names == [("Proyecto previo",)]
            columns = [row[1] for row in copy.execute("PRAGMA table_info(segments)")]
            assert "original_text" not in columns  # pre-0004 schema preserved
    finally:
        engine.dispose()


def test_new_database_and_database_at_head_are_not_backed_up(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "voz.sqlite3")
    backups = tmp_path / "backups"
    try:
        upgrade_to_head(engine, backups)
        upgrade_to_head(engine, backups)
    finally:
        engine.dispose()

    assert not backups.exists()


def test_backup_failure_aborts_the_migration(tmp_path: Path) -> None:
    engine = _engine_at(tmp_path, OLD_REVISION)
    blocked = tmp_path / "backups"
    blocked.write_text("a file, so mkdir must fail")
    try:
        with pytest.raises(MigrationBackupError) as raised:
            upgrade_to_head(engine, blocked)

        assert raised.value.code == "migration_backup_failed"
        assert current_revision(engine) == OLD_REVISION
    finally:
        engine.dispose()


def test_backup_keeps_only_the_most_recent_five(tmp_path: Path) -> None:
    engine = _engine_at(tmp_path, OLD_REVISION)
    backups = tmp_path / "backups"
    try:
        created = [
            backup_database(engine, OLD_REVISION, backups)
            for _ in range(KEEP_BACKUPS + 3)
        ]
    finally:
        engine.dispose()

    assert sorted(backups.glob("voz-*.sqlite3")) == sorted(created[-KEEP_BACKUPS:])


def test_default_backup_directory_is_xdg_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    engine = _engine_at(tmp_path, OLD_REVISION)
    try:
        upgrade_to_head(engine)
    finally:
        engine.dispose()

    assert len(list((tmp_path / "state" / "voz" / "backups").glob("voz-*"))) == 1
