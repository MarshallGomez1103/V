"""Raw-body upload endpoint exercised through ASGI with real SQLite and storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from starlette.types import Message

from voz.application.import_media import ImportMedia
from voz.application.ports.media_probe import MediaProbePort
from voz.application.ports.media_storage import MediaStoragePort
from voz.application.ports.repositories import MediaAssetRepository
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
)
from voz.interfaces.api.media import FILENAME_HEADER, create_media_router

REPOSITORY_ROOT = Path(__file__).parents[2]
MEDIA_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"

pytestmark = pytest.mark.skipif(
    shutil.which("ffprobe") is None,
    reason="ffprobe is required for real probe coverage",
)


def _migrate(database_path: Path) -> None:
    engine = create_sqlite_engine(database_path)
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()


@dataclass(slots=True)
class _Harness:
    app: FastAPI
    project_id: UUID
    upload_dir: Path
    storage: FileSystemMediaStorage
    media_assets: SqliteMediaAssetRepository


def _build(
    tmp_path: Path,
    *,
    max_upload_bytes: int | None = None,
    media_probe: MediaProbePort | None = None,
    media_storage: MediaStoragePort | None = None,
    media_assets: MediaAssetRepository | None = None,
) -> _Harness:
    database_path = tmp_path / "data" / "voz.db"
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    storage = FileSystemMediaStorage(tmp_path / "data")
    assets = SqliteMediaAssetRepository(engine)
    projects = SqliteProjectRepository(engine)
    project = Project("Upload course")
    projects.add(project)

    upload_dir = tmp_path / "cache" / "uploads"
    import_media = ImportMedia(
        media_probe=FfprobeMediaProbe() if media_probe is None else media_probe,
        media_storage=storage if media_storage is None else media_storage,
        media_assets=assets if media_assets is None else media_assets,
    )
    app = FastAPI()
    if max_upload_bytes is None:
        app.include_router(create_media_router(import_media, projects, upload_dir))
    else:
        app.include_router(
            create_media_router(
                import_media,
                projects,
                upload_dir,
                max_upload_bytes=max_upload_bytes,
            )
        )
    return _Harness(app, project.id, upload_dir, storage, assets)


async def _post(
    app: FastAPI,
    project_id: UUID | str,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
    chunk_size: int = 1024,
    content_length: bool = True,
) -> tuple[int, dict[str, object]]:
    chunks = [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)] or [
        b""
    ]
    raw_headers: list[tuple[bytes, bytes]] = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    if content_length:
        raw_headers.append((b"content-length", str(len(body)).encode()))
    messages: list[Message] = []

    async def receive() -> Message:
        if chunks:
            chunk = chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    path = f"/api/projects/{project_id}/media"
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": raw_headers,
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    payload = b"".join(cast(bytes, m.get("body", b"")) for m in messages)
    return int(cast(int, messages[0]["status"])), cast(
        dict[str, object], json.loads(payload)
    )


def _upload(
    harness: _Harness,
    body: bytes,
    *,
    filename: str | None = "synthetic-tone.wav",
    project_id: UUID | str | None = None,
    **kwargs: object,
) -> tuple[int, dict[str, object]]:
    headers = {} if filename is None else {FILENAME_HEADER: filename}
    target = harness.project_id if project_id is None else project_id
    chunk_size = cast(int, kwargs.get("chunk_size", 1024))
    content_length = cast(bool, kwargs.get("content_length", True))
    return asyncio.run(
        _post(
            harness.app,
            target,
            body,
            headers=headers,
            chunk_size=chunk_size,
            content_length=content_length,
        )
    )


def _staging_is_empty(upload_dir: Path) -> bool:
    return not upload_dir.exists() or not any(upload_dir.iterdir())


def _detail(body: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], body["detail"])


def test_wav_upload_persists_asset_and_returns_path_free_metadata(
    tmp_path: Path,
) -> None:
    harness = _build(tmp_path)
    fixture_bytes = MEDIA_FIXTURE.read_bytes()

    status, body = _upload(harness, fixture_bytes, chunk_size=1000)

    assert status == 201
    assert body["project_id"] == str(harness.project_id)
    assert body["filename"] == "synthetic-tone.wav"
    assert body["media_type"] == "audio/wav"
    assert body["duration_ms"] == 250
    assert body["sha256"] == hashlib.sha256(fixture_bytes).hexdigest()
    assert str(tmp_path) not in json.dumps(body)

    persisted = harness.media_assets.get(UUID(cast(str, body["media_asset_id"])))
    assert persisted is not None
    assert persisted.display_name == "synthetic-tone.wav"
    assert persisted.content_sha256 == body["sha256"]
    with harness.storage.open_original(
        project_id=harness.project_id,
        media_asset_id=persisted.id,
    ) as original:
        assert original.read() == fixture_bytes
    assert _staging_is_empty(harness.upload_dir)


def test_garbage_body_is_reported_as_corrupt_media_and_leaves_nothing(
    tmp_path: Path,
) -> None:
    harness = _build(tmp_path)

    status, body = _upload(harness, b"this is definitely not media" * 50)

    assert status == 422
    assert _detail(body)["code"] == "media_corrupt"
    assert harness.media_assets.list_by_project(harness.project_id) == ()
    assert _staging_is_empty(harness.upload_dir)


def test_missing_filename_header_is_rejected(tmp_path: Path) -> None:
    harness = _build(tmp_path)

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes(), filename=None)

    assert status == 400
    assert _detail(body)["code"] == "filename_invalid"
    assert _staging_is_empty(harness.upload_dir)


@pytest.mark.parametrize(
    "filename",
    [
        "../synthetic-tone.wav",
        "..",
        ".",
        "dir/tone.wav",
        "dir\\tone.wav",
        "   ",
        "a\x00b",
    ],
)
def test_path_like_or_control_filenames_are_rejected_not_sanitized(
    tmp_path: Path, filename: str
) -> None:
    harness = _build(tmp_path)

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes(), filename=filename)

    assert status == 400
    assert _detail(body)["code"] == "filename_invalid"
    assert harness.media_assets.list_by_project(harness.project_id) == ()
    assert _staging_is_empty(harness.upload_dir)


def test_percent_encoded_utf8_filename_is_preserved(tmp_path: Path) -> None:
    harness = _build(tmp_path)

    status, body = _upload(
        harness,
        MEDIA_FIXTURE.read_bytes(),
        filename="clase%20de%20se%C3%B1ales.wav",
    )

    assert status == 201
    assert body["filename"] == "clase de señales.wav"


def test_unknown_project_is_not_found_before_reading_body(tmp_path: Path) -> None:
    harness = _build(tmp_path)

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes(), project_id=uuid4())

    assert status == 404
    assert _detail(body)["code"] == "project_not_found"
    assert _staging_is_empty(harness.upload_dir)


def test_declared_oversize_body_is_rejected_early(tmp_path: Path) -> None:
    harness = _build(tmp_path, max_upload_bytes=100)

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes())

    assert status == 413
    assert _detail(body)["code"] == "media_too_large"
    assert _staging_is_empty(harness.upload_dir)


def test_streamed_oversize_body_is_rejected_and_temporary_removed(
    tmp_path: Path,
) -> None:
    harness = _build(tmp_path, max_upload_bytes=100)

    status, body = _upload(
        harness,
        MEDIA_FIXTURE.read_bytes(),
        chunk_size=64,
        content_length=False,
    )

    assert status == 413
    assert _detail(body)["code"] == "media_too_large"
    assert _staging_is_empty(harness.upload_dir)


def test_empty_body_is_rejected(tmp_path: Path) -> None:
    harness = _build(tmp_path)

    status, body = _upload(harness, b"")

    assert status == 400
    assert _detail(body)["code"] == "media_empty"
    assert _staging_is_empty(harness.upload_dir)


def test_unsafe_storage_root_maps_to_service_unavailable(tmp_path: Path) -> None:
    blocked_root = tmp_path / "blocked"
    blocked_root.write_bytes(b"not a directory")
    harness = _build(tmp_path, media_storage=FileSystemMediaStorage(blocked_root))

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes())

    assert status == 503
    assert _detail(body)["code"] == "media_storage_unavailable"
    assert str(tmp_path) not in json.dumps(body)
    assert _staging_is_empty(harness.upload_dir)


def test_missing_probe_tool_maps_to_service_unavailable(tmp_path: Path) -> None:
    harness = _build(
        tmp_path,
        media_probe=FfprobeMediaProbe(executable=str(tmp_path / "missing-ffprobe")),
    )

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes())

    assert status == 503
    assert _detail(body)["code"] == "media_probe_unavailable"
    assert str(tmp_path) not in json.dumps(body)
    assert harness.media_assets.list_by_project(harness.project_id) == ()
    assert _staging_is_empty(harness.upload_dir)


class _BrokenRepository:
    def add(self, media_asset: MediaAsset) -> None:
        raise RuntimeError(f"connection lost at {media_asset.display_name}")

    def save(self, media_asset: MediaAsset) -> None:
        raise RuntimeError("unused")

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        raise RuntimeError("/private/host/path leaked in diagnostic")

    def list_by_project(self, project_id: UUID) -> tuple[MediaAsset, ...]:
        return ()


def test_unexpected_failure_is_generic_without_traceback(tmp_path: Path) -> None:
    harness = _build(tmp_path, media_assets=_BrokenRepository())

    status, body = _upload(harness, MEDIA_FIXTURE.read_bytes())

    assert status == 500
    assert _detail(body)["code"] == "media_import_failed"
    serialized = json.dumps(body)
    assert "/private/" not in serialized
    assert "Traceback" not in serialized
    assert str(tmp_path) not in serialized
    assert _staging_is_empty(harness.upload_dir)
