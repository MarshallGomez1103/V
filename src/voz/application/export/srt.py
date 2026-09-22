"""SubRip (SRT) export of a literal transcript."""

from collections.abc import Sequence
from dataclasses import dataclass

from voz.application.export.timestamps import format_srt_timestamp
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript


@dataclass(frozen=True, slots=True)
class SrtExporter:
    """Numbered cue blocks ordered by ``start_ms``; text is emitted verbatim."""

    format_id: str = "srt"
    file_extension: str = "srt"

    def render(
        self,
        transcript: Transcript,
        segments: Sequence[Segment],
        speakers: Sequence[Speaker] = (),
    ) -> str:
        ordered = sorted(segments, key=lambda segment: segment.start_ms)
        return "".join(
            f"{index}\n"
            f"{format_srt_timestamp(segment.start_ms)} --> "
            f"{format_srt_timestamp(segment.end_ms)}\n"
            f"{segment.text}\n\n"
            for index, segment in enumerate(ordered, start=1)
        )
