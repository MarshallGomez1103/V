"""Migration 0006, quality hint persistence and checkpoint compatibility."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from voz.application.ports.transcription import TranscriptionSegment
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    _segment_json,  # pyright: ignore[reportPrivateUsage]
    _segments_from_json,  # pyright: ignore[reportPrivateUsage]
)

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 9, 30, 8, tzinfo=UTC)


def _config(engine: Engine) -> Config:
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    return config


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine((tmp_path / "voz.sqlite3").absolute())
    yield created
    created.dispose()


def test_migration_0006_keeps_segments_and_words_and_downgrades(
    engine: Engine,
) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0005_job_diarization")
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p', 'P', '2026-09-30T08:00:00+00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m', 'p', 'h', 'a.wav', 1, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcripts VALUES ('t', 'p', 'm', NULL, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO segments (id, transcript_id, start_ms, end_ms, text)"
            " VALUES ('s', 't', 0, 10, 'hola')"
        )
        connection.exec_driver_sql(
            "INSERT INTO words (id, segment_id, start_ms, end_ms, text)"
            " VALUES ('w', 's', 0, 5, 'hola')"
        )
        connection.commit()

        command.upgrade(config, "0006_segment_quality")
        assert connection.execute(text("SELECT count(*) FROM words")).scalar_one() == 1
        row = connection.execute(text("SELECT text, quality_json FROM segments")).one()
        assert tuple(row) == ("hola", None)

        connection.exec_driver_sql(
            'UPDATE segments SET quality_json = \'{"flags":["repetition"]}\''
        )
        connection.commit()
        command.downgrade(config, "0005_job_diarization")
        assert "quality_json" not in {
            c["name"] for c in inspect(connection).get_columns("segments")
        }
        assert connection.execute(text("SELECT text FROM segments")).scalar_one() == (
            "hola"
        )
        assert connection.execute(text("SELECT count(*) FROM words")).scalar_one() == 1

        command.upgrade(config, "head")
        assert "quality_json" in {
            c["name"] for c in inspect(connection).get_columns("segments")
        }


def _repository(engine: Engine) -> tuple[SqliteSegmentRepository, Transcript]:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    project = Project("Clase", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "clase.wav", 10, duration_ms=1_000)
    SqliteMediaAssetRepository(engine).add(asset)
    transcript = Transcript(project.id, asset.id, created_at=NOW)
    SqliteTranscriptRepository(engine).add(transcript)
    return SqliteSegmentRepository(engine), transcript


def test_quality_hints_round_trip_and_unflagged_segments_store_null(
    engine: Engine,
) -> None:
    repository, transcript = _repository(engine)
    flagged = Segment(
        transcript.id,
        0,
        500,
        "Thank you.",
        quality_flags=("silence_hallucination", "low_confidence"),
        avg_logprob=-1.5,
    )
    clean = Segment(transcript.id, 500, 900, "Hola.")
    repository.add(flagged)
    repository.add(clean)

    assert repository.get(flagged.id) == flagged
    assert repository.get(clean.id) == clean
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT text, quality_json FROM segments")).all()
    stored = {str(row[0]): row[1] for row in rows}
    assert stored["Hola."] is None
    assert "silence_hallucination" in str(stored["Thank you."])


@pytest.mark.parametrize("damaged", ["not json", "[1]", '{"flags": 3}', "123"])
def test_damaged_quality_json_reads_as_no_hints(engine: Engine, damaged: str) -> None:
    repository, transcript = _repository(engine)
    segment = Segment(transcript.id, 0, 500, "Hola.")
    repository.add(segment)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE segments SET quality_json = :v"), {"v": damaged}
        )

    stored = repository.get(segment.id)

    assert stored is not None
    assert stored.text == "Hola." and stored.quality_flags == ()
    assert stored.avg_logprob is None


def test_checkpoint_json_keeps_metrics_and_reads_old_checkpoints() -> None:
    segment = TranscriptionSegment(
        0,
        100,
        " x",
        avg_logprob=-1.2,
        no_speech_prob=0.8,
        compression_ratio=3.1,
        exceeds_audio=True,
    )
    assert _segments_from_json(json.dumps([_segment_json(segment)])) == (segment,)

    # Written before S13.04: no metric keys at all.
    old = {"start_ms": 0, "end_ms": 100, "text": " x"}
    (loaded,) = _segments_from_json(json.dumps([old]))
    assert loaded == TranscriptionSegment(0, 100, " x")
    assert "avg_logprob" not in _segment_json(loaded)
