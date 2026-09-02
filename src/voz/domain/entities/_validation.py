"""Shared validation helpers for framework-independent domain entities."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID


def require_aware_datetime(value: object, *, field: str) -> datetime:
    """Return ``value`` normalized to UTC, rejecting naive datetimes."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def require_non_blank(value: object, *, field: str) -> str:
    """Return trimmed text without blank or control characters."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{field} must not contain control characters")
    return normalized


def require_uuid(value: object, *, field: str) -> UUID:
    """Return a UUID identity, rejecting serialized or arbitrary values."""
    if not isinstance(value, UUID):
        raise TypeError(f"{field} must be a UUID")
    return value


def require_positive_int(value: object, *, field: str) -> int:
    """Return a positive integer while excluding booleans."""
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    if value <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return value
