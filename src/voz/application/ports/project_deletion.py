"""Ports to erase a project: its files first, then its records."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ProjectFileEraser(Protocol):
    """Remove everything a project keeps on disk (originals and derivatives)."""

    def delete_project_files(self, project_id: UUID) -> None:
        """Idempotently delete the project's files; raise on failure."""
        ...


@runtime_checkable
class ProjectRecordEraser(Protocol):
    """Remove a project row and everything that depends on it, atomically."""

    def delete_project(self, project_id: UUID) -> bool:
        """Cascade-delete everything the project owns; ``False`` if it was absent."""
        ...


__all__ = ["ProjectFileEraser", "ProjectRecordEraser"]
