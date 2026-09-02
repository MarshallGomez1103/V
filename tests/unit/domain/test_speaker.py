"""Unit tests for the editable Speaker domain identity."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from voz.domain.entities.speaker import Speaker


def test_speaker_generates_identity_and_aware_timestamps() -> None:
    project_id = uuid4()

    speaker = Speaker(project_id, "Profesor", "#A1B2C3")

    assert isinstance(speaker.id, UUID)
    assert speaker.project_id == project_id
    assert speaker.name == "Profesor"
    assert speaker.color == "#a1b2c3"
    assert speaker.created_at.utcoffset() == timedelta(0)
    assert speaker.updated_at.utcoffset() == timedelta(0)


def test_speaker_rename_returns_a_new_snapshot_with_the_same_identity() -> None:
    created_at = datetime(2026, 9, 2, 12, tzinfo=UTC)
    renamed_at = datetime(2026, 9, 2, 13, tzinfo=UTC)
    speaker = Speaker(
        uuid4(),
        "SPEAKER_00",
        "#123456",
        created_at=created_at,
        updated_at=created_at,
    )

    renamed = speaker.rename("  Profesora  ", updated_at=renamed_at)

    assert speaker.name == "SPEAKER_00"
    assert renamed.name == "Profesora"
    assert renamed.id == speaker.id
    assert renamed.project_id == speaker.project_id
    assert renamed.color == speaker.color
    assert renamed.created_at == speaker.created_at
    assert renamed.updated_at == renamed_at


def test_speaker_normalizes_aware_timestamps_to_utc() -> None:
    bogota = timezone(timedelta(hours=-5))
    created_at = datetime(2026, 9, 2, 7, tzinfo=bogota)
    updated_at = datetime(2026, 9, 2, 8, tzinfo=bogota)

    speaker = Speaker(
        uuid4(),
        "Invitado",
        "#abcdef",
        created_at=created_at,
        updated_at=updated_at,
    )

    assert speaker.created_at == datetime(2026, 9, 2, 12, tzinfo=UTC)
    assert speaker.updated_at == datetime(2026, 9, 2, 13, tzinfo=UTC)


@pytest.mark.parametrize("name", ["", "   ", "Profesor\nOtro"])
def test_speaker_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValueError):
        Speaker(uuid4(), name, "#123456")


@pytest.mark.parametrize(
    "color",
    ["", "123456", "#fff", "#1234567", "#ghijkl"],
)
def test_speaker_rejects_invalid_colors(color: str) -> None:
    with pytest.raises(ValueError, match="#RRGGBB"):
        Speaker(uuid4(), "Profesor", color)


def test_speaker_rejects_naive_or_regressive_timestamps() -> None:
    aware = datetime(2026, 9, 2, 12, tzinfo=UTC)

    with pytest.raises(ValueError, match="timezone-aware"):
        Speaker(uuid4(), "Profesor", "#123456", created_at=datetime(2026, 9, 2))
    with pytest.raises(ValueError, match="before created_at"):
        Speaker(
            uuid4(),
            "Profesor",
            "#123456",
            created_at=aware,
            updated_at=aware - timedelta(seconds=1),
        )


def test_speaker_rejects_rename_before_creation() -> None:
    created_at = datetime(2026, 9, 2, 12, tzinfo=UTC)
    speaker = Speaker(
        uuid4(),
        "Profesor",
        "#123456",
        created_at=created_at,
        updated_at=created_at,
    )

    with pytest.raises(ValueError, match="before created_at"):
        speaker.rename("Docente", updated_at=created_at - timedelta(seconds=1))


def test_speaker_rejects_rename_before_current_snapshot() -> None:
    created_at = datetime(2026, 9, 2, 12, tzinfo=UTC)
    updated_at = datetime(2026, 9, 2, 14, tzinfo=UTC)
    speaker = Speaker(
        uuid4(),
        "Profesor",
        "#123456",
        created_at=created_at,
        updated_at=updated_at,
    )

    with pytest.raises(ValueError, match="before current updated_at"):
        speaker.rename(
            "Docente",
            updated_at=datetime(2026, 9, 2, 13, tzinfo=UTC),
        )


def test_speaker_is_immutable() -> None:
    speaker = Speaker(uuid4(), "Profesor", "#123456")

    with pytest.raises(FrozenInstanceError):
        speaker.name = "Docente"  # type: ignore[misc]
