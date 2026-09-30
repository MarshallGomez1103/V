"""Pure reconciliation of diarization turns with ASR segments (S6.08, S6.14)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from voz.application.diarization_reconcile import reconcile_turns
from voz.application.ports.diarization import DiarizedTurn
from voz.domain.entities.segment import Segment

_TRANSCRIPT = uuid4()


def _segment(start: int, end: int) -> Segment:
    return Segment(_TRANSCRIPT, start, end, "texto")


def _turn(start: int, end: int, cluster: str) -> DiarizedTurn:
    return DiarizedTurn(start, end, cluster)


def test_assigns_cluster_with_largest_overlap() -> None:
    segment = _segment(0, 1_000)
    result = reconcile_turns([segment], [_turn(0, 300, "A"), _turn(300, 1_000, "B")])
    assert result.assignments == {segment.id: "B"}
    assert result.cluster_order == ("A", "B")


def test_turn_crossing_several_segments_labels_all_of_them() -> None:
    segments = [_segment(0, 1_000), _segment(1_000, 2_000), _segment(2_000, 3_000)]
    result = reconcile_turns(segments, [_turn(0, 3_000, "A")])
    assert list(result.assignments.values()) == ["A", "A", "A"]


def test_silence_segment_has_no_speaker() -> None:
    covered, silent = _segment(0, 1_000), _segment(5_000, 6_000)
    result = reconcile_turns([covered, silent], [_turn(0, 1_000, "A")])
    assert result.assignments == {covered.id: "A", silent.id: None}


def test_overlapping_speech_tie_goes_to_earlier_cluster() -> None:
    segment = _segment(1_000, 2_000)
    # Both clusters cover the whole segment; B started first.
    result = reconcile_turns(
        [segment], [_turn(1_000, 2_000, "A"), _turn(500, 2_500, "B")]
    )
    assert result.assignments == {segment.id: "B"}
    assert result.cluster_order == ("B", "A")


def test_overlapping_speech_tie_same_start_is_stable() -> None:
    segment = _segment(0, 1_000)
    turns = [_turn(0, 1_000, "X"), _turn(0, 1_000, "Y")]
    first = reconcile_turns([segment], turns)
    second = reconcile_turns([segment], list(reversed(turns)))
    assert first.assignments == {segment.id: "X"}
    assert second.assignments == {segment.id: "Y"}  # input order breaks full ties


def test_overlap_majority_wins_even_with_interruption() -> None:
    segment = _segment(0, 1_000)
    result = reconcile_turns([segment], [_turn(0, 1_000, "A"), _turn(400, 600, "B")])
    assert result.assignments == {segment.id: "A"}


def test_same_cluster_overlapping_turns_are_not_double_counted() -> None:
    segment = _segment(0, 1_000)
    # A's turns overlap each other for 800 ms but cover only 600 ms in total.
    turns = [
        _turn(0, 400, "A"),
        _turn(0, 400, "A"),
        _turn(200, 600, "A"),
        _turn(600, 1_000, "B"),
    ]
    result = reconcile_turns([segment], turns)
    # A covers 600 ms, B 400 ms.
    assert result.assignments == {segment.id: "A"}


def test_overlap_below_threshold_is_none() -> None:
    segment = _segment(0, 1_000)
    below = reconcile_turns([segment], [_turn(0, 299, "A")])
    at_threshold = reconcile_turns([segment], [_turn(0, 300, "A")])
    assert below.assignments == {segment.id: None}
    assert at_threshold.assignments == {segment.id: "A"}


def test_threshold_zero_still_requires_real_overlap() -> None:
    touching, inside = _segment(0, 1_000), _segment(1_000, 1_010)
    result = reconcile_turns(
        [touching, inside],
        [_turn(0, 1_000, "A"), _turn(1_005, 1_010, "B")],
        min_overlap_ratio=0,
    )
    assert result.assignments == {touching.id: "A", inside.id: "B"}
    # Touching edges give zero overlap: A does not leak into the next segment.
    only_a = reconcile_turns([inside], [_turn(0, 1_000, "A")], min_overlap_ratio=0)
    assert only_a.assignments == {inside.id: None}


def test_boundary_segments_before_and_after_the_turns() -> None:
    before, after = _segment(0, 500), _segment(9_000, 9_500)
    result = reconcile_turns([before, after], [_turn(1_000, 8_000, "A")])
    assert result.assignments == {before.id: None, after.id: None}


def test_unordered_inputs_are_handled() -> None:
    segments = [_segment(2_000, 3_000), _segment(0, 1_000), _segment(1_000, 2_000)]
    turns = [_turn(2_000, 3_000, "B"), _turn(1_000, 2_000, "A"), _turn(0, 1_000, "B")]
    result = reconcile_turns(segments, turns)
    assert [result.assignments[s.id] for s in segments] == ["B", "B", "A"]
    assert result.cluster_order == ("B", "A")  # B appears first in time


def test_long_early_turn_still_reaches_late_segments() -> None:
    # A short later turn must not hide an earlier long turn from the search.
    segments = [_segment(5_000, 6_000)]
    turns = [_turn(0, 10_000, "A"), _turn(100, 200, "B")]
    assert reconcile_turns(segments, turns).assignments == {segments[0].id: "A"}


def test_zero_turns_leaves_everything_unassigned() -> None:
    segments = [_segment(0, 1_000), _segment(1_000, 2_000)]
    result = reconcile_turns(segments, [])
    assert result.assignments == {s.id: None for s in segments}
    assert result.cluster_order == ()


def test_zero_segments() -> None:
    result = reconcile_turns([], [_turn(0, 1_000, "A")])
    assert result.assignments == {}
    assert result.cluster_order == ("A",)


def test_inputs_are_not_mutated() -> None:
    segments = [_segment(1_000, 2_000), _segment(0, 1_000)]
    turns = [_turn(1_000, 2_000, "B"), _turn(0, 1_000, "A")]
    reconcile_turns(segments, turns)
    assert [s.start_ms for s in segments] == [1_000, 0]
    assert [t.cluster for t in turns] == ["B", "A"]


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_invalid_ratio_is_rejected(ratio: float) -> None:
    with pytest.raises(ValueError):
        reconcile_turns([], [], min_overlap_ratio=ratio)


def test_assignment_keys_are_segment_ids() -> None:
    segment = _segment(0, 10)
    assert isinstance(next(iter(reconcile_turns([segment], []).assignments)), UUID)
