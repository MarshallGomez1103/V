"""Strict row readers shared by the SQLite persistence adapters."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text

from voz.infrastructure.persistence._rows import (
    row_integer,
    row_optional_text,
    row_real,
    row_text,
)


def _row(engine: Engine, literal: str):  # type: ignore[no-untyped-def]
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT {literal} AS v")).mappings().one()


@pytest.fixture
def engine() -> Engine:
    return create_engine("sqlite://")


def test_row_text_accepts_only_strings(engine: Engine) -> None:
    assert row_text(_row(engine, "'abc'"), "v") == "abc"
    for literal in ("1", "NULL", "1.5"):
        with pytest.raises(TypeError, match="persisted v must be a string"):
            row_text(_row(engine, literal), "v")


def test_row_optional_text_allows_null(engine: Engine) -> None:
    assert row_optional_text(_row(engine, "NULL"), "v") is None
    assert row_optional_text(_row(engine, "'x'"), "v") == "x"
    with pytest.raises(TypeError, match="persisted v must be a string or null"):
        row_optional_text(_row(engine, "7"), "v")


def test_row_integer_rejects_floats_and_text(engine: Engine) -> None:
    assert row_integer(_row(engine, "7"), "v") == 7
    for literal in ("7.0", "'7'", "NULL"):
        with pytest.raises(TypeError, match="persisted v must be an integer"):
            row_integer(_row(engine, literal), "v")


def test_row_real_accepts_numbers_and_returns_float(engine: Engine) -> None:
    assert row_real(_row(engine, "2"), "v") == 2.0
    assert isinstance(row_real(_row(engine, "2"), "v"), float)
    assert row_real(_row(engine, "2.5"), "v") == 2.5
    for literal in ("'2'", "NULL"):
        with pytest.raises(TypeError, match="persisted v must be a real number"):
            row_real(_row(engine, literal), "v")
