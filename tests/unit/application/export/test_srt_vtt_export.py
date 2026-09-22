"""Golden tests for SRT and WebVTT rendering with fixed identities and offsets."""

from datetime import UTC, datetime
from uuid import UUID

from voz.application.export.srt import SrtExporter
from voz.application.export.vtt import VttExporter
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript

PROJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
MEDIA_ID = UUID("00000000-0000-4000-8000-000000000002")
TRANSCRIPT_ID = UUID("00000000-0000-4000-8000-000000000003")
CREATED_AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)

TRANSCRIPT = Transcript(
    PROJECT_ID,
    MEDIA_ID,
    id=TRANSCRIPT_ID,
    language="es",
    created_at=CREATED_AT,
)
SPEAKER = Speaker(
    PROJECT_ID,
    "Ana",
    "#ff0000",
    id=UUID("00000000-0000-4000-8000-000000000010"),
    created_at=CREATED_AT,
    updated_at=CREATED_AT,
)
# Deliberately out of order: exporters must sort by start_ms.
SEGMENTS = (
    Segment(
        TRANSCRIPT_ID,
        3599999,
        3600500,
        "Hasta luego, año nuevo.",
        id=UUID("00000000-0000-4000-8000-000000000022"),
    ),
    Segment(
        TRANSCRIPT_ID,
        0,
        1250,
        "Hola mundo",
        id=UUID("00000000-0000-4000-8000-000000000021"),
    ),
)


def test_srt_golden() -> None:
    expected = (
        "1\n"
        "00:00:00,000 --> 00:00:01,250\n"
        "Hola mundo\n"
        "\n"
        "2\n"
        "00:59:59,999 --> 01:00:00,500\n"
        "Hasta luego, año nuevo.\n"
        "\n"
    )
    assert SrtExporter().render(TRANSCRIPT, SEGMENTS, (SPEAKER,)) == expected


def test_vtt_golden() -> None:
    expected = (
        "WEBVTT\n"
        "\n"
        "00:00:00.000 --> 00:00:01.250\n"
        "Hola mundo\n"
        "\n"
        "00:59:59.999 --> 01:00:00.500\n"
        "Hasta luego, año nuevo.\n"
        "\n"
    )
    assert VttExporter().render(TRANSCRIPT, SEGMENTS) == expected


def test_empty_transcripts() -> None:
    assert SrtExporter().render(TRANSCRIPT, ()) == ""
    assert VttExporter().render(TRANSCRIPT, ()) == "WEBVTT\n\n"


def test_format_metadata() -> None:
    assert (SrtExporter().format_id, SrtExporter().file_extension) == ("srt", "srt")
    assert (VttExporter().format_id, VttExporter().file_extension) == ("vtt", "vtt")


def test_render_is_deterministic_and_text_literal() -> None:
    segment = Segment(TRANSCRIPT_ID, 10, 20, "  espacios <b>y</b> símbolos -- ")
    first = SrtExporter().render(TRANSCRIPT, (segment,))
    assert first == SrtExporter().render(TRANSCRIPT, (segment,))
    assert "  espacios <b>y</b> símbolos -- \n" in first
