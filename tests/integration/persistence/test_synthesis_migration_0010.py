"""Migration 0010: request_hash column and index, backfilled over 0009 data."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

from voz.application.synthesis.create_synthesis_job import request_hash
from voz.domain.entities.synthesis_request import SynthesisRequest
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import (
    current_revision,
    head_revision,
    migrations_directory,
)

PREVIOUS = "0009_synthesis"
INDEX = "ix_synthesis_jobs_request_hash_state"
INSERT_JOB = (
    "INSERT INTO synthesis_jobs (id, state, chunks_done, chunks_total, created_at,"
    " updated_at, text, provider_id, model_id, model_revision, voice_id, language,"
    " speed, output_format) VALUES (?, ?, 0, 1, 'now', 'now', ?, 'p', 'm', ?, 'v',"
    " ?, ?, ?)"
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


def _seed_0009(engine: Engine) -> None:
    rows = [
        ("a", "COMPLETED", "Hola ñ", "rev", "es", 1.0, "wav_pcm16_mono"),
        ("b", "QUEUED", "Sin extras", None, None, 1.25, "wav_pcm16_mono"),
        ("bad-speed", "FAILED", "Roto", None, None, 0.0, "wav_pcm16_mono"),
        ("bad-format", "FAILED", "Roto", None, None, 1.0, "mp3-from-the-future"),
    ]
    with engine.begin() as connection:
        for row in rows:
            connection.exec_driver_sql(INSERT_JOB, row)


def _hashes(engine: Engine) -> dict[str, str | None]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT id, request_hash FROM synthesis_jobs")
        return {job_id: digest for job_id, digest in rows}


def test_upgrade_backfills_valid_rows_and_leaves_invalid_ones_null(
    engine: Engine,
) -> None:
    _migrate(engine, "upgrade", PREVIOUS)
    _seed_0009(engine)

    _migrate(engine, "upgrade", "head")

    assert current_revision(engine) == head_revision() == "0010_synthesis_request_hash"
    hashes = _hashes(engine)
    assert hashes["a"] == request_hash(
        SynthesisRequest("Hola ñ", "p", "m", "v", model_revision="rev", language="es")
    )
    assert hashes["b"] == request_hash(
        SynthesisRequest("Sin extras", "p", "m", "v", speed=1.25)
    )
    assert hashes["bad-speed"] is None
    assert hashes["bad-format"] is None
    assert [
        (i["name"], i["column_names"])
        for i in inspect(engine).get_indexes("synthesis_jobs")
    ].count((INDEX, ["request_hash", "state"])) == 1


def test_upgrade_of_an_empty_table_works(engine: Engine) -> None:
    _migrate(engine, "upgrade", "head")

    assert _hashes(engine) == {}
    columns = {c["name"]: c for c in inspect(engine).get_columns("synthesis_jobs")}
    assert columns["request_hash"]["nullable"] is True


def test_downgrade_drops_column_and_index_and_keeps_the_rows(engine: Engine) -> None:
    _migrate(engine, "upgrade", PREVIOUS)
    _seed_0009(engine)
    _migrate(engine, "upgrade", "head")

    _migrate(engine, "downgrade", PREVIOUS)

    assert current_revision(engine) == PREVIOUS
    assert "request_hash" not in {
        c["name"] for c in inspect(engine).get_columns("synthesis_jobs")
    }
    assert INDEX not in {
        i["name"] for i in inspect(engine).get_indexes("synthesis_jobs")
    }
    with engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM synthesis_jobs")
        assert count.scalar_one() == 4
    _migrate(engine, "upgrade", "head")  # and it can be re-applied
    assert _hashes(engine)["a"] is not None
