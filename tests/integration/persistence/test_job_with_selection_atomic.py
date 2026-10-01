"""Job + selection are written in one transaction (INTEGRITY-001)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, Table, func, select
from sqlalchemy.exc import IntegrityError

from voz.application.ports.transcription_job_selection import (
    JobSelection,
    JobWithSelectionWriter,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.schema import (
    transcription_job_selections,
    transcription_jobs,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

NOW = datetime(2026, 9, 30, 10, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


def _job(tmp_path: Path) -> tuple[Engine, TranscriptionJob]:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    upgrade_to_head(engine)
    project = Project("Demo", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=250)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
    )
    return engine, job


def _selection(job_id: UUID) -> JobSelection:
    return JobSelection(
        job_id=job_id,
        option_id="option-v1-fixture",
        model=MODEL,
        execution=None,
        language="es",
        created_at=NOW,
    )


def _count(engine: Engine, table: Table) -> int:
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table)).scalar_one()


def test_adapter_satisfies_the_port(tmp_path: Path) -> None:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    assert isinstance(SqliteTranscriptionJobRepository(engine), JobWithSelectionWriter)
    engine.dispose()


def test_job_and_selection_are_persisted_together(tmp_path: Path) -> None:
    engine, job = _job(tmp_path)
    selection = _selection(job.id)

    SqliteTranscriptionJobRepository(engine).add_with_selection(job, selection)

    assert SqliteTranscriptionJobRepository(engine).get(job.id) == job
    assert SqliteTranscriptionJobSelectionRepository(engine).get(job.id) == selection
    engine.dispose()


def test_invalid_selection_rolls_back_the_job(tmp_path: Path) -> None:
    engine, job = _job(tmp_path)
    # The selection points at a job that does not exist: the FK rejects it.
    orphan = _selection(uuid4())

    with pytest.raises(IntegrityError):
        SqliteTranscriptionJobRepository(engine).add_with_selection(job, orphan)

    assert SqliteTranscriptionJobRepository(engine).get(job.id) is None
    assert _count(engine, transcription_jobs) == 0
    assert _count(engine, transcription_job_selections) == 0
    engine.dispose()
