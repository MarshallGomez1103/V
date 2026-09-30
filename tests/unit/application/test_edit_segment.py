"""Unit tests for EditSegmentText using an in-memory repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from voz.application.edit_segment import (
    EditSegmentText,
    SegmentNotFound,
    SegmentRevisionConflict,
    SegmentTextInvalid,
)
from voz.domain.entities.segment import Segment


class MemorySegments:
    def __init__(self, *items: Segment) -> None:
        self.items = {item.id: item for item in items}
        self.race: Segment | None = None  # stored by a "concurrent" writer

    def add(self, segment: Segment) -> None:
        self.items[segment.id] = segment

    def save(self, segment: Segment) -> None:
        self.items[segment.id] = segment

    def list_by_transcript(self, transcript_id: UUID) -> Sequence[Segment]:
        return [i for i in self.items.values() if i.transcript_id == transcript_id]

    def get(self, segment_id: UUID) -> Segment | None:
        return self.items.get(segment_id)

    def update_text_if_revision(self, segment: Segment, expected_revision: int) -> bool:
        if self.race is not None:
            self.items[self.race.id] = self.race
            self.race = None
        current = self.items.get(segment.id)
        if current is None or current.revision != expected_revision:
            return False
        self.items[segment.id] = segment
        return True

    def update_speakers(self, assignments: Mapping[UUID, UUID | None]) -> None:
        for segment_id, speaker_id in assignments.items():
            if segment_id in self.items:
                self.items[segment_id] = replace(
                    self.items[segment_id], speaker_id=speaker_id
                )


def _segment() -> Segment:
    return Segment(uuid4(), 0, 1_000, "texto asr")


def test_edit_strips_text_and_keeps_asr_literal() -> None:
    segment = _segment()
    repo = MemorySegments(segment)

    updated = EditSegmentText(repo).execute(segment.id, "  Texto corregido.  ", 0)

    assert updated.text == "Texto corregido."
    assert (updated.edited, updated.revision) == (True, 1)
    assert updated.original_text == "texto asr"
    assert repo.items[segment.id] == updated


def test_edit_unknown_segment_and_empty_text() -> None:
    segment = _segment()
    use_case = EditSegmentText(MemorySegments(segment))

    with pytest.raises(SegmentNotFound):
        use_case.execute(uuid4(), "x", 0)
    with pytest.raises(SegmentTextInvalid):
        use_case.execute(segment.id, "  \n ", 0)


def test_stale_revision_raises_conflict_with_current_segment() -> None:
    segment = _segment()
    repo = MemorySegments(segment)
    use_case = EditSegmentText(repo)
    use_case.execute(segment.id, "uno", 0)

    with pytest.raises(SegmentRevisionConflict) as raised:
        use_case.execute(segment.id, "dos", 0)

    assert raised.value.current.text == "uno"
    assert raised.value.current.revision == 1


def test_lost_race_between_read_and_update_is_a_conflict() -> None:
    segment = _segment()
    repo = MemorySegments(segment)
    repo.race = segment.edit_text("de otro")

    with pytest.raises(SegmentRevisionConflict) as raised:
        EditSegmentText(repo).execute(segment.id, "mío", 0)

    assert raised.value.current.text == "de otro"
