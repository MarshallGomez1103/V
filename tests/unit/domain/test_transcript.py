"""Tests for the Transcript domain entity."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from voz.domain.entities import Transcript


def test_transcript_links_project_and_media_with_own_identity() -> None:
    project_id = uuid4()
    media_asset_id = uuid4()

    transcript = Transcript(
        project_id,
        media_asset_id,
        language="es-CO",
    )

    assert isinstance(transcript.id, UUID)
    assert transcript.project_id == project_id
    assert transcript.media_asset_id == media_asset_id
    assert transcript.language == "es-CO"
    assert transcript.created_at.utcoffset() == timedelta(0)


def test_transcript_accepts_unknown_language() -> None:
    transcript = Transcript(uuid4(), uuid4())

    assert transcript.language is None


def test_transcript_trims_language_without_changing_its_value() -> None:
    transcript = Transcript(uuid4(), uuid4(), language="  es-CO  ")

    assert transcript.language == "es-CO"


@pytest.mark.parametrize("language", ["", "   ", "\x00"])
def test_transcript_rejects_invalid_language(language: str) -> None:
    with pytest.raises(ValueError):
        Transcript(uuid4(), uuid4(), language=language)


def test_transcript_normalizes_aware_datetime_to_utc() -> None:
    created_at = datetime(2026, 9, 2, 9, tzinfo=timezone(timedelta(hours=-5)))

    transcript = Transcript(uuid4(), uuid4(), created_at=created_at)

    assert transcript.created_at == datetime(2026, 9, 2, 14, tzinfo=UTC)


def test_transcript_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Transcript(uuid4(), uuid4(), created_at=datetime(2026, 9, 2))


def test_transcript_rejects_non_uuid_media_identity() -> None:
    with pytest.raises(TypeError, match="media_asset_id"):
        Transcript(uuid4(), "media")  # type: ignore[arg-type]
