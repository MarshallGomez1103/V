"""Literal plain-text transcript export (S10.02, S10.08)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from voz.application.export.grouping import group_by_speaker
from voz.application.export.port import format_timestamp, ordered_segments
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript


@dataclass(frozen=True, slots=True)
class TxtExporter:
    """One segment per line, text verbatim, ``\\n`` line endings.

    The transcript is never altered: segment text is emitted exactly as stored,
    including embedded newlines and any Unicode.
    """

    format_id: str = field(default="txt", init=False)
    file_extension: str = field(default="txt", init=False)

    # ponytail: options live on the exporter instead of a separate request
    # object; one bool does not justify a second dataclass.
    include_timestamps: bool = False
    group_by_speaker: bool = False

    def render(
        self,
        transcript: Transcript,
        segments: Sequence[Segment],
        speakers: Sequence[Speaker] = (),
    ) -> str:
        """Render every segment on its own line; empty input yields ``""``.

        With ``group_by_speaker`` each run of one speaker is a ``Name:`` block
        and blocks are separated by a blank line.
        """

        del transcript  # accepted for the port; TXT has no header.
        if not self.group_by_speaker:
            lines = [self._line(segment) for segment in ordered_segments(segments)]
            return "".join(f"{line}\n" for line in lines)
        blocks = [
            "".join(
                [f"{label}:\n", *(f"{self._line(segment)}\n" for segment in members)]
            )
            for label, members in group_by_speaker(segments, speakers)
        ]
        return "\n".join(blocks)

    def _line(self, segment: Segment) -> str:
        if self.include_timestamps:
            return f"[{format_timestamp(segment.start_ms)}] {segment.text}"
        return segment.text


__all__ = ["TxtExporter"]
