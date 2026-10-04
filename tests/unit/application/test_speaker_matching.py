"""New clusters inherit the identity of the old speaker they overlap (CP-A3)."""

from __future__ import annotations

from uuid import uuid4

from voz.application.ports.diarization import DiarizedTurn
from voz.application.speaker_matching import match_clusters_to_speakers

TEACHER, STUDENT = uuid4(), uuid4()
OLD = [(0, 600, TEACHER), (600, 1_000, STUDENT)]


def test_labels_do_not_matter_only_time() -> None:
    new = [DiarizedTurn(0, 580, "9"), DiarizedTurn(620, 1_000, "4")]

    assert match_clusters_to_speakers(new, OLD) == {"9": TEACHER, "4": STUDENT}


def test_one_old_speaker_is_given_to_one_cluster_only() -> None:
    new = [DiarizedTurn(0, 400, "a"), DiarizedTurn(400, 600, "b")]

    matched = match_clusters_to_speakers(new, OLD)

    assert matched == {"a": TEACHER}  # the larger fragment keeps the name


def test_a_cluster_that_blends_people_takes_the_name_of_the_largest() -> None:
    new = [DiarizedTurn(0, 1_000, "all")]
    old = [(0, 300, TEACHER), (300, 900, STUDENT), (900, 1_000, uuid4())]

    assert match_clusters_to_speakers(new, old) == {"all": STUDENT}


def test_an_over_split_person_merged_back_keeps_their_name() -> None:
    # The old run cut the teacher in two; the new cluster holds both halves.
    half, other = uuid4(), uuid4()
    new = [DiarizedTurn(0, 1_000, "0")]
    old = [(0, 400, half), (400, 1_000, other)]

    assert match_clusters_to_speakers(new, old) == {"0": other}


def test_a_stray_overlap_is_not_a_match() -> None:
    new = [DiarizedTurn(0, 1_000, "0")]
    old = [(0, 100, TEACHER), (2_000, 3_000, TEACHER)]  # 100 of 1100 ms

    assert match_clusters_to_speakers(new, old) == {}


def test_without_history_nothing_matches() -> None:
    assert match_clusters_to_speakers([DiarizedTurn(0, 10, "0")], []) == {}
