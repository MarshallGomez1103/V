"""Create and list projects through the persistence port only."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from voz.application.ports.repositories import ProjectRepository
from voz.domain.entities.project import Project

MAX_PROJECT_NAME_LENGTH = 200


class InvalidProjectName(ValueError):
    """The supplied project name cannot become a project."""


def normalize_project_name(name: str) -> str:
    """Return the trimmed name or raise ``InvalidProjectName`` with a safe message."""
    normalized = name.strip()
    if not normalized:
        raise InvalidProjectName("Project name must not be blank.")
    if len(normalized) > MAX_PROJECT_NAME_LENGTH:
        raise InvalidProjectName(
            f"Project name must be at most {MAX_PROJECT_NAME_LENGTH} characters."
        )
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise InvalidProjectName("Project name must not contain control characters.")
    return normalized


@dataclass(frozen=True, slots=True)
class CreateProject:
    projects: ProjectRepository

    def execute(self, *, name: str) -> Project:
        project = Project(normalize_project_name(name))
        self.projects.add(project)
        return project


@dataclass(frozen=True, slots=True)
class ListProjects:
    projects: ProjectRepository

    def execute(self) -> Sequence[Project]:
        """Newest first; identity breaks ties so the order is deterministic."""
        return tuple(
            sorted(
                self.projects.list_all(),
                key=lambda project: (project.created_at, str(project.id)),
                reverse=True,
            )
        )


__all__ = [
    "MAX_PROJECT_NAME_LENGTH",
    "CreateProject",
    "InvalidProjectName",
    "ListProjects",
    "normalize_project_name",
]
