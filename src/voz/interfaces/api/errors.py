"""Shared builder for the stable ``{"detail": {"code", "message"}}`` error body."""

from __future__ import annotations

from fastapi import HTTPException


def api_error(
    status_code: int, code: str, message: str, **extra: object
) -> HTTPException:
    """Return an ``HTTPException`` whose detail is ``{code, message, **extra}``."""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
    )


__all__ = ["api_error"]
