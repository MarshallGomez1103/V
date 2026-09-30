"""Golden tests for speaker grouping and timestamps in TXT/Markdown (S10.07, S10.08)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from voz.application.export import (
    UNKNOWN_SPEAKER_LABEL,
    MarkdownExporter,
    TxtExporter,
    group_by_speaker,
)
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
TRANSCRIPT_ID = UUID("00000000-0000-0000-0000-000000000003")
TRANSCRIPT = Transcript(
    PROJECT_ID,
    UUID("00000000-0000-0000-0000-000000000002"),
    id=TRANSCRIPT_ID,
    language="es",
    created_at=datetime(2026, 9, 21, 12, 0, tzinfo=UTC),
)
ANA = Speaker(PROJECT_ID, "Ana", "#112233", id=UUID(int=0xA1))
BRUNO = Speaker(PROJECT_ID, "Bruno_*", "#445566", id=UUID(int=0xB2))
SPEAKERS = (ANA, BRUNO)


def _segment(number: int, start_ms: int, text: str, speaker: Speaker | None) -> Segment:
    return Segment(
        TRANSCRIPT_ID,
        start_ms,
        start_ms + 500,
        text,
        id=UUID(int=number),
        speaker_id=None if speaker is None else speaker.id,
    )


# Deliberately out of order; timeline is Ana, Ana, Bruno, (none), Ana.
SEGMENTS = (
    _segment(5, 4_000, "otra vez Ana", ANA),
    _segment(2, 500, "Ana sigue", ANA),
    _segment(4, 3_000, "sin dueño", None),
    _segment(1, 0, "Hola, soy Ana", ANA),
    _segment(3, 1_000, "y yo Bruno", BRUNO),
)


def test_group_by_speaker_breaks_runs_and_labels_missing_speaker() -> None:
    groups = group_by_speaker(SEGMENTS, SPEAKERS)

    assert [(label, len(members)) for label, members in groups] == [
        ("Ana", 2),
        ("Bruno_*", 1),
        (UNKNOWN_SPEAKER_LABEL, 1),
        ("Ana", 1),
    ]


def test_group_by_speaker_treats_unknown_speaker_id_as_unlabeled() -> None:
    stranger = Speaker(PROJECT_ID, "Fuera", "#000000")

    groups = group_by_speaker([_segment(1, 0, "x", stranger)], SPEAKERS)

    assert [label for label, _ in groups] == ["Sin speaker"]


def test_txt_grouped_golden() -> None:
    expected = (
        "Ana:\n"
        "Hola, soy Ana\n"
        "Ana sigue\n"
        "\n"
        "Bruno_*:\n"
        "y yo Bruno\n"
        "\n"
        "Sin speaker:\n"
        "sin dueño\n"
        "\n"
        "Ana:\n"
        "otra vez Ana\n"
    )

    assert (
        TxtExporter(group_by_speaker=True).render(TRANSCRIPT, SEGMENTS, SPEAKERS)
        == expected
    )


def test_txt_grouped_with_timestamps_golden() -> None:
    expected = (
        "Ana:\n"
        "[00:00:00.000] Hola, soy Ana\n"
        "[00:00:00.500] Ana sigue\n"
        "\n"
        "Bruno_*:\n"
        "[00:00:01.000] y yo Bruno\n"
        "\n"
        "Sin speaker:\n"
        "[00:00:03.000] sin dueño\n"
        "\n"
        "Ana:\n"
        "[00:00:04.000] otra vez Ana\n"
    )

    rendered = TxtExporter(include_timestamps=True, group_by_speaker=True).render(
        TRANSCRIPT, SEGMENTS, SPEAKERS
    )

    assert rendered == expected


def test_markdown_grouped_golden_escapes_speaker_name() -> None:
    expected = (
        "# Transcript\n"
        "\n"
        "- Language: es\n"
        "\n"
        "## Ana\n"
        "\n"
        "**[00:00:00.000]** Hola, soy Ana\n"
        "\n"
        "**[00:00:00.500]** Ana sigue\n"
        "\n"
        "## Bruno\\_\\*\n"
        "\n"
        "**[00:00:01.000]** y yo Bruno\n"
        "\n"
        "## Sin speaker\n"
        "\n"
        "**[00:00:03.000]** sin dueño\n"
        "\n"
        "## Ana\n"
        "\n"
        "**[00:00:04.000]** otra vez Ana\n"
    )

    rendered = MarkdownExporter(include_timestamps=True, group_by_speaker=True).render(
        TRANSCRIPT, SEGMENTS, SPEAKERS
    )

    assert rendered == expected


def test_grouping_is_off_by_default_and_ignores_speakers() -> None:
    assert TxtExporter().render(TRANSCRIPT, SEGMENTS, SPEAKERS) == (
        "Hola, soy Ana\nAna sigue\ny yo Bruno\nsin dueño\notra vez Ana\n"
    )
    assert "##" not in MarkdownExporter().render(TRANSCRIPT, SEGMENTS, SPEAKERS)


def test_grouped_empty_transcript_stays_valid() -> None:
    assert TxtExporter(group_by_speaker=True).render(TRANSCRIPT, [], SPEAKERS) == ""
    assert (
        MarkdownExporter(group_by_speaker=True).render(TRANSCRIPT, [], SPEAKERS)
        == "# Transcript\n\n- Language: es\n"
    )
