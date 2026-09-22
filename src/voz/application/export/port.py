"""Structural port for transcript exporters (S10.01).

``TranscriptExporter`` is a :class:`typing.Protocol`: any class exposing
``format_id``, ``file_extension`` and ``render`` satisfies it without importing
or subclassing it. Sibling exporters (``srt.py``, ``vtt.py``,
``json_canonical.py``) conform structurally; the composition root can therefore
register them by ``format_id`` without a plugin framework.

``format_id``/``file_extension`` are read-only in the protocol so frozen
dataclass fields (``field(default=..., init=False)``) or ``@property`` satisfy
it under pyright strict. ``ClassVar`` members do not: pyright rejects them
against a non-``ClassVar`` protocol member.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript


@runtime_checkable
class TranscriptExporter(Protocol):
    """Render a literal transcript into a text-based export format."""

    @property
    def format_id(self) -> str:
        """Stable identifier used to select the exporter (e.g. ``"txt"``)."""
        ...

    @property
    def file_extension(self) -> str:
        """File extension without the leading dot (e.g. ``"txt"``)."""
        ...

    def render(
        self,
        transcript: Transcript,
        segments: Sequence[Segment],
        speakers: Sequence[Speaker] = (),
    ) -> str:
        """Return the full export document as text. Pure: no I/O."""
        ...


def ordered_segments(segments: Sequence[Segment]) -> list[Segment]:
    """Return segments in timeline order, deterministic for equal offsets."""

    return sorted(segments, key=lambda s: (s.start_ms, s.end_ms, s.id.int))


def format_timestamp(milliseconds: int) -> str:
    """Format milliseconds as ``HH:MM:SS.mmm`` (hours may exceed two digits)."""

    seconds, millis = divmod(milliseconds, 1000)
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


__all__ = ["TranscriptExporter", "format_timestamp", "ordered_segments"]
