"""WebVTT export of a literal transcript."""

from collections.abc import Sequence
from dataclasses import dataclass

from voz.application.export.timestamps import format_vtt_timestamp
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript


@dataclass(frozen=True, slots=True)
class VttExporter:
    """``WEBVTT`` header followed by unnumbered cues ordered by ``start_ms``."""

    format_id: str = "vtt"
    file_extension: str = "vtt"

    def render(
        self,
        transcript: Transcript,
        segments: Sequence[Segment],
        speakers: Sequence[Speaker] = (),
    ) -> str:
        ordered = sorted(segments, key=lambda segment: segment.start_ms)
        cues = "".join(
            f"{format_vtt_timestamp(segment.start_ms)} --> "
            f"{format_vtt_timestamp(segment.end_ms)}\n"
            f"{segment.text}\n\n"
            for segment in ordered
        )
        return "WEBVTT\n\n" + cues
