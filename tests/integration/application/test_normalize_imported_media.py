"""End-to-end import and normalization coverage with real local adapters."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from alembic import command
from alembic.config import Config

from voz.application.import_media import ImportMedia
from voz.application.normalize_media import NormalizeImportedMedia
from voz.domain.entities.project import Project
from voz.infrastructure.audio.ffmpeg import FfmpegMediaNormalizer
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
MEDIA_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.webm"


def _migrate(database_path: Path) -> None:
    engine = create_sqlite_engine(database_path)
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()


def test_import_then_normalize_preserves_original_and_persisted_hash(
    tmp_path: Path,
) -> None:
    source_digest = hashlib.sha256(MEDIA_FIXTURE.read_bytes()).hexdigest()
    data_root = tmp_path / "data"
    database_path = data_root / "voz.db"
    storage_root = data_root / "media"
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    project = Project("Normalization integration")
    projects = SqliteProjectRepository(engine)
    media_assets = SqliteMediaAssetRepository(engine)
    projects.add(project)
    storage = FileSystemMediaStorage(storage_root)

    imported = ImportMedia(
        media_probe=FfprobeMediaProbe(),
        media_storage=storage,
        media_assets=media_assets,
    ).execute(source=MEDIA_FIXTURE, project_id=project.id)
    original_path = storage.original_path_for(project.id, imported.media_asset.id)
    stored_digest_before = hashlib.sha256(original_path.read_bytes()).hexdigest()
    normalizer = FfmpegMediaNormalizer(storage_root)

    normalized = NormalizeImportedMedia(
        media_storage=storage,
        media_normalization=normalizer,
    ).execute(imported_media=imported)

    persisted = media_assets.get(imported.media_asset.id)
    normalized_path = normalizer.normalized_path_for(
        project.id,
        imported.media_asset.id,
    )
    assert persisted == imported.media_asset
    assert persisted is not None
    assert persisted.content_sha256 == source_digest
    assert imported.media_asset.content_sha256 == source_digest
    assert hashlib.sha256(MEDIA_FIXTURE.read_bytes()).hexdigest() == source_digest
    assert (
        hashlib.sha256(original_path.read_bytes()).hexdigest() == stored_digest_before
    )
    assert stored_digest_before == source_digest
    assert original_path != normalized_path
    assert normalized.bytes_written == normalized_path.stat().st_size
    with normalized_path.open("rb") as opened:
        output_probe = FfprobeMediaProbe().probe(opened)
    assert output_probe.audio_streams[0].codec_name == "pcm_s16le"
    assert output_probe.audio_streams[0].sample_rate_hz == 16_000
    assert output_probe.audio_streams[0].channels == 1
    assert not list(storage_root.rglob(".normalize-*.tmp.wav"))
    assert not {
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith("voz-ffmpeg-")
    }
    engine.dispose()
