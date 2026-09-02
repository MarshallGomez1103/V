"""Integration coverage for applying and reverting Alembic migrations."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from voz.infrastructure.persistence.schema import metadata

REPOSITORY_ROOT = Path(__file__).parents[3]


def _migration_config(database_url: str) -> Config:
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_initial_migration_matches_metadata_and_downgrades_safely(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    config = _migration_config(database_url)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        actual_tables = set(inspect(connection).get_table_names())
        assert set(metadata.tables).issubset(actual_tables)

        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, metadata) == []

        command.downgrade(config, "base")

        remaining_tables = set(inspect(connection).get_table_names())
        assert set(metadata.tables).isdisjoint(remaining_tables)

    engine.dispose()
