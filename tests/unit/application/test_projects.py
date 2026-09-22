"""Use-case behaviour for creating and listing projects with a fake repository."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from voz.application.projects import (
    MAX_PROJECT_NAME_LENGTH,
    CreateProject,
    InvalidProjectName,
    ListProjects,
)
from voz.domain.entities.project import Project

BASE_TIME = datetime(2026, 9, 21, 8, tzinfo=UTC)


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[UUID, Project] = {}

    def add(self, project: Project) -> None:
        if project.id in self.projects:
            raise ValueError("duplicate project")
        self.projects[project.id] = project

    def save(self, project: Project) -> None:
        self.projects[project.id] = project

    def get(self, project_id: UUID) -> Project | None:
        return self.projects.get(project_id)

    def list_all(self) -> Sequence[Project]:
        return tuple(self.projects.values())


def test_create_persists_trimmed_name_and_returns_stored_entity() -> None:
    repository = InMemoryProjectRepository()

    project = CreateProject(repository).execute(name="  Clase de redes  ")

    assert project.name == "Clase de redes"
    assert project.created_at.tzinfo is not None
    assert repository.get(project.id) == project


def test_create_accepts_name_at_maximum_length() -> None:
    repository = InMemoryProjectRepository()
    name = "x" * MAX_PROJECT_NAME_LENGTH

    assert CreateProject(repository).execute(name=name).name == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "\t\n",
        "x" * (MAX_PROJECT_NAME_LENGTH + 1),
        "a\x00b",
        "a\nb",
        "a\x7fb",
    ],
)
def test_create_rejects_invalid_names_without_persisting(name: str) -> None:
    repository = InMemoryProjectRepository()

    with pytest.raises(InvalidProjectName):
        CreateProject(repository).execute(name=name)

    assert repository.projects == {}


def test_invalid_name_is_a_value_error_with_safe_message() -> None:
    with pytest.raises(ValueError, match="control characters"):
        CreateProject(InMemoryProjectRepository()).execute(name="bad\x01name")


def test_list_returns_newest_first_regardless_of_insertion_order() -> None:
    repository = InMemoryProjectRepository()
    middle = Project("Middle", created_at=BASE_TIME)
    oldest = Project("Oldest", created_at=BASE_TIME - timedelta(days=1))
    newest = Project("Newest", created_at=BASE_TIME + timedelta(days=1))
    for project in (middle, oldest, newest):
        repository.add(project)

    assert ListProjects(repository).execute() == (newest, middle, oldest)


def test_list_is_empty_for_fresh_repository() -> None:
    assert ListProjects(InMemoryProjectRepository()).execute() == ()
