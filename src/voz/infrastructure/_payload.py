"""Argument guards shared by infrastructure adapters."""

from __future__ import annotations

from uuid import UUID


def require_uuid(value: object, *, field: str) -> None:
    """Reject identifiers that are not real ``UUID`` objects."""
    if not isinstance(value, UUID):
        raise TypeError(f"{field} must be a UUID")
