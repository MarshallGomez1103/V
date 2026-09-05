"""File-backed integration coverage for the complete media import use case."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from voz.application.import_media import ImportMedia
from voz.application.ports.media_probe import MediaProbeError, MediaProbeFailureCode
from voz.application.ports.media_storage import ImportedOriginal
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
MEDIA_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"


class _SourceMutatingStorage(FileSystemMediaStorage):
    def import_original(
        self,
        *,
        source: Path,
        project_id: UUID,
        media_asset_id: UUID,
        media_type: str | None = None,
    ) -> ImportedOriginal:
        imported = super().import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
            media_type=media_type,
        )
        source.write_bytes(b"source changed after immutable copy")
        return imported


class _PostCommitThenRaiseRepository(SqliteMediaAssetRepository):
    def add(self, media_asset: MediaAsset) -> None:
        super().add(media_asset)
        raise RuntimeError("connection dropped after commit")


def _migrate(database_path: Path) -> None:
    engine = create_sqlite_engine(database_path)
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()


def test_import_persists_probe_metadata_and_preserves_reopenable_original(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "voz.db"
    storage = FileSystemMediaStorage(tmp_path / "data" / "media")
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    project = Project("Integration course")
    SqliteProjectRepository(engine).add(project)

    imported = ImportMedia(
        media_probe=FfprobeMediaProbe(),
        media_storage=storage,
        media_assets=SqliteMediaAssetRepository(engine),
    ).execute(source=MEDIA_FIXTURE, project_id=project.id)
    engine.dispose()

    reopened_engine = create_sqlite_engine(database_path)
    persisted = SqliteMediaAssetRepository(reopened_engine).get(imported.media_asset.id)
    reopened_engine.dispose()
    expected_bytes = MEDIA_FIXTURE.read_bytes()

    assert persisted == imported.media_asset
    assert persisted is not None
    assert persisted.content_sha256 == hashlib.sha256(expected_bytes).hexdigest()
    assert persisted.duration_ms == 250
    assert persisted.media_type == "audio/wav"
    assert imported.probe_result.audio_streams[0].codec_name == "pcm_s16le"
    assert imported.probe_result.audio_streams[0].sample_rate_hz == 16_000
    assert imported.probe_result.audio_streams[0].channels == 1
    with storage.open_original(
        project_id=project.id,
        media_asset_id=persisted.id,
    ) as original:
        assert original.read() == expected_bytes
    assert str(storage.original_path_for(project.id, persisted.id)) not in repr(
        imported
    )


def test_sqlite_rejection_compensates_the_published_original(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "voz.db"
    storage = FileSystemMediaStorage(tmp_path / "data" / "media")
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    missing_project_id = uuid4()
    media_asset_id = uuid4()

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        ImportMedia(
            media_probe=FfprobeMediaProbe(),
            media_storage=storage,
            media_assets=SqliteMediaAssetRepository(engine),
            id_factory=lambda: media_asset_id,
        ).execute(source=MEDIA_FIXTURE, project_id=missing_project_id)

    engine.dispose()
    original_path = storage.original_path_for(missing_project_id, media_asset_id)
    assert not original_path.exists()
    assert not list(original_path.parent.glob(".import-*.tmp"))


def test_corrupt_import_is_path_safe_and_leaves_repository_and_storage_clean(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "voz.db"
    storage = FileSystemMediaStorage(tmp_path / "data" / "media")
    source = tmp_path / "private-course-name.wav"
    source.write_bytes(b"this is corrupt media, not a wav")
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    project = Project("Corrupt media course")
    repository = SqliteMediaAssetRepository(engine)
    SqliteProjectRepository(engine).add(project)
    media_asset_id = uuid4()

    with pytest.raises(MediaProbeError) as captured:
        ImportMedia(
            media_probe=FfprobeMediaProbe(),
            media_storage=storage,
            media_assets=repository,
            id_factory=lambda: media_asset_id,
        ).execute(source=source, project_id=project.id)

    assert captured.value.code is MediaProbeFailureCode.INVALID_MEDIA
    assert source.name not in str(captured.value)
    assert repository.get(media_asset_id) is None
    original_path = storage.original_path_for(project.id, media_asset_id)
    assert not original_path.exists()
    assert not list(original_path.parent.glob(".import-*.tmp"))
    engine.dispose()


def test_import_probes_stored_copy_when_source_changes_after_publication(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "voz.db"
    storage = _SourceMutatingStorage(tmp_path / "data" / "media")
    source = tmp_path / "changing-source.wav"
    expected_bytes = MEDIA_FIXTURE.read_bytes()
    source.write_bytes(expected_bytes)
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    project = Project("Changing source course")
    repository = SqliteMediaAssetRepository(engine)
    SqliteProjectRepository(engine).add(project)

    imported = ImportMedia(
        media_probe=FfprobeMediaProbe(),
        media_storage=storage,
        media_assets=repository,
    ).execute(source=source, project_id=project.id)

    assert source.read_bytes() != expected_bytes
    assert (
        imported.media_asset.content_sha256
        == hashlib.sha256(expected_bytes).hexdigest()
    )
    assert imported.probe_result.duration_ms == 250
    with storage.open_original(
        project_id=project.id,
        media_asset_id=imported.media_asset.id,
    ) as original:
        assert original.read() == expected_bytes
    engine.dispose()


def test_post_commit_exception_keeps_persisted_row_and_original(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "voz.db"
    storage = FileSystemMediaStorage(tmp_path / "data" / "media")
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    project = Project("Commit reconciliation course")
    SqliteProjectRepository(engine).add(project)
    repository = _PostCommitThenRaiseRepository(engine)

    imported = ImportMedia(
        media_probe=FfprobeMediaProbe(),
        media_storage=storage,
        media_assets=repository,
    ).execute(source=MEDIA_FIXTURE, project_id=project.id)

    assert repository.get(imported.media_asset.id) == imported.media_asset
    with storage.open_original(
        project_id=project.id,
        media_asset_id=imported.media_asset.id,
    ) as original:
        assert original.read() == MEDIA_FIXTURE.read_bytes()
    engine.dispose()
