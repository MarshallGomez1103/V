"""Pure word -> speaker reconciliation (S7.05).

A word takes the speaker of the turn that contains its midpoint; when no turn
does, it inherits the speaker of its segment. No I/O, no persistence: the
``words`` table has no speaker column, so the API view computes this on the fly.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
from itertools import accumulate
from uuid import UUID

from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker_turn import SpeakerTurn


class SpeakerTimeline:
    """Turns with a speaker, indexed to find the one covering an instant."""

    def __init__(self, turns: Iterable[SpeakerTurn]) -> None:
        ordered = sorted(
            (turn for turn in turns if turn.speaker_id is not None),
            key=lambda turn: (turn.start_ms, turn.end_ms),
        )
        self._turns = ordered
        self._starts = [turn.start_ms for turn in ordered]
        self._running_max_end = list(accumulate((t.end_ms for t in ordered), max))

    def speaker_at(self, start_ms: int, end_ms: int) -> UUID | None:
        """Speaker of the earliest turn with ``start <= midpoint < end``."""

        twice = start_ms + end_ms  # compare against 2 * midpoint: stays integer
        # Candidates lie in [low, high): those starting at or before the midpoint,
        # past the first index whose running max end exceeds it.
        low = bisect_right(self._running_max_end, twice // 2)
        high = bisect_right(self._starts, twice // 2)
        for turn in self._turns[low:high]:
            if 2 * turn.start_ms <= twice < 2 * turn.end_ms:
                return turn.speaker_id
        return None


def word_speaker_ids(
    segment: Segment, timeline: SpeakerTimeline | None = None
) -> tuple[UUID | None, ...]:
    """Speaker of each word of ``segment``, in word order.

    Without a timeline (or turn hit) a word falls back to the segment speaker.
    """

    fallback = segment.speaker_id
    if timeline is None:
        return (fallback,) * len(segment.words)
    return tuple(
        timeline.speaker_at(word.start_ms, word.end_ms) or fallback
        for word in segment.words
    )


__all__ = ["SpeakerTimeline", "word_speaker_ids"]
