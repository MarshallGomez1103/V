"""Speaker grouping shared by the TXT and Markdown exporters (S10.07)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from voz.application.export.port import ordered_segments
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker

UNKNOWN_SPEAKER_LABEL = "Sin speaker"


def group_by_speaker(
    segments: Sequence[Segment], speakers: Sequence[Speaker]
) -> list[tuple[str, list[Segment]]]:
    """Group consecutive segments of the same speaker under the speaker's name.

    Segments keep timeline order. A run breaks whenever ``speaker_id`` changes,
    so a speaker who talks again later gets a new group. Segments without a
    speaker (or whose speaker is not in ``speakers``) use ``Sin speaker``.
    """

    names: dict[UUID | None, str] = {speaker.id: speaker.name for speaker in speakers}
    groups: list[tuple[str, list[Segment]]] = []
    previous: UUID | None = None
    for segment in ordered_segments(segments):
        if groups and segment.speaker_id == previous:
            groups[-1][1].append(segment)
        else:
            label = names.get(segment.speaker_id, UNKNOWN_SPEAKER_LABEL)
            groups.append((label, [segment]))
        previous = segment.speaker_id
    return groups


__all__ = ["UNKNOWN_SPEAKER_LABEL", "group_by_speaker"]
