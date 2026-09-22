"""Golden tests for the literal TXT exporter (S10.02, S10.10)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from voz.application.export import TranscriptExporter, TxtExporter
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEDIA_ID = UUID("00000000-0000-0000-0000-000000000002")
TRANSCRIPT_ID = UUID("00000000-0000-0000-0000-000000000003")
TRANSCRIPT = Transcript(
    PROJECT_ID,
    MEDIA_ID,
    id=TRANSCRIPT_ID,
    language="es",
    created_at=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
)


def _segment(number: int, start_ms: int, end_ms: int, text: str) -> Segment:
    return Segment(
        TRANSCRIPT_ID,
        start_ms,
        end_ms,
        text,
        id=UUID(f"00000000-0000-0000-0000-0000000001{number:02d}"),
    )


UNORDERED_SEGMENTS = (
    _segment(2, 3_725_500, 3_730_000, "tercero, después de una hora"),
    _segment(1, 0, 1_200, "Hola mundo"),
    _segment(3, 1_200, 3_000, "línea con\nsalto interno y ñ, 日本語, 🎙️"),
)


def test_txt_exporter_satisfies_structural_port() -> None:
    exporter: TranscriptExporter = TxtExporter()

    assert isinstance(exporter, TranscriptExporter)
    assert exporter.format_id == "txt"
    assert exporter.file_extension == "txt"


def test_txt_sorts_by_start_and_preserves_text_literally() -> None:
    expected = (
        "Hola mundo\n"
        "línea con\nsalto interno y ñ, 日本語, 🎙️\n"
        "tercero, después de una hora\n"
    )

    assert TxtExporter().render(TRANSCRIPT, UNORDERED_SEGMENTS) == expected


def test_txt_with_timestamps_prefixes_each_line() -> None:
    expected = (
        "[00:00:00.000] Hola mundo\n"
        "[00:00:01.200] línea con\nsalto interno y ñ, 日本語, 🎙️\n"
        "[01:02:05.500] tercero, después de una hora\n"
    )

    rendered = TxtExporter(include_timestamps=True).render(
        TRANSCRIPT, UNORDERED_SEGMENTS
    )

    assert rendered == expected


def test_txt_empty_transcript_renders_empty_document() -> None:
    assert TxtExporter().render(TRANSCRIPT, []) == ""


def test_txt_never_normalizes_whitespace_or_punctuation() -> None:
    raw = "  doble  espacio\ty tab ... sin corregir  "

    rendered = TxtExporter().render(TRANSCRIPT, [_segment(9, 10, 20, raw)])

    assert rendered == f"{raw}\n"


def test_txt_does_not_mutate_input_order() -> None:
    segments = list(UNORDERED_SEGMENTS)

    TxtExporter().render(TRANSCRIPT, segments)

    assert segments == list(UNORDERED_SEGMENTS)
