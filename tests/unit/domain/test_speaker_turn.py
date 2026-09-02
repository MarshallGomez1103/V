"""Unit tests for acoustic speaker turns and UI assignments."""

from uuid import UUID, uuid4

import pytest

from voz.domain.entities.speaker_turn import SpeakerTurn


def make_turn(
    *,
    start_ms: int = 100,
    end_ms: int = 500,
    speaker_id: UUID | None = None,
) -> SpeakerTurn:
    return SpeakerTurn(
        transcript_id=uuid4(),
        cluster_label="SPEAKER_00",
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_id=speaker_id,
    )


def test_speaker_turn_keeps_acoustic_cluster_separate_from_ui_identity() -> None:
    turn = make_turn()

    assert isinstance(turn.id, UUID)
    assert turn.cluster_label == "SPEAKER_00"
    assert turn.speaker_id is None


def test_speaker_turn_assignment_and_reassignment_preserve_cluster() -> None:
    turn = make_turn()
    first_speaker_id = uuid4()
    second_speaker_id = uuid4()

    assigned = turn.assign_speaker(first_speaker_id)
    reassigned = assigned.assign_speaker(second_speaker_id)

    assert turn.speaker_id is None
    assert assigned.speaker_id == first_speaker_id
    assert reassigned.speaker_id == second_speaker_id
    assert reassigned.id == turn.id
    assert reassigned.transcript_id == turn.transcript_id
    assert reassigned.cluster_label == turn.cluster_label
    assert (reassigned.start_ms, reassigned.end_ms) == (turn.start_ms, turn.end_ms)


def test_speaker_turn_can_remove_a_ui_assignment_without_changing_cluster() -> None:
    turn = make_turn(speaker_id=uuid4())

    unassigned = turn.assign_speaker(None)

    assert unassigned.speaker_id is None
    assert unassigned.cluster_label == turn.cluster_label
    assert unassigned.id == turn.id


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(-1, 10), (0, -1), (100, 100), (101, 100)],
)
def test_speaker_turn_rejects_invalid_offset_ranges(
    start_ms: int,
    end_ms: int,
) -> None:
    with pytest.raises(ValueError):
        make_turn(start_ms=start_ms, end_ms=end_ms)


@pytest.mark.parametrize(
    ("start_ms", "end_ms"),
    [(True, 10), (0, False)],
)
def test_speaker_turn_rejects_non_integer_offsets(
    start_ms: int,
    end_ms: int,
) -> None:
    with pytest.raises(TypeError):
        make_turn(start_ms=start_ms, end_ms=end_ms)


@pytest.mark.parametrize("cluster_label", ["", "   ", "SPEAKER\n00"])
def test_speaker_turn_rejects_invalid_cluster_labels(cluster_label: str) -> None:
    with pytest.raises(ValueError):
        SpeakerTurn(
            transcript_id=uuid4(),
            cluster_label=cluster_label,
            start_ms=0,
            end_ms=1,
        )


def test_speaker_turn_rejects_non_uuid_assignment() -> None:
    turn = make_turn()

    with pytest.raises(TypeError):
        turn.assign_speaker("speaker-id")  # type: ignore[arg-type]
