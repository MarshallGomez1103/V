"""Apply Alembic migrations at startup from the checkout or the installed wheel."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

_PACKAGE_DIR = Path(__file__).resolve().parent
# The wheel force-includes ``migrations`` next to this module; a development
# checkout keeps them at the repository root (``src/voz/infrastructure/persistence``
# is four levels below it).
_CANDIDATE_SCRIPT_DIRS = (
    _PACKAGE_DIR / "migrations",
    _PACKAGE_DIR.parents[3] / "migrations",
)


def migrations_directory() -> Path:
    """Locate the Alembic ``migrations`` directory for this installation."""
    for candidate in _CANDIDATE_SCRIPT_DIRS:
        if (candidate / "env.py").is_file():
            return candidate
    raise FileNotFoundError("Alembic migrations directory not found")


def upgrade_to_head(engine: Engine) -> None:
    """Bring the database behind ``engine`` to the latest schema revision.

    Idempotent: a database already at head is left untouched. The programmatic
    ``Config`` has no ini file, so Alembic does not reconfigure process logging.
    """
    config = Config()
    config.set_main_option("script_location", str(migrations_directory()))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
