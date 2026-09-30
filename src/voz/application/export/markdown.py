"""Markdown transcript export (S10.03)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from voz.application.export.grouping import group_by_speaker
from voz.application.export.port import format_timestamp, ordered_segments
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript

# ponytail: minimal escape table for inline/block Markdown syntax. Deliberately
# not a full sanitizer; list markers ("-", "1.") at line start are left as-is.
_MARKDOWN_ESCAPES = str.maketrans(
    {
        "\\": "\\\\",
        "*": "\\*",
        "_": "\\_",
        "`": "\\`",
        "#": "\\#",
        "[": "\\[",
        "]": "\\]",
        "<": "\\<",
        ">": "\\>",
    }
)


def escape_markdown(text: str) -> str:
    """Backslash-escape characters that would change Markdown structure."""

    return text.translate(_MARKDOWN_ESCAPES)


@dataclass(frozen=True, slots=True)
class MarkdownExporter:
    """``# Transcript`` heading, optional metadata, one paragraph per segment."""

    format_id: str = field(default="markdown", init=False)
    file_extension: str = field(default="md", init=False)

    include_timestamps: bool = False
    group_by_speaker: bool = False

    def render(
        self,
        transcript: Transcript,
        segments: Sequence[Segment],
        speakers: Sequence[Speaker] = (),
    ) -> str:
        """Render the document; an empty transcript still yields a valid file."""

        blocks = ["# Transcript"]
        if transcript.language is not None:
            blocks.append(f"- Language: {escape_markdown(transcript.language)}")
        if self.group_by_speaker:
            for label, members in group_by_speaker(segments, speakers):
                blocks.append(f"## {escape_markdown(label)}")
                blocks.extend(self._paragraph(segment) for segment in members)
        else:
            blocks.extend(
                self._paragraph(segment) for segment in ordered_segments(segments)
            )
        return "\n\n".join(blocks) + "\n"

    def _paragraph(self, segment: Segment) -> str:
        body = escape_markdown(segment.text)
        if self.include_timestamps:
            return f"**[{format_timestamp(segment.start_ms)}]** {body}"
        return body


__all__ = ["MarkdownExporter", "escape_markdown"]
