"""Glossary validation and use case (S13.01)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from voz.application.project_glossary import (
    MAX_GLOSSARY_TERMS,
    MAX_TERM_LENGTH,
    InvalidGlossary,
    ProjectGlossary,
    ProjectNotFound,
    normalize_glossary,
)
from voz.domain.entities.project import Project


class _Projects:
    def __init__(self, *items: Project) -> None:
        self.items = {item.id: item for item in items}

    def add(self, project: Project) -> None:
        self.items[project.id] = project

    def save(self, project: Project) -> None:
        self.items[project.id] = project

    def get(self, project_id: UUID) -> Project | None:
        return self.items.get(project_id)

    def list_all(self) -> Sequence[Project]:
        return tuple(self.items.values())


class _Glossaries:
    def __init__(self) -> None:
        self.items: dict[UUID, tuple[str, ...]] = {}

    def get(self, project_id: UUID) -> tuple[str, ...]:
        return self.items.get(project_id, ())

    def put(self, project_id: UUID, terms: tuple[str, ...]) -> None:
        self.items[project_id] = terms


def test_normalize_trims_drops_blanks_and_dedupes_keeping_order() -> None:
    assert normalize_glossary([" Mitocondria ", "", "VOZ", "  ", "VOZ", "voz"]) == (
        "Mitocondria",
        "VOZ",
        "voz",
    )


@pytest.mark.parametrize(
    "terms",
    [
        ["x" * (MAX_TERM_LENGTH + 1)],
        ["bad\nterm"],
        ["tab\there"],
        [f"t{i}" for i in range(MAX_GLOSSARY_TERMS + 1)],
    ],
)
def test_normalize_rejects_invalid_terms(terms: list[str]) -> None:
    with pytest.raises(InvalidGlossary):
        normalize_glossary(terms)


def test_normalize_accepts_exact_limits() -> None:
    assert len(normalize_glossary([f"t{i}" for i in range(MAX_GLOSSARY_TERMS)])) == (
        MAX_GLOSSARY_TERMS
    )
    assert normalize_glossary(["x" * MAX_TERM_LENGTH]) == ("x" * MAX_TERM_LENGTH,)


def test_use_case_replaces_and_reads_the_glossary() -> None:
    project = Project("Clase")
    store = _Glossaries()
    service = ProjectGlossary(_Projects(project), store)

    assert service.get(project.id) == ()
    assert service.replace(project.id, [" a ", "b", "a"]) == ("a", "b")
    assert service.get(project.id) == ("a", "b")
    assert service.replace(project.id, []) == ()


def test_use_case_rejects_unknown_project_and_stores_nothing_when_invalid() -> None:
    project = Project("Clase")
    store = _Glossaries()
    service = ProjectGlossary(_Projects(project), store)

    with pytest.raises(ProjectNotFound):
        service.get(uuid4())
    with pytest.raises(ProjectNotFound):
        service.replace(uuid4(), ["a"])
    with pytest.raises(InvalidGlossary):
        service.replace(project.id, ["x" * 99])
    assert store.items == {}
