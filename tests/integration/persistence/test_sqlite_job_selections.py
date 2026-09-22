"""Selection snapshots round-trip through SQLite and cascade with their job."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, inspect
from sqlalchemy.exc import IntegrityError

from voz.application.asr_device_selection import (
    ComputeDevice,
    ExecutionDecision,
    FallbackReason,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.schema import transcription_jobs
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="turbo",
    display_name="Turbo",
    source="publisher/turbo",
    revision="c" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16, ComputePrecision.INT8_FLOAT16),
        ComputePrecision.INT8,
    ),
    capabilities=frozenset(
        {ModelCapability.TRANSCRIPTION, ModelCapability.LANGUAGE_DETECTION}
    ),
)


def _config(url: str) -> Config:
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_migration_0003_upgrades_and_downgrades_cleanly(tmp_path: Path) -> None:
    engine = create_sqlite_engine((tmp_path / "m.db").absolute())
    config = _config(str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002_asr_checkpoints")
        assert (
            "transcription_job_selections" not in inspect(connection).get_table_names()
        )
        command.upgrade(config, "0003_job_selections")
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "transcription_job_selections"
            )
        }
        assert {"job_id", "option_id", "model_json", "execution_json"} <= columns
        command.downgrade(config, "0002_asr_checkpoints")
        assert (
            "transcription_job_selections" not in inspect(connection).get_table_names()
        )
    engine.dispose()


def test_snapshot_round_trips_and_cascades_with_job(tmp_path: Path) -> None:
    engine = create_sqlite_engine((tmp_path / "s.db").absolute())
    config = _config(str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    project = Project("Demo", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 10, duration_ms=250)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
    )
    SqliteTranscriptionJobRepository(engine).add(job)

    repository: TranscriptionJobSelectionRepository = (
        SqliteTranscriptionJobSelectionRepository(engine)
    )
    assert isinstance(repository, TranscriptionJobSelectionRepository)
    selection = JobSelection(
        job_id=job.id,
        option_id="option-v1-abc",
        model=MODEL,
        execution=ExecutionDecision(
            ComputeDevice.CPU,
            ComputePrecision.INT8,
            FallbackReason.CUDA_UNAVAILABLE,
        ),
        language="es",
        created_at=NOW,
    )
    repository.add(selection)

    assert repository.get(job.id) == selection
    assert repository.get(uuid4()) is None
    with pytest.raises(IntegrityError):
        repository.add(selection)

    minimal = JobSelection(
        job_id=uuid4(),
        option_id="option-v1-min",
        model=ModelDescriptor(
            provider_id="x",
            model_id="y",
            display_name="Y",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        ),
        execution=None,
        language=None,
        created_at=NOW,
    )
    with pytest.raises(IntegrityError):
        repository.add(minimal)

    with engine.begin() as connection:
        connection.execute(
            delete(transcription_jobs).where(transcription_jobs.c.id == str(job.id))
        )
    assert repository.get(job.id) is None
    engine.dispose()
