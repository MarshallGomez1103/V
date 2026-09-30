"""SQLite engine construction and per-connection safety configuration."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry

DEFAULT_BUSY_TIMEOUT_MS = 5_000


def create_sqlite_engine(
    database_path: Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> Engine:
    """Create an engine for an explicit, absolute, file-backed SQLite path.

    The caller owns path selection; this module deliberately has no checkout or
    working-directory default. SQLite safety pragmas are installed for every
    DB-API connection because ``foreign_keys`` and ``busy_timeout`` are
    connection-local settings.
    """

    path = Path(database_path)
    if not path.is_absolute():
        raise ValueError("database_path must be absolute")
    if type(busy_timeout_ms) is not int:
        raise TypeError("busy_timeout_ms must be an integer")
    if busy_timeout_ms <= 0:
        raise ValueError("busy_timeout_ms must be greater than zero")

    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        connect_args={"timeout": busy_timeout_ms / 1_000},
    )

    def configure_connection(
        dbapi_connection: DBAPIConnection,
        _connection_record: ConnectionPoolEntry,
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            # Explicit: a confirmed chunk must survive power loss, and some
            # SQLite builds default to NORMAL (may drop the last WAL commits).
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms:d}")
        finally:
            cursor.close()

    event.listen(engine, "connect", configure_connection)
    return engine
