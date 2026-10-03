"""Apply Alembic migrations at startup from the checkout or the installed wheel."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing, suppress
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from voz.infrastructure.paths import resolve_voz_paths
from voz.infrastructure.safe_fs import BINARY_FLAG, DirectoryHandle, best_effort_chmod

_PACKAGE_DIR = Path(__file__).resolve().parent
# The wheel force-includes ``migrations`` next to this module; a development
# checkout keeps them at the repository root (``src/voz/infrastructure/persistence``
# is four levels below it).
_CANDIDATE_SCRIPT_DIRS = (
    _PACKAGE_DIR / "migrations",
    _PACKAGE_DIR.parents[3] / "migrations",
)

BACKUPS_DIRECTORY = "backups"
KEEP_BACKUPS = 5
_BACKUP_NAME = re.compile(r"voz-(?P<revision>.+)-(?P<stamp>\d{8}T\d{12}Z)\.sqlite3")


class MigrationBackupError(RuntimeError):
    """The pre-migration backup failed, so the database was left untouched."""

    code = "migration_backup_failed"


def migrations_directory() -> Path:
    """Locate the Alembic ``migrations`` directory for this installation."""
    for candidate in _CANDIDATE_SCRIPT_DIRS:
        if (candidate / "env.py").is_file():
            return candidate
    raise FileNotFoundError("Alembic migrations directory not found")


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    return config


def head_revision() -> str | None:
    """Latest revision known to this installation's migration scripts."""
    return ScriptDirectory.from_config(_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    """Revision recorded in the database; ``None`` for a brand new database."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _fsync_file(path: Path) -> None:
    # Read-write: Windows refuses to flush a descriptor opened read-only.
    descriptor = os.open(path, os.O_RDWR | BINARY_FLAG)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prune_backups(directory: Path, keep: int) -> None:
    found = [
        (match["stamp"], entry)
        for entry in directory.iterdir()
        if (match := _BACKUP_NAME.fullmatch(entry.name)) and entry.is_file()
    ]
    for _, entry in sorted(found, key=lambda item: item[0])[:-keep]:
        entry.unlink(missing_ok=True)


def backup_database(engine: Engine, revision: str, directory: Path) -> Path:
    """Copy the live database consistently (WAL-safe) into ``directory``.

    Uses SQLite's online backup API, fsyncs the copy and its directory, then keeps
    only the ``KEEP_BACKUPS`` most recent backups.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    final = directory / f"voz-{revision}-{stamp}.sqlite3"
    partial = directory / f".{final.name}.partial"
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = engine.raw_connection()
        try:
            source = raw.driver_connection
            if not isinstance(source, sqlite3.Connection):
                raise MigrationBackupError("Only SQLite databases can be backed up.")
            with closing(sqlite3.connect(partial)) as copy:
                source.backup(copy)
        finally:
            raw.close()
        best_effort_chmod(partial, 0o600)  # Windows only honours the read-only bit
        _fsync_file(partial)
        os.replace(partial, final)
        DirectoryHandle(directory, None).fsync()  # no-op where NTFS cannot
        _prune_backups(directory, KEEP_BACKUPS)
    except (OSError, sqlite3.Error) as error:
        with suppress(OSError):
            partial.unlink(missing_ok=True)
        raise MigrationBackupError(
            "Could not back up the database before migrating; nothing was changed."
        ) from error
    return final


def upgrade_to_head(engine: Engine, backup_directory: Path | None = None) -> None:
    """Bring the database behind ``engine`` to the latest schema revision.

    Idempotent: a database already at head is left untouched. An existing database
    behind head is first copied to ``backup_directory`` (default: the XDG state
    ``backups`` folder); if that copy fails, ``MigrationBackupError`` is raised and
    nothing is migrated. New and in-memory databases need no backup. The
    programmatic ``Config`` has no ini file, so Alembic does not reconfigure
    process logging.
    """
    config = _config()
    current = current_revision(engine)
    if (
        current is not None
        and current != head_revision()
        and engine.url.database not in {None, "", ":memory:"}
    ):
        target = backup_directory or resolve_voz_paths().state / BACKUPS_DIRECTORY
        backup_database(engine, current, target)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
