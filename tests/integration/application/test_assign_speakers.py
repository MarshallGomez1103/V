"""AssignSpeakers against the real SQLite adapters (S6.02, S6.08, S6.14)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from voz.application.assign_speakers import AssignSpeakers, TranscriptNotFound
from voz.application.ports.diarization import DiarizationResult, DiarizedTurn
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import SPEAKER_PALETTE
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.word import Word
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptRepository,
)

_NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


@dataclass
class _World:
    engine: Engine
    project: Project
    transcript: Transcript
    segments: tuple[Segment, ...]
    use_case: AssignSpeakers

    @property
    def segment_repo(self) -> SqliteSegmentRepository:
        return SqliteSegmentRepository(self.engine)

    @property
    def speaker_repo(self) -> SqliteSpeakerRepository:
        return SqliteSpeakerRepository(self.engine)

    @property
    def turn_repo(self) -> SqliteSpeakerTurnRepository:
        return SqliteSpeakerTurnRepository(self.engine)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[_World]:
    engine = create_sqlite_engine(tmp_path / "voz.sqlite3")
    upgrade_to_head(engine)
    project = Project("Clase", created_at=_NOW)
    media = MediaAsset(project.id, "a" * 64, "clase.wav", 10, created_at=_NOW)
    transcript = Transcript(project.id, media.id, created_at=_NOW)
    SqliteProjectRepository(engine).add(project)
    SqliteMediaAssetRepository(engine).add(media)
    SqliteTranscriptRepository(engine).add(transcript)
    first = Segment(transcript.id, 0, 1_000, "Hola")
    first = first.add_word(Word(first.id, 0, 500, "Hola"))
    segments = (
        first,
        Segment(transcript.id, 1_000, 2_000, "Buenas"),
        Segment(transcript.id, 5_000, 6_000, "silencio"),
    )
    segment_repo = SqliteSegmentRepository(engine)
    for segment in segments:
        segment_repo.add(segment)
    use_case = AssignSpeakers(
        SqliteTranscriptRepository(engine),
        segment_repo,
        SqliteSpeakerRepository(engine),
        SqliteSpeakerTurnRepository(engine),
    )
    yield _World(engine, project, transcript, segments, use_case)
    engine.dispose()


def _result() -> DiarizationResult:
    return DiarizationResult(
        (DiarizedTurn(1_000, 2_000, "spk_b"), DiarizedTurn(0, 1_000, "spk_a"))
    )


def test_creates_named_colored_speakers_and_labels_segments(world: _World) -> None:
    outcome = world.use_case.execute(world.transcript.id, _result())

    assert [s.name for s in outcome.speakers] == ["Speaker 1", "Speaker 2"]
    assert [s.color for s in outcome.speakers] == list(SPEAKER_PALETTE[:2])
    assert (outcome.assigned_segments, outcome.unassigned_segments) == (2, 1)
    stored = world.segment_repo.list_by_transcript(world.transcript.id)
    assert [s.speaker_id for s in stored] == [
        outcome.speakers[0].id,
        outcome.speakers[1].id,
        None,
    ]
    # Words, text and revisions are untouched.
    assert stored[0].words == world.segments[0].words
    assert [s.text for s in stored] == ["Hola", "Buenas", "silencio"]
    # Turns keep the provider's original cluster and point to the speaker.
    turns = world.turn_repo.list_by_transcript(world.transcript.id)
    assert [(t.cluster_label, t.speaker_id) for t in turns] == [
        ("spk_a", outcome.speakers[0].id),
        ("spk_b", outcome.speakers[1].id),
    ]
    assert world.speaker_repo.list_by_project(world.project.id) == outcome.speakers


def test_rerun_is_idempotent_and_keeps_renames(world: _World) -> None:
    first = world.use_case.execute(world.transcript.id, _result())
    renamed = first.speakers[0].rename("Profesor")
    world.speaker_repo.save(renamed)

    second = world.use_case.execute(world.transcript.id, _result())

    assert [s.id for s in second.speakers] == [s.id for s in first.speakers]
    speakers = world.speaker_repo.list_by_project(world.project.id)
    assert len(speakers) == 2
    assert "Profesor" in {s.name for s in speakers}
    assert len(world.turn_repo.list_by_transcript(world.transcript.id)) == 2
    stored = world.segment_repo.list_by_transcript(world.transcript.id)
    assert stored[0].speaker_id == first.speakers[0].id


def test_rerun_with_new_cluster_only_adds_that_speaker(world: _World) -> None:
    first = world.use_case.execute(world.transcript.id, _result())
    extended = DiarizationResult(
        (*_result().turns, DiarizedTurn(5_000, 6_000, "spk_c"))
    )

    outcome = world.use_case.execute(world.transcript.id, extended)

    assert [s.id for s in outcome.speakers[:2]] == [s.id for s in first.speakers]
    assert len(world.speaker_repo.list_by_project(world.project.id)) == 3
    assert outcome.assigned_segments == 3


def test_rerun_with_zero_turns_clears_assignments(world: _World) -> None:
    world.use_case.execute(world.transcript.id, _result())

    outcome = world.use_case.execute(world.transcript.id, DiarizationResult(()))

    assert outcome.speakers == () and outcome.turns == ()
    assert (outcome.assigned_segments, outcome.unassigned_segments) == (0, 3)
    assert world.turn_repo.list_by_transcript(world.transcript.id) == ()
    stored = world.segment_repo.list_by_transcript(world.transcript.id)
    assert all(s.speaker_id is None for s in stored)


def test_palette_cycles_after_last_color(world: _World) -> None:
    many = DiarizationResult(
        tuple(
            DiarizedTurn(index * 10, index * 10 + 5, f"c{index}")
            for index in range(len(SPEAKER_PALETTE) + 1)
        )
    )
    outcome = world.use_case.execute(world.transcript.id, many)
    assert outcome.speakers[-1].color == SPEAKER_PALETTE[0]
    assert outcome.speakers[-1].name == f"Speaker {len(SPEAKER_PALETTE) + 1}"


def test_unknown_transcript_is_rejected(world: _World) -> None:
    with pytest.raises(TranscriptNotFound):
        world.use_case.execute(uuid4(), _result())


def test_repository_additions_are_atomic_and_scoped(world: _World) -> None:
    foreign = SpeakerTurn(uuid4(), "x", 0, 10)
    with pytest.raises(ValueError):
        world.turn_repo.replace_for_transcript(world.transcript.id, [foreign])
    # Unknown segment ids are ignored by update_speakers.
    world.segment_repo.update_speakers({uuid4(): None})
