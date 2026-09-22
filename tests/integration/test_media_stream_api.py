"""Inline original streaming exercised through ASGI with real SQLite and storage."""

from __future__ import annotations

import asyncio
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
from voz.domain.entities.project import Project
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
)
from voz.interfaces.api.media_stream import create_media_stream_router

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
    media_asset_id: UUID
    storage: FileSystemMediaStorage


def _build(tmp_path: Path) -> _Harness:
    database_path = tmp_path / "data" / "voz.db"
    _migrate(database_path)
    engine = create_sqlite_engine(database_path)
    storage = FileSystemMediaStorage(tmp_path / "data")
    assets = SqliteMediaAssetRepository(engine)
    projects = SqliteProjectRepository(engine)
    project = Project("Stream course")
    projects.add(project)

    source_dir = tmp_path / "incoming"
    source_dir.mkdir()
    source = source_dir / "synthetic-tone.wav"
    source.write_bytes(MEDIA_FIXTURE.read_bytes())
    imported = ImportMedia(
        media_probe=FfprobeMediaProbe(),
        media_storage=storage,
        media_assets=assets,
    ).execute(source=source, project_id=project.id)

    app = FastAPI()
    app.include_router(create_media_stream_router(assets, storage))
    return _Harness(app, project.id, imported.media_asset.id, storage)


async def _get(
    app: FastAPI,
    media_asset_id: UUID | str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    raw_headers: list[tuple[bytes, bytes]] = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    path = f"/api/media/{media_asset_id}/original"
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
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
    start = messages[0]
    response_headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in cast(list[tuple[bytes, bytes]], start.get("headers", []))
    }
    body = b"".join(cast(bytes, m.get("body", b"")) for m in messages[1:])
    return int(cast(int, start["status"])), response_headers, body


def _fetch(
    harness: _Harness,
    media_asset_id: UUID | str | None = None,
    **headers: str,
) -> tuple[int, dict[str, str], bytes]:
    target = harness.media_asset_id if media_asset_id is None else media_asset_id
    return asyncio.run(_get(harness.app, target, headers=headers or None))


def _detail(body: bytes) -> dict[str, object]:
    return cast(dict[str, object], json.loads(body)["detail"])


def test_full_original_is_streamed_inline_with_its_media_type(
    tmp_path: Path,
) -> None:
    harness = _build(tmp_path)
    fixture_bytes = MEDIA_FIXTURE.read_bytes()

    status, headers, body = _fetch(harness)

    assert status == 200
    assert body == fixture_bytes
    assert headers["content-type"] == "audio/wav"
    assert headers["content-length"] == str(len(fixture_bytes))
    assert headers["accept-ranges"] == "bytes"
    assert headers["cache-control"] == "private, max-age=3600"
    assert "content-disposition" not in headers
    assert str(tmp_path) not in json.dumps(headers)


def test_byte_range_returns_partial_content(tmp_path: Path) -> None:
    harness = _build(tmp_path)
    fixture_bytes = MEDIA_FIXTURE.read_bytes()

    status, headers, body = _fetch(harness, Range="bytes=0-3")

    assert status == 206
    assert body == fixture_bytes[:4]
    assert len(body) == 4
    assert headers["content-range"] == f"bytes 0-3/{len(fixture_bytes)}"
    assert headers["content-length"] == "4"
    assert headers["content-type"] == "audio/wav"


def test_unsatisfiable_range_is_rejected(tmp_path: Path) -> None:
    harness = _build(tmp_path)
    size = MEDIA_FIXTURE.stat().st_size

    status, headers, _ = _fetch(harness, Range=f"bytes={size + 10}-{size + 20}")

    assert status == 416
    assert headers["content-range"] == f"bytes */{size}"


def test_unknown_asset_is_not_found(tmp_path: Path) -> None:
    harness = _build(tmp_path)

    status, _, body = _fetch(harness, uuid4())

    assert status == 404
    assert _detail(body)["code"] == "media_asset_not_found"
    assert str(tmp_path) not in body.decode()


def test_deleted_original_file_is_reported_missing_without_path(
    tmp_path: Path,
) -> None:
    harness = _build(tmp_path)
    original = harness.storage.original_path_for(
        harness.project_id, harness.media_asset_id
    )
    original.chmod(0o644)
    original.unlink()

    status, _, body = _fetch(harness)

    assert status == 404
    assert _detail(body)["code"] == "media_file_missing"
    assert str(tmp_path) not in body.decode()
