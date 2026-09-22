"""Golden and round-trip tests for the canonical JSON transcript document."""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from voz.application.export.json_canonical import (
    CanonicalJsonError,
    JsonExporter,
    parse_canonical_json,
)
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.word import Word

PROJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
MEDIA_ID = UUID("00000000-0000-4000-8000-000000000002")
TRANSCRIPT_ID = UUID("00000000-0000-4000-8000-000000000003")
SEGMENT_A = UUID("00000000-0000-4000-8000-000000000021")
SEGMENT_B = UUID("00000000-0000-4000-8000-000000000022")
CREATED_AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)

TRANSCRIPT = Transcript(
    PROJECT_ID, MEDIA_ID, id=TRANSCRIPT_ID, language="es", created_at=CREATED_AT
)
SPEAKER = Speaker(
    PROJECT_ID,
    "Ana",
    "#ff0000",
    id=UUID("00000000-0000-4000-8000-000000000010"),
    created_at=CREATED_AT,
    updated_at=CREATED_AT,
)
WITH_WORDS = Segment(
    TRANSCRIPT_ID,
    0,
    1250,
    "Hola mundo",
    id=SEGMENT_A,
    words=(
        Word(
            SEGMENT_A, 0, 500, "Hola", id=UUID("00000000-0000-4000-8000-000000000031")
        ),
        Word(
            SEGMENT_A,
            600,
            1250,
            "mundo",
            id=UUID("00000000-0000-4000-8000-000000000032"),
        ),
    ),
)
WITHOUT_WORDS = Segment(
    TRANSCRIPT_ID, 3599999, 3600500, "Año nuevo — fin.", id=SEGMENT_B
)

GOLDEN = """{
  "format": "voz.transcript",
  "segments": [
    {
      "end_ms": 1250,
      "id": "00000000-0000-4000-8000-000000000021",
      "start_ms": 0,
      "text": "Hola mundo",
      "words": [
        {
          "end_ms": 500,
          "id": "00000000-0000-4000-8000-000000000031",
          "start_ms": 0,
          "text": "Hola"
        },
        {
          "end_ms": 1250,
          "id": "00000000-0000-4000-8000-000000000032",
          "start_ms": 600,
          "text": "mundo"
        }
      ]
    },
    {
      "end_ms": 3600500,
      "id": "00000000-0000-4000-8000-000000000022",
      "start_ms": 3599999,
      "text": "Año nuevo — fin.",
      "words": []
    }
  ],
  "speakers": [
    {
      "color": "#ff0000",
      "id": "00000000-0000-4000-8000-000000000010",
      "name": "Ana"
    }
  ],
  "transcript": {
    "created_at": "2024-01-02T03:04:05+00:00",
    "id": "00000000-0000-4000-8000-000000000003",
    "language": "es",
    "media_asset_id": "00000000-0000-4000-8000-000000000002",
    "project_id": "00000000-0000-4000-8000-000000000001"
  },
  "version": 1
}
"""


def test_golden_document_sorts_segments_and_keys() -> None:
    # Segments passed out of order; the document orders them by start_ms.
    rendered = JsonExporter().render(
        TRANSCRIPT, (WITHOUT_WORDS, WITH_WORDS), (SPEAKER,)
    )
    assert rendered == GOLDEN


def test_format_metadata() -> None:
    assert (JsonExporter().format_id, JsonExporter().file_extension) == ("json", "json")


def test_round_trip_with_and_without_words() -> None:
    rendered = JsonExporter().render(
        TRANSCRIPT, (WITH_WORDS, WITHOUT_WORDS), (SPEAKER,)
    )
    transcript, segments, speakers = parse_canonical_json(rendered)
    assert transcript == TRANSCRIPT
    assert segments == (WITH_WORDS, WITHOUT_WORDS)
    # Audit timestamps are not part of the document; identity and labels are.
    assert [(s.id, s.name, s.color, s.project_id) for s in speakers] == [
        (SPEAKER.id, SPEAKER.name, SPEAKER.color, PROJECT_ID)
    ]
    assert JsonExporter().render(transcript, segments, speakers) == rendered


def test_round_trip_preserves_null_language_and_non_utc_zone() -> None:
    transcript = Transcript(
        PROJECT_ID,
        MEDIA_ID,
        id=TRANSCRIPT_ID,
        created_at=datetime(2024, 6, 1, 12, tzinfo=timezone(timedelta(hours=-5))),
    )
    rendered = JsonExporter().render(transcript, ())
    parsed, segments, speakers = parse_canonical_json(rendered)
    assert parsed == transcript
    assert parsed.language is None
    assert (segments, speakers) == ((), ())


_NO_WORDS: list[object] = []


def _document(**overrides: object) -> str:
    document = json.loads(GOLDEN)
    document.update(overrides)
    return json.dumps(document)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("{not json", "malformed_json"),
        ("[]", "invalid_structure"),
        (_document(version=2), "unsupported_version"),
        (_document(version="1"), "unsupported_version"),
        (_document(format="other"), "unsupported_format"),
        (_document(segments={}), "invalid_structure"),
        (
            _document(speakers=[{"id": "x", "name": "A", "color": "#000000"}]),
            "invalid_structure",
        ),
        (
            _document(transcript={"id": "00000000-0000-4000-8000-000000000003"}),
            "invalid_structure",
        ),
        (
            _document(
                transcript={
                    "id": "00000000-0000-4000-8000-000000000003",
                    "project_id": "00000000-0000-4000-8000-000000000001",
                    "media_asset_id": "00000000-0000-4000-8000-000000000002",
                    "language": None,
                    "created_at": "2024-01-02T03:04:05",
                }
            ),
            "invalid_structure",
        ),
        (
            _document(
                segments=[
                    {
                        "id": "00000000-0000-4000-8000-000000000021",
                        "start_ms": 10,
                        "end_ms": 5,
                        "text": "reversed",
                        "words": _NO_WORDS,
                    }
                ]
            ),
            "invalid_entity",
        ),
        (
            _document(
                speakers=[
                    {
                        "id": "00000000-0000-4000-8000-000000000010",
                        "name": "Ana",
                        "color": "red",
                    }
                ]
            ),
            "invalid_entity",
        ),
    ],
)
def test_parse_errors_are_typed(text: str, code: str) -> None:
    with pytest.raises(CanonicalJsonError) as info:
        parse_canonical_json(text)
    assert info.value.code == code
    assert isinstance(info.value, ValueError)
