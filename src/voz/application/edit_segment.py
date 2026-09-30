"""Use case: correct the text of one transcript segment with optimistic locking."""

from __future__ import annotations

from uuid import UUID

from voz.application.ports.repositories import SegmentRepository
from voz.domain.entities.segment import Segment


class SegmentNotFound(Exception):
    """The segment does not exist."""


class SegmentTextInvalid(ValueError):
    """The new text is empty once surrounding whitespace is removed."""


class SegmentRevisionConflict(Exception):
    """The caller edited a stale revision; ``current`` is the stored segment."""

    def __init__(self, current: Segment) -> None:
        super().__init__(f"segment {current.id} is at revision {current.revision}")
        self.current = current


class EditSegmentText:
    """Replace a segment's text; the literal ASR text is kept in ``original_text``."""

    def __init__(self, segments: SegmentRepository) -> None:
        self._segments = segments

    def execute(self, segment_id: UUID, text: str, expected_revision: int) -> Segment:
        clean = text.strip()
        if not clean:
            raise SegmentTextInvalid("segment text cannot be empty")
        current = self._segments.get(segment_id)
        if current is None:
            raise SegmentNotFound(str(segment_id))
        if current.revision != expected_revision:
            raise SegmentRevisionConflict(current)
        updated = current.edit_text(clean)
        if not self._segments.update_text_if_revision(updated, expected_revision):
            # Lost a race between the read above and the conditional UPDATE.
            latest = self._segments.get(segment_id)
            if latest is None:
                raise SegmentNotFound(str(segment_id))
            raise SegmentRevisionConflict(latest)
        return updated
