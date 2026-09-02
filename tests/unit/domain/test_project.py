"""Tests for the Project domain entity."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from voz.domain.entities import Project


def test_project_generates_uuid_and_aware_timestamp() -> None:
    project = Project("Clase de arquitectura")

    assert isinstance(project.id, UUID)
    assert project.name == "Clase de arquitectura"
    assert project.created_at.utcoffset() == timedelta(0)


def test_project_normalizes_name_and_timestamp_to_utc() -> None:
    project_id = uuid4()
    created_at = datetime(2026, 9, 2, 8, tzinfo=timezone(timedelta(hours=-5)))

    project = Project(
        "  Entrevista  ",
        id=project_id,
        created_at=created_at,
    )

    assert project.id == project_id
    assert project.name == "Entrevista"
    assert project.created_at == datetime(2026, 9, 2, 13, tzinfo=UTC)


@pytest.mark.parametrize("name", ["", "   ", "clase\x00privada", "clase\nprivada"])
def test_project_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValueError):
        Project(name)


def test_project_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Project("Clase", created_at=datetime(2026, 9, 2))


def test_project_is_immutable() -> None:
    project = Project("Clase")

    with pytest.raises(FrozenInstanceError):
        project.name = "Otro nombre"  # type: ignore[misc]
