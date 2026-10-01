"""Persistence port for the per-project glossary (S13.01)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ProjectGlossaryRepository(Protocol):
    """One short list of terms per project; absent means empty."""

    def get(self, project_id: UUID) -> tuple[str, ...]:
        """Return the stored terms (empty when the project has none)."""
        ...

    def put(self, project_id: UUID, terms: tuple[str, ...]) -> None:
        """Replace the whole list; an empty tuple clears it."""
        ...


__all__ = ["ProjectGlossaryRepository"]
