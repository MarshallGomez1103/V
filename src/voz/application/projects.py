"""Create and list projects through the persistence port only."""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from voz.application.ports.project_deletion import (
    ProjectFileEraser,
    ProjectRecordEraser,
)
from voz.application.ports.repositories import (
    ProjectRepository,
    TranscriptionJobRepository,
)
from voz.application.project_glossary import ProjectNotFound
from voz.domain.entities.project import Project

_LOG = logging.getLogger(__name__)

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


class ProjectBusy(RuntimeError):
    """The project has a job that has not finished yet."""


class ProjectDeleteFailed(RuntimeError):
    """The project's files could not be deleted; nothing else was removed."""


@dataclass(frozen=True, slots=True)
class RenameProject:
    projects: ProjectRepository

    def execute(self, project_id: UUID, name: str) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise ProjectNotFound(str(project_id))
        renamed = replace(project, name=normalize_project_name(name))
        self.projects.save(renamed)
        return renamed


@dataclass(frozen=True, slots=True)
class DeleteProject:
    """Erase a project with its files; refuses while one of its jobs is running.

    Files go first: if that fails the project stays intact and the delete can be
    retried (it is idempotent); the rows are removed only once no file is left.

    # ponytail: a job created between the busy check and the delete is not
    # prevented; VOZ is single-user and the UI blocks it.
    """

    projects: ProjectRepository
    jobs: TranscriptionJobRepository
    files: ProjectFileEraser
    records: ProjectRecordEraser

    def execute(self, project_id: UUID) -> None:
        if self.projects.get(project_id) is None:
            raise ProjectNotFound(str(project_id))
        if any(
            not job.state.is_terminal for job in self.jobs.list_by_project(project_id)
        ):
            raise ProjectBusy(str(project_id))
        try:
            self.files.delete_project_files(project_id)
        except Exception as error:
            # Boundary: any eraser failure becomes a typed error; the API shows
            # a stable code, so the cause is logged here.
            _LOG.exception("Could not delete the files of project %s", project_id)
            raise ProjectDeleteFailed(str(project_id)) from error
        self.records.delete_project(project_id)


__all__ = [
    "MAX_PROJECT_NAME_LENGTH",
    "CreateProject",
    "DeleteProject",
    "InvalidProjectName",
    "ListProjects",
    "ProjectBusy",
    "ProjectDeleteFailed",
    "RenameProject",
    "normalize_project_name",
]
