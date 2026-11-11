"""The queue repository writes a queue, its jobs and their order as one unit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, Table, func, select
from sqlalchemy.exc import IntegrityError

from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.domain.entities.transcription_queue import (
    SkippedRecording,
    SkipReason,
    TranscriptionQueue,
)
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.schema import (
    metadata,
    transcription_job_selections,
    transcription_jobs,
    transcription_queue_items,
    transcription_queues,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.infrastructure.persistence.transcription_queues import (
    SqliteTranscriptionQueueRepository,
)

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
)


def _engine(tmp_path: Path) -> Engine:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    metadata.create_all(engine)
    return engine


def _project(engine: Engine, name: str = "Clase") -> Project:
    project = Project(name, created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    return project


def _items(
    engine: Engine, project: Project, count: int
) -> list[tuple[TranscriptionJob, JobSelection]]:
    assets = SqliteMediaAssetRepository(engine)
    items: list[tuple[TranscriptionJob, JobSelection]] = []
    for index in range(count):
        asset = MediaAsset(
            project.id, f"{index:064x}", f"c-{index}.wav", 10, duration_ms=2_000
        )
        assets.add(asset)
        job = TranscriptionJob.create(
            job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
        )
        selection = JobSelection(
            job_id=job.id,
            option_id="option-v1-fixture",
            model=MODEL,
            execution=None,
            language="es",
            created_at=NOW,
        )
        items.append((job, selection))
    return items


def _count(engine: Engine, table: Table) -> int:
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(table)) or 0


def test_add_round_trips_queue_skipped_and_job_order(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    project = _project(engine)
    items = _items(engine, project, 3)
    skipped = (
        SkippedRecording(uuid4(), SkipReason.ALREADY_TRANSCRIBED),
        SkippedRecording(uuid4(), SkipReason.DURATION_UNKNOWN),
    )
    queue = TranscriptionQueue(uuid4(), project.id, NOW, skipped)
    repo = SqliteTranscriptionQueueRepository(engine)

    repo.add(queue, items)

    assert repo.get(queue.id) == queue
    assert repo.job_ids(queue.id) == [job.id for job, _ in items]
    jobs = SqliteTranscriptionJobRepository(engine)
    assert all(jobs.get(job.id) == job for job, _ in items)
    selections = SqliteTranscriptionJobSelectionRepository(engine)
    assert all(selections.get(job.id) == sel for job, sel in items)
    assert repo.get(uuid4()) is None
    assert repo.job_ids(uuid4()) == []


def test_a_failing_item_leaves_no_queue_job_or_selection(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    project = _project(engine)
    items = _items(engine, project, 3)
    # The third job points at a recording that does not exist: the whole write fails.
    broken = TranscriptionJob.create(
        job_id=items[2][0].id,
        project_id=project.id,
        media_asset_id=uuid4(),
        now=NOW,
    )
    items[2] = (broken, items[2][1])
    queue = TranscriptionQueue(uuid4(), project.id, NOW)

    with pytest.raises(IntegrityError):
        SqliteTranscriptionQueueRepository(engine).add(queue, items)

    for table in (
        transcription_queues,
        transcription_queue_items,
        transcription_jobs,
        transcription_job_selections,
    ):
        assert _count(engine, table) == 0


def test_latest_for_project_is_the_last_created_even_at_the_same_instant(
    tmp_path: Path,
) -> None:
    engine = _engine(tmp_path)
    project = _project(engine)
    other = _project(engine, "Otra")
    repo = SqliteTranscriptionQueueRepository(engine)
    assert repo.latest_for_project(project.id) is None
    queues = [TranscriptionQueue(uuid4(), project.id, NOW) for _ in range(4)]
    for queue in queues:
        repo.add(queue, _items(engine, project, 1))

    assert repo.latest_for_project(project.id) == queues[-1]
    assert repo.latest_for_project(other.id) is None


def test_foreign_keys_are_enforced_on_the_queue_connection(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    queue = TranscriptionQueue(uuid4(), uuid4(), NOW)  # unknown project

    with pytest.raises(IntegrityError):
        SqliteTranscriptionQueueRepository(engine).add(queue, [])

    assert _count(engine, transcription_queues) == 0
