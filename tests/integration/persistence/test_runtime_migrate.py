"""The runtime upgrade helper creates the schema and is idempotent."""

from pathlib import Path

from sqlalchemy import inspect

from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import (
    migrations_directory,
    upgrade_to_head,
)
from voz.infrastructure.persistence.schema import metadata


def test_upgrade_to_head_creates_schema_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "runtime.sqlite3")
    try:
        upgrade_to_head(engine)
        upgrade_to_head(engine)
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
        assert set(metadata.tables).issubset(tables)
        assert "alembic_version" in tables
    finally:
        engine.dispose()


def test_migrations_directory_points_at_env_py() -> None:
    assert (migrations_directory() / "env.py").is_file()
