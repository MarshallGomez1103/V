"""S14.02: multi-statement SQLite writes are all-or-nothing, even across a kill."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import IntegrityError

from voz.application.ports.transcription import TranscriptionSegment
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.word import Word
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
    SqliteWordRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)

BASE_TIME = datetime(2026, 9, 30, 8, tzinfo=UTC)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine(tmp_path / "voz.sqlite3")
    upgrade_to_head(created, tmp_path / "backups")
    yield created
    created.dispose()


def _transcript(engine: Engine) -> Transcript:
    project = Project("Clase")
    asset = MediaAsset(project.id, "a" * 64, "clase.wav", 1_024, duration_ms=5_000)
    root = Transcript(project.id, asset.id)
    SqliteProjectRepository(engine).add(project)
    SqliteMediaAssetRepository(engine).add(asset)
    SqliteTranscriptRepository(engine).add(root)
    return root


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(text(f"select count(*) from {table}")).scalar_one()
        )


def test_every_connection_syncs_the_wal_on_commit(engine: Engine) -> None:
    # synchronous=FULL (2) is what makes a confirmed chunk survive power loss.
    with engine.connect() as connection:
        assert connection.execute(text("pragma synchronous")).scalar_one() == 2
        assert connection.execute(text("pragma journal_mode")).scalar_one() == "wal"


def test_failed_segment_save_rolls_back_text_and_words(engine: Engine) -> None:
    root = _transcript(engine)
    segments = SqliteSegmentRepository(engine)
    words = SqliteWordRepository(engine)
    first_id, second_id = uuid4(), uuid4()
    kept = Word(second_id, 1_000, 1_100, "ajena")
    original = Segment(root.id, 0, 1_000, "original", id=first_id)
    other = Segment(root.id, 1_000, 2_000, "otro", id=second_id, words=(kept,))
    segments.add(original)
    segments.add(other)
    # The new word collides with another segment's word: the insert fails
    # after the UPDATE and the DELETE of the old words already ran.
    clash = Segment(
        root.id,
        0,
        1_000,
        "editado",
        id=first_id,
        words=(Word(first_id, 0, 50, "x", id=kept.id),),
    )

    with pytest.raises(IntegrityError):
        segments.save(clash)

    assert segments.get(first_id) == original
    assert words.get(kept.id) == kept
    assert segments.get(second_id) == other


def test_failed_turn_replacement_keeps_the_previous_turns(engine: Engine) -> None:
    root = _transcript(engine)
    turns = SqliteSpeakerTurnRepository(engine)
    previous = (SpeakerTurn(root.id, "a", 0, 100), SpeakerTurn(root.id, "b", 100, 200))
    turns.replace_for_transcript(root.id, previous)
    duplicate = uuid4()
    incoming = [
        SpeakerTurn(root.id, "c", 0, 50, id=duplicate),
        SpeakerTurn(root.id, "d", 50, 100, id=duplicate),
    ]

    with pytest.raises(IntegrityError):
        turns.replace_for_transcript(root.id, incoming)

    assert turns.list_by_transcript(root.id) == previous


def test_failed_speaker_batch_changes_no_segment(engine: Engine) -> None:
    root = _transcript(engine)
    project_id = root.project_id
    speaker = Speaker(project_id, "Ana", "#4e79a7")
    SqliteSpeakerRepository(engine).add(speaker)
    segments = SqliteSegmentRepository(engine)
    first = Segment(root.id, 0, 100, "uno")
    second = Segment(root.id, 100, 200, "dos")
    segments.add(first)
    segments.add(second)

    with pytest.raises(IntegrityError):  # the second speaker does not exist
        segments.update_speakers({first.id: speaker.id, second.id: uuid4()})

    assert [s.speaker_id for s in segments.list_by_transcript(root.id)] == [None, None]


def _checkpoint(job: TranscriptionJob) -> TranscriptionCheckpoint:
    return TranscriptionCheckpoint(
        job_id=job.id,
        chunk_index=0,
        process_start_ms=0,
        process_end_ms=100,
        owned_start_ms=0,
        owned_end_ms=100,
        provider_id="fake-asr",
        model_id="fixture",
        model_source=None,
        model_revision=None,
        requested_language=None,
        segments=(TranscriptionSegment(0, 100, "x"),),
        language="es",
        progress=1.0,
        job_progress=job.progress,
        completed_at=job.updated_at,
    )


def test_failure_after_the_checkpoint_insert_rolls_the_insert_back(
    engine: Engine,
) -> None:
    root = _transcript(engine)
    job = TranscriptionJob(
        id=uuid4(),
        project_id=root.project_id,
        media_asset_id=root.media_asset_id,
        state=TranscriptionJobState.TRANSCRIBING,
        progress=0.5,
        created_at=BASE_TIME,
        updated_at=BASE_TIME + timedelta(seconds=1),
    )
    SqliteTranscriptionJobRepository(engine).add(job)

    def die_on_job_update(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE transcription_jobs"):
            raise OSError("disk vanished between the two statements")

    event.listen(engine, "before_cursor_execute", die_on_job_update)
    with pytest.raises(OSError, match="vanished"):
        SqliteTranscriptionCheckpointStore(engine).commit(_checkpoint(job), job)
    event.remove(engine, "before_cursor_execute", die_on_job_update)

    assert _count(engine, "transcription_checkpoints") == 0
    persisted = SqliteTranscriptionJobRepository(engine).get(job.id)
    assert persisted == job


def test_a_killed_process_mid_transaction_leaves_the_previous_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "voz.sqlite3"
    child = textwrap.dedent(
        f"""
        import os
        from pathlib import Path
        from sqlalchemy import text
        from voz.domain.entities.project import Project
        from voz.infrastructure.persistence.database import create_sqlite_engine
        from voz.infrastructure.persistence.migrate import upgrade_to_head
        from voz.infrastructure.persistence.repositories import SqliteProjectRepository

        engine = create_sqlite_engine(Path({str(database)!r}))
        upgrade_to_head(engine, Path({str(tmp_path / "backups")!r}))
        SqliteProjectRepository(engine).add(Project("confirmado"))
        with engine.begin() as connection:
            connection.execute(text(
                "insert into projects (id, name, created_at) "
                "values ('lost', 'perdido', '2026-09-30T00:00:00+00:00')"
            ))
            os._exit(9)  # no commit, no rollback, no cleanup: a hard kill
        """
    )
    src = Path(__file__).parents[3] / "src"
    done = subprocess.run(
        [sys.executable, "-c", child],
        env={"PYTHONPATH": str(src), "PATH": ""},
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 9, done.stderr.decode()

    reopened = create_sqlite_engine(database)
    try:
        assert [p.name for p in SqliteProjectRepository(reopened).list_all()] == [
            "confirmado"
        ]
    finally:
        reopened.dispose()
