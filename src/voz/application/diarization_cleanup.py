"""Fold residual speakers (a few seconds of speech) into their nearest neighbour.

Clustering over-segments: a stray cough or a distant voice becomes its own
"speaker". Keeping them clutters the UI, and merging two real speakers later is
easy, so only clusters with almost no speech are folded here.

ponytail: heuristic. "Nearest" means closest in time, not closest by voice
embedding (the engine does not expose embeddings): the residual's turns are
compared with the turns of each larger cluster and the smallest total gap wins.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from voz.application.ports.diarization import DiarizedTurn

MIN_SHARE = 0.02
"""A cluster below this share of all speech is residual."""
MIN_TALK_MS = 10_000
"""...and so is one below this much speech, capped at ``MAX_SHORT_SHARE``."""
MAX_SHORT_SHARE = 0.05
"""The absolute floor never exceeds this share, so short audio keeps its speakers."""


def _gap(first: DiarizedTurn, second: DiarizedTurn) -> int:
    return max(0, first.start_ms - second.end_ms, second.start_ms - first.end_ms)


def _distance(source: Sequence[DiarizedTurn], target: Sequence[DiarizedTurn]) -> int:
    return sum(min(_gap(turn, other) for other in target) for turn in source)


def merge_residual_clusters(
    turns: Sequence[DiarizedTurn],
    *,
    keep_at_least: int = 1,
    min_share: float = MIN_SHARE,
    min_talk_ms: int = MIN_TALK_MS,
) -> list[DiarizedTurn]:
    """Relabel the turns of residual clusters with their nearest larger cluster.

    Never goes below ``keep_at_least`` clusters (an exact or minimum speaker count
    asked by the user wins). Input order is preserved; inputs are not mutated.
    """
    by_cluster: dict[str, list[DiarizedTurn]] = defaultdict(list)
    for turn in turns:
        by_cluster[turn.cluster].append(turn)
    talk = {
        cluster: sum(t.end_ms - t.start_ms for t in group)
        for cluster, group in by_cluster.items()
    }
    total = sum(talk.values())
    floor = max(min_share * total, min(float(min_talk_ms), MAX_SHORT_SHARE * total))
    relabel: dict[str, str] = {}
    while len(talk) > max(keep_at_least, 1):
        smallest = min(talk, key=lambda cluster: (talk[cluster], cluster))
        if talk[smallest] >= floor:
            break
        larger = [c for c in talk if c != smallest and talk[c] > talk[smallest]]
        if not larger:
            break
        source = by_cluster[smallest]
        target = min(
            larger,
            key=lambda c: (_distance(source, by_cluster[c]), -talk[c], c),
        )
        by_cluster[target].extend(by_cluster.pop(smallest))
        talk[target] += talk.pop(smallest)
        relabel[smallest] = target
        for origin, destination in relabel.items():
            if destination == smallest:
                relabel[origin] = target

    return [
        DiarizedTurn(t.start_ms, t.end_ms, relabel.get(t.cluster, t.cluster))
        for t in turns
    ]


__all__ = ["MAX_SHORT_SHARE", "MIN_SHARE", "MIN_TALK_MS", "merge_residual_clusters"]
