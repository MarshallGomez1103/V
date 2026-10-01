"""Migration 0007, glossary persistence and profile/glossary in selections."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.quality_profiles import ACADEMIC_PROFILE
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.project_glossaries import (
    SqliteProjectGlossaryRepository,
)
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 9, 30, 8, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="turbo",
    display_name="Turbo",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


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


def _migrate(engine: Engine, revision: str = "head") -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def _project(engine: Engine) -> Project:
    project = Project("Clase", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    return project


def test_migration_0007_keeps_old_selections_and_downgrades(engine: Engine) -> None:
    config = _config(engine)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0006_segment_quality")
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p', 'P', '2026-09-30T08:00:00+00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m', 'p', 'h', 'a.wav', 1, 'now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_jobs VALUES ('j', 'p', 'm', 'QUEUED', 0.0,"
            " 'now', 'now', NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO transcription_job_selections (job_id, option_id, provider_id,"
            " model_id, model_json, created_at)"
            " VALUES ('j', 'o', 'x', 'y', '{}', 'now')"
        )
        connection.commit()

        command.upgrade(config, "0007_project_glossary")
        row = connection.execute(
            text(
                "SELECT option_id, profile_json, glossary_json FROM"
                " transcription_job_selections"
            )
        ).one()
        assert tuple(row) == ("o", None, None)
        assert "project_glossaries" in inspect(connection).get_table_names()

        command.downgrade(config, "0006_segment_quality")
        columns = {
            c["name"]
            for c in inspect(connection).get_columns("transcription_job_selections")
        }
        assert {"profile_json", "glossary_json"}.isdisjoint(columns)
        assert "project_glossaries" not in inspect(connection).get_table_names()
        assert (
            connection.execute(
                text("SELECT option_id FROM transcription_job_selections")
            ).scalar_one()
            == "o"
        )


def test_glossary_round_trips_replaces_and_clears(engine: Engine) -> None:
    _migrate(engine)
    project = _project(engine)
    repository = SqliteProjectGlossaryRepository(engine)

    assert repository.get(project.id) == ()
    repository.put(project.id, ("Mitocondria", "ñandú", "VOZ"))
    assert repository.get(project.id) == ("Mitocondria", "ñandú", "VOZ")
    repository.put(project.id, ("solo",))
    assert repository.get(project.id) == ("solo",)
    repository.put(project.id, ())
    assert repository.get(project.id) == ()


def test_glossaries_are_per_project_and_cascade_on_project_delete(
    engine: Engine,
) -> None:
    _migrate(engine)
    first, second = _project(engine), _project(engine)
    repository = SqliteProjectGlossaryRepository(engine)
    repository.put(first.id, ("a",))
    repository.put(second.id, ("b",))

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM projects WHERE id = :id"), {"id": str(first.id)}
        )

    assert repository.get(first.id) == ()
    assert repository.get(second.id) == ("b",)
    assert repository.get(UUID(int=0)) == ()


def _selection_for(engine: Engine, **extra: object) -> JobSelection:
    project = _project(engine)
    asset = MediaAsset(project.id, "a" * 64, "clase.wav", 10, duration_ms=1_000)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
    )
    SqliteTranscriptionJobRepository(engine).add(job)
    return JobSelection(
        job_id=job.id,
        option_id="o",
        model=MODEL,
        execution=None,
        language="es",
        created_at=NOW,
        **extra,  # type: ignore[arg-type]
    )


def test_selection_keeps_the_full_profile_and_frozen_glossary(engine: Engine) -> None:
    _migrate(engine)
    selection = _selection_for(
        engine, quality_profile=ACADEMIC_PROFILE, glossary=("Mitocondria", "VOZ")
    )
    repository = SqliteTranscriptionJobSelectionRepository(engine)

    repository.add(selection)

    stored = repository.get(selection.job_id)
    assert stored == selection
    assert stored is not None and stored.quality_profile == ACADEMIC_PROFILE


def test_selection_without_profile_or_glossary_reads_back_empty(
    engine: Engine,
) -> None:
    _migrate(engine)
    selection = _selection_for(engine)
    repository = SqliteTranscriptionJobSelectionRepository(engine)

    repository.add(selection)

    stored = repository.get(selection.job_id)
    assert stored is not None
    assert stored.quality_profile is None
    assert stored.glossary == ()
