"""Golden tests for the Markdown exporter (S10.03, S10.10)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from voz.application.export import (
    MarkdownExporter,
    TranscriptExporter,
    escape_markdown,
)
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEDIA_ID = UUID("00000000-0000-0000-0000-000000000002")
TRANSCRIPT_ID = UUID("00000000-0000-0000-0000-000000000003")
CREATED_AT = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
TRANSCRIPT = Transcript(
    PROJECT_ID, MEDIA_ID, id=TRANSCRIPT_ID, language="es", created_at=CREATED_AT
)
TRANSCRIPT_NO_LANGUAGE = Transcript(
    PROJECT_ID, MEDIA_ID, id=TRANSCRIPT_ID, created_at=CREATED_AT
)


def _segment(number: int, start_ms: int, end_ms: int, text: str) -> Segment:
    return Segment(
        TRANSCRIPT_ID,
        start_ms,
        end_ms,
        text,
        id=UUID(f"00000000-0000-0000-0000-0000000002{number:02d}"),
    )


UNORDERED_SEGMENTS = (
    _segment(2, 3_725_500, 3_730_000, "tercero, después de una hora"),
    _segment(1, 0, 1_200, "Hola mundo"),
    _segment(3, 1_200, 3_000, "línea con\nsalto interno y ñ, 日本語, 🎙️"),
)


def test_markdown_exporter_satisfies_structural_port() -> None:
    exporter: TranscriptExporter = MarkdownExporter()

    assert isinstance(exporter, TranscriptExporter)
    assert exporter.format_id == "markdown"
    assert exporter.file_extension == "md"


def test_markdown_golden_with_language_and_sorted_paragraphs() -> None:
    expected = (
        "# Transcript\n"
        "\n"
        "- Language: es\n"
        "\n"
        "Hola mundo\n"
        "\n"
        "línea con\nsalto interno y ñ, 日本語, 🎙️\n"
        "\n"
        "tercero, después de una hora\n"
    )

    assert MarkdownExporter().render(TRANSCRIPT, UNORDERED_SEGMENTS) == expected


def test_markdown_with_timestamps_bolds_prefix() -> None:
    expected = (
        "# Transcript\n"
        "\n"
        "- Language: es\n"
        "\n"
        "**[00:00:00.000]** Hola mundo\n"
        "\n"
        "**[00:00:01.200]** línea con\nsalto interno y ñ, 日本語, 🎙️\n"
        "\n"
        "**[01:02:05.500]** tercero, después de una hora\n"
    )

    rendered = MarkdownExporter(include_timestamps=True).render(
        TRANSCRIPT, UNORDERED_SEGMENTS
    )

    assert rendered == expected


def test_markdown_empty_transcript_without_language_is_valid_document() -> None:
    assert MarkdownExporter().render(TRANSCRIPT_NO_LANGUAGE, []) == "# Transcript\n"


def test_markdown_escapes_structural_characters_minimally() -> None:
    segment = _segment(9, 10, 20, "# no *es* _título_ `ni` [link](x) <b>\\")
    expected = (
        "# Transcript\n"
        "\n"
        "- Language: es\n"
        "\n"
        "\\# no \\*es\\* \\_título\\_ \\`ni\\` \\[link\\](x) \\<b\\>\\\\\n"
    )

    assert MarkdownExporter().render(TRANSCRIPT, [segment]) == expected


def test_escape_markdown_leaves_plain_text_untouched() -> None:
    plain = "Texto plano con ñ, 日本語 y 🎙️. ¿Sin cambios? ¡Sí!"

    assert escape_markdown(plain) == plain
