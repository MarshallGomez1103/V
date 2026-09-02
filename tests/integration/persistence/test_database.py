"""File-backed integration tests for SQLite engine configuration."""

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from voz.infrastructure.persistence.database import (
    DEFAULT_BUSY_TIMEOUT_MS,
    create_sqlite_engine,
)


def read_pragma(engine: Engine, name: str) -> str | int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"PRAGMA {name}").scalar_one()
    assert isinstance(value, (str, int))
    return value


def test_engine_enables_sqlite_safety_pragmas_for_each_connection(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "voz.sqlite3"
    engine = create_sqlite_engine(database_path)

    try:
        assert read_pragma(engine, "journal_mode") == "wal"
        assert read_pragma(engine, "foreign_keys") == 1
        assert read_pragma(engine, "busy_timeout") == DEFAULT_BUSY_TIMEOUT_MS
        assert database_path.is_file()
    finally:
        engine.dispose()


def test_wal_database_reopens_with_data_and_connection_pragmas(tmp_path: Path) -> None:
    database_path = tmp_path / "voz.sqlite3"
    first_engine = create_sqlite_engine(database_path, busy_timeout_ms=2_500)
    try:
        with first_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE checkpoint (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO checkpoint (value) VALUES ('persisted')"
            )
    finally:
        first_engine.dispose()

    reopened_engine = create_sqlite_engine(database_path, busy_timeout_ms=2_500)
    try:
        with reopened_engine.connect() as connection:
            persisted = connection.exec_driver_sql(
                "SELECT value FROM checkpoint WHERE id = 1"
            ).scalar_one()

        assert persisted == "persisted"
        assert read_pragma(reopened_engine, "journal_mode") == "wal"
        assert read_pragma(reopened_engine, "foreign_keys") == 1
        assert read_pragma(reopened_engine, "busy_timeout") == 2_500
    finally:
        reopened_engine.dispose()


def test_foreign_key_enforcement_is_active(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "voz.sqlite3")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE child ("
                "id INTEGER PRIMARY KEY, "
                "parent_id INTEGER NOT NULL REFERENCES parent(id)"
                ")"
            )

        with (
            pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"),
            engine.begin() as connection,
        ):
            connection.exec_driver_sql(
                "INSERT INTO child (id, parent_id) VALUES (1, 999)"
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("busy_timeout_ms", [0, -1])
def test_engine_rejects_non_positive_busy_timeout(
    tmp_path: Path,
    busy_timeout_ms: int,
) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        create_sqlite_engine(
            tmp_path / "voz.sqlite3",
            busy_timeout_ms=busy_timeout_ms,
        )


def test_engine_rejects_relative_database_path() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        create_sqlite_engine(Path("voz.sqlite3"))
