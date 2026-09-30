"""Pure reconciliation of acoustic diarization turns with ASR segments.

Each segment gets the cluster that covers most of it; a segment barely covered
(or not covered) by any turn gets ``None``. No I/O and no identities: mapping
clusters to editable speakers is the job of ``AssignSpeakers``.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import accumulate
from uuid import UUID

from voz.application.ports.diarization import DiarizedTurn
from voz.domain.entities.segment import Segment

DEFAULT_MIN_OVERLAP_RATIO = 0.3


@dataclass(frozen=True, slots=True)
class SpeakerReconciliation:
    """Outcome of matching turns to segments."""

    assignments: Mapping[UUID, str | None]
    cluster_order: tuple[str, ...]
    """Every cluster of the input turns by first appearance in time."""


def _covered_ms(intervals: list[tuple[int, int]]) -> int:
    """Length of the union of sorted-by-start intervals."""

    total = 0
    current_end = -1
    for start, end in intervals:
        start = max(start, current_end)
        if end > start:
            total += end - start
            current_end = end
    return total


def reconcile_turns(
    segments: Sequence[Segment],
    turns: Sequence[DiarizedTurn],
    *,
    min_overlap_ratio: float = DEFAULT_MIN_OVERLAP_RATIO,
) -> SpeakerReconciliation:
    """Assign each segment the cluster with the largest temporal overlap.

    Rules: the winner is the cluster whose union of turns overlaps the segment
    the most (overlapping turns of one cluster are not double counted); ties go
    to the cluster that started earlier inside the segment, then to the one that
    appears first overall. Overlap of zero, or below ``min_overlap_ratio`` of
    the segment duration, yields ``None``. Overlapped speech still yields a
    single speaker per segment (ponytail: sin multi-speaker por segmento).
    Inputs may come in any order and are not mutated.
    """

    if not 0 <= min_overlap_ratio <= 1:
        raise ValueError("min_overlap_ratio must be between 0 and 1")

    ordered = sorted(
        enumerate(turns), key=lambda item: (item[1].start_ms, item[1].end_ms, item[0])
    )
    ordered_turns = [turn for _, turn in ordered]
    cluster_order: list[str] = []
    for turn in ordered_turns:
        if turn.cluster not in cluster_order:
            cluster_order.append(turn.cluster)
    rank = {cluster: index for index, cluster in enumerate(cluster_order)}

    starts = [turn.start_ms for turn in ordered_turns]
    running_max_end = list(accumulate((turn.end_ms for turn in ordered_turns), max))

    assignments: dict[UUID, str | None] = {}
    for segment in segments:
        # Turns that can touch the segment lie in ordered_turns[low:high].
        low = bisect_right(running_max_end, segment.start_ms)
        high = bisect_left(starts, segment.end_ms)
        by_cluster: dict[str, list[tuple[int, int]]] = {}
        for turn in ordered_turns[low:high]:
            start = max(turn.start_ms, segment.start_ms)
            end = min(turn.end_ms, segment.end_ms)
            if end > start:
                by_cluster.setdefault(turn.cluster, []).append((start, end))

        best: tuple[int, int, int, str] | None = None
        for cluster, intervals in by_cluster.items():
            key = (-_covered_ms(intervals), intervals[0][0], rank[cluster], cluster)
            if best is None or key < best:
                best = key
        duration = segment.end_ms - segment.start_ms
        if best is None or -best[0] < min_overlap_ratio * duration:
            assignments[segment.id] = None
        else:
            assignments[segment.id] = best[3]

    return SpeakerReconciliation(assignments, tuple(cluster_order))


__all__ = ["DEFAULT_MIN_OVERLAP_RATIO", "SpeakerReconciliation", "reconcile_turns"]
