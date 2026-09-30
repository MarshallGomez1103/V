"""Word -> speaker reconciliation by midpoint (S7.05)."""

from __future__ import annotations

from uuid import UUID, uuid4

from voz.application.word_speakers import SpeakerTimeline, word_speaker_ids
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.word import Word

TRANSCRIPT = uuid4()
ANA = uuid4()
BEA = uuid4()


def _turn(start: int, end: int, speaker: UUID | None) -> SpeakerTurn:
    return SpeakerTurn(TRANSCRIPT, "c", start, end, speaker_id=speaker)


def _segment(
    *spans: tuple[int, int], speaker: UUID | None = None, end: int = 1_000
) -> Segment:
    segment_id = uuid4()
    return Segment(
        TRANSCRIPT,
        0,
        end,
        "x",
        id=segment_id,
        words=tuple(Word(segment_id, s, e, "w") for s, e in spans),
        speaker_id=speaker,
    )


def test_each_word_takes_the_turn_containing_its_midpoint() -> None:
    segment = _segment((0, 100), (100, 300), (300, 500), speaker=ANA)
    timeline = SpeakerTimeline([_turn(0, 200, ANA), _turn(200, 600, BEA)])

    # midpoints 50 -> ANA, 200 -> BEA (end is exclusive), 400 -> BEA
    assert word_speaker_ids(segment, timeline) == (ANA, BEA, BEA)


def test_word_outside_every_turn_inherits_the_segment_speaker() -> None:
    segment = _segment((0, 100), (800, 900), speaker=BEA)
    timeline = SpeakerTimeline([_turn(0, 200, ANA)])

    assert word_speaker_ids(segment, timeline) == (ANA, BEA)
    no_speaker = _segment((800, 900))
    assert word_speaker_ids(no_speaker, timeline) == (None,)


def test_without_timeline_or_speakers_words_follow_the_segment() -> None:
    segment = _segment((0, 100), (100, 200), speaker=ANA)

    assert word_speaker_ids(segment) == (ANA, ANA)
    assert word_speaker_ids(segment, SpeakerTimeline([_turn(0, 500, None)])) == (
        ANA,
        ANA,
    )
    assert word_speaker_ids(_segment()) == ()


def test_overlapping_turns_pick_the_earliest_and_long_turns_are_not_missed() -> None:
    # A long early turn must still be found behind a short later one.
    timeline = SpeakerTimeline(
        [_turn(500, 600, BEA), _turn(0, 900, ANA), _turn(520, 580, BEA)]
    )
    segment = _segment((700, 800), (530, 570), speaker=None)

    assert word_speaker_ids(segment, timeline) == (ANA, ANA)


def test_odd_millisecond_midpoints_are_exact() -> None:
    # (100, 101) has midpoint 100.5: inside [100, 101) but not [50, 100).
    timeline = SpeakerTimeline([_turn(50, 100, ANA), _turn(100, 101, BEA)])

    assert word_speaker_ids(_segment((100, 101)), timeline) == (BEA,)
    assert word_speaker_ids(_segment((99, 100)), timeline) == (ANA,)


def test_input_turn_order_does_not_matter() -> None:
    turns = [_turn(200, 400, BEA), _turn(0, 200, ANA)]
    segment = _segment((50, 150), (250, 350))

    assert word_speaker_ids(segment, SpeakerTimeline(turns)) == (ANA, BEA)
    assert word_speaker_ids(segment, SpeakerTimeline(turns[::-1])) == (ANA, BEA)
