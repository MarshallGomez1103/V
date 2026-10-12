"""Strict typed readers for SQLite rows shared by the persistence adapters."""

from __future__ import annotations

from sqlalchemy import RowMapping


def row_text(row: RowMapping, key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"persisted {key} must be a string")
    return value


def row_optional_text(row: RowMapping, key: str) -> str | None:
    value = row[key]
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"persisted {key} must be a string or null")


def row_integer(row: RowMapping, key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise TypeError(f"persisted {key} must be an integer")
    return value


def row_real(row: RowMapping, key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"persisted {key} must be a real number")
    return float(value)
