"""Structural contract tests for persistence ports."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    SegmentRepository,
    SpeakerRepository,
    SpeakerTurnRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
    WordRepository,
)
from voz.domain.entities.project import Project


class _InMemoryProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[UUID, Project] = {}

    def add(self, project: Project) -> None:
        self.projects[project.id] = project

    def save(self, project: Project) -> None:
        self.projects[project.id] = project

    def get(self, project_id: UUID) -> Project | None:
        return self.projects.get(project_id)

    def list_all(self) -> Sequence[Project]:
        return tuple(self.projects.values())


class _MissingSaveProjectRepository:
    def add(self, project: Project) -> None:
        pass

    def get(self, project_id: UUID) -> Project | None:
        return None

    def list_all(self) -> Sequence[Project]:
        return ()


def _accept_project_repository(repository: ProjectRepository) -> ProjectRepository:
    """Make Pyright verify structural conformance of the test adapter."""
    return repository


def test_project_repository_is_structural_and_returns_domain_entities() -> None:
    adapter = _InMemoryProjectRepository()
    repository = _accept_project_repository(adapter)
    project = Project("Clase de arquitectura", id=uuid4())

    assert isinstance(adapter, ProjectRepository)
    repository.add(project)
    assert repository.get(project.id) is project
    assert repository.list_all() == (project,)
    assert repository.get(uuid4()) is None


def test_runtime_protocol_rejects_adapter_missing_required_operation() -> None:
    assert not isinstance(_MissingSaveProjectRepository(), ProjectRepository)


def test_repository_ports_expose_complete_owner_queries() -> None:
    expected_operations = {
        ProjectRepository: {"add", "save", "get", "list_all"},
        MediaAssetRepository: {"add", "save", "get", "list_by_project"},
        TranscriptRepository: {
            "add",
            "save",
            "get",
            "list_by_project",
            "list_by_media_asset",
        },
        SegmentRepository: {"add", "save", "get", "list_by_transcript"},
        WordRepository: {"add", "save", "get", "list_by_segment"},
        SpeakerRepository: {"add", "save", "get", "list_by_project"},
        SpeakerTurnRepository: {
            "add",
            "save",
            "get",
            "list_by_transcript",
            "list_by_speaker",
        },
        TranscriptionJobRepository: {
            "add",
            "save",
            "get",
            "list_by_project",
            "list_by_media_asset",
            "list_recoverable",
        },
    }

    for repository, operations in expected_operations.items():
        assert operations <= repository.__dict__.keys()
