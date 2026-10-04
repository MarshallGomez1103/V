"""Residual speakers are folded into the nearest larger one (CP-A3)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from voz.application.diarization_cleanup import merge_residual_clusters
from voz.application.ports.diarization import DiarizedTurn

S = 1_000


def _talk(turns: Sequence[DiarizedTurn]) -> Counter[str]:
    talk: Counter[str] = Counter()
    for turn in turns:
        talk[turn.cluster] += turn.end_ms - turn.start_ms
    return talk


def _class() -> list[DiarizedTurn]:
    """A teacher (1000 s), a student (400 s) and a 5 s cough near the student."""
    return [
        DiarizedTurn(0, 1_000 * S, "teacher"),
        DiarizedTurn(1_000 * S, 1_400 * S, "student"),
        DiarizedTurn(1_402 * S, 1_407 * S, "cough"),
    ]


def test_tiny_cluster_goes_to_the_nearest_in_time() -> None:
    merged = merge_residual_clusters(_class())

    assert _talk(merged) == {"teacher": 1_000 * S, "student": 405 * S}
    assert [t.start_ms for t in merged] == [t.start_ms for t in _class()]


def test_clusters_above_the_floor_stay() -> None:
    turns = [
        DiarizedTurn(0, 600 * S, "a"),
        DiarizedTurn(600 * S, 900 * S, "b"),
        DiarizedTurn(900 * S, 1_000 * S, "c"),  # 10 % of the speech
    ]

    assert merge_residual_clusters(turns) == turns


def test_exact_speaker_count_is_never_undercut() -> None:
    merged = merge_residual_clusters(_class(), keep_at_least=3)

    assert set(_talk(merged)) == {"teacher", "student", "cough"}


def test_short_audio_keeps_both_speakers() -> None:
    # 14 s of speech: the 10 s floor would swallow the 6 s speaker; it must not.
    turns = [DiarizedTurn(0, 8 * S, "a"), DiarizedTurn(8 * S, 14 * S, "b")]

    assert merge_residual_clusters(turns) == turns


def test_chain_of_residuals_ends_in_a_single_surviving_label() -> None:
    turns = [
        DiarizedTurn(0, 1_000 * S, "main"),
        DiarizedTurn(1_000 * S, 1_003 * S, "x"),
        DiarizedTurn(1_003 * S, 1_004 * S, "y"),
    ]

    merged = merge_residual_clusters(turns)

    assert {t.cluster for t in merged} == {"main"}


def test_single_cluster_and_empty_input() -> None:
    assert merge_residual_clusters([]) == []
    one = [DiarizedTurn(0, 5 * S, "only")]
    assert merge_residual_clusters(one) == one
