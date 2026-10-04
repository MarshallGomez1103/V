"""Carry speaker identities (names, colors) over to a fresh clustering.

A new diarization run numbers its clusters from scratch, so labels cannot be
compared. Time can: a new cluster that speaks over the same stretches as an old
speaker is that person.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from voz.application.ports.diarization import DiarizedTurn

MIN_COVERAGE = 0.5
"""Share of the new cluster's speech, or of the old speaker's, that they must share."""


def _overlap_ms(
    new_turns: Sequence[DiarizedTurn],
    old: Sequence[tuple[int, int]],
) -> int:
    """Total overlap of two interval lists, both sorted by start."""
    total = 0
    start_index = 0
    for turn in new_turns:
        while start_index < len(old) and old[start_index][1] <= turn.start_ms:
            start_index += 1
        index = start_index
        while index < len(old) and old[index][0] < turn.end_ms:
            total += max(
                0, min(turn.end_ms, old[index][1]) - max(turn.start_ms, old[index][0])
            )
            index += 1
    return total


def match_clusters_to_speakers(
    new_turns: Sequence[DiarizedTurn],
    old_turns: Sequence[tuple[int, int, UUID]],
    *,
    min_coverage: float = MIN_COVERAGE,
) -> dict[str, UUID]:
    """Map new cluster labels to old speaker ids, one old speaker per cluster.

    Greedy by overlap: the largest (cluster, speaker) overlap is taken first, and
    only when it covers at least ``min_coverage`` of the cluster's speech (the
    old speaker is the cluster) or of the old speaker's speech (the cluster
    contains them: an over-split person merged back keeps the name they were
    given). A cluster that merges several old people takes the name of the one
    with the most overlap, like merging speakers by hand keeps the target's.

    # ponytail: greedy, not an optimal assignment; clusters are few.
    """
    clusters: dict[str, list[DiarizedTurn]] = defaultdict(list)
    for turn in new_turns:
        clusters[turn.cluster].append(turn)
    speakers: dict[UUID, list[tuple[int, int]]] = defaultdict(list)
    for start, end, speaker_id in old_turns:
        speakers[speaker_id].append((start, end))
    for group in clusters.values():
        group.sort(key=lambda turn: (turn.start_ms, turn.end_ms))
    for intervals in speakers.values():
        intervals.sort()

    pairs: list[tuple[int, str, UUID]] = []
    for label, group in clusters.items():
        talk = sum(turn.end_ms - turn.start_ms for turn in group)
        for speaker_id, intervals in speakers.items():
            overlap = _overlap_ms(group, intervals)
            old_talk = sum(end - start for start, end in intervals)
            if overlap > 0 and (
                overlap >= min_coverage * talk or overlap >= min_coverage * old_talk
            ):
                pairs.append((overlap, label, speaker_id))
    pairs.sort(key=lambda pair: (-pair[0], pair[1], str(pair[2])))

    matched: dict[str, UUID] = {}
    taken: set[UUID] = set()
    for _, label, speaker_id in pairs:
        if label not in matched and speaker_id not in taken:
            matched[label] = speaker_id
            taken.add(speaker_id)
    return matched


__all__ = ["MIN_COVERAGE", "match_clusters_to_speakers"]
