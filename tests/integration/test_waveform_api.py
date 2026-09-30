"""Waveform peaks HTTP contract through ASGI with real SQLite, storage and FFmpeg."""

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
from voz.application.waveform_peaks import GetWaveformPeaks
from voz.domain.entities.project import Project
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.audio.waveform_peaks import FfmpegWaveformPeaks
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
)
from voz.interfaces.api.waveform import create_waveform_router

REPOSITORY_ROOT = Path(__file__).parents[2]
MEDIA_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.mp3"

pytestmark = pytest.mark.skipif(
    shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
    reason="ffmpeg and ffprobe are required",
)


@dataclass(slots=True)
class _Harness:
    app: FastAPI
    media_asset_id: UUID
    duration_ms: int


def _build(tmp_path: Path, *, executable: str = "ffmpeg") -> _Harness:
    database_path = tmp_path / "data" / "voz.db"
    engine = create_sqlite_engine(database_path)
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    storage = FileSystemMediaStorage(tmp_path / "data")
    assets = SqliteMediaAssetRepository(engine)
    projects = SqliteProjectRepository(engine)
    project = Project("Waveform course")
    projects.add(project)
    source = tmp_path / "synthetic-tone.mp3"
    source.write_bytes(MEDIA_FIXTURE.read_bytes())
    imported = ImportMedia(
        media_probe=FfprobeMediaProbe(), media_storage=storage, media_assets=assets
    ).execute(source=source, project_id=project.id)

    app = FastAPI()
    app.include_router(
        create_waveform_router(
            GetWaveformPeaks(
                assets,
                FfmpegWaveformPeaks(
                    storage_root=tmp_path / "data",
                    cache_root=tmp_path / "cache",
                    media_storage=storage,
                    executable=executable,
                ),
            )
        )
    )
    return _Harness(
        app, imported.media_asset.id, cast(int, imported.media_asset.duration_ms)
    )


async def _get(app: FastAPI, path: str, query: str) -> tuple[int, dict[str, object]]:
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": [],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    body = b"".join(cast(bytes, m.get("body", b"")) for m in messages[1:])
    return int(cast(int, messages[0]["status"])), json.loads(body)


def _fetch(
    harness: _Harness, media_asset_id: UUID | str | None = None, query: str = ""
) -> tuple[int, dict[str, object]]:
    target = harness.media_asset_id if media_asset_id is None else media_asset_id
    return asyncio.run(_get(harness.app, f"/api/media/{target}/peaks", query))


def test_default_request_returns_2000_normalized_peaks(tmp_path: Path) -> None:
    harness = _build(tmp_path)

    status, body = _fetch(harness)

    assert status == 200
    assert body["media_asset_id"] == str(harness.media_asset_id)
    assert body["duration_ms"] == harness.duration_ms
    assert body["buckets"] == 2000
    peaks = cast(list[list[float]], body["peaks"])
    assert len(peaks) == 2000
    assert all(len(pair) == 2 and -1.0 <= pair[0] <= pair[1] <= 1.0 for pair in peaks)


def test_explicit_bucket_count_is_honored(tmp_path: Path) -> None:
    status, body = _fetch(_build(tmp_path), query="buckets=150")

    assert status == 200
    assert body["buckets"] == 150
    assert len(cast(list[object], body["peaks"])) == 150


@pytest.mark.parametrize("buckets", ["99", "20001", "0", "-5", "abc", "", "1.5"])
def test_invalid_buckets_are_rejected(tmp_path: Path, buckets: str) -> None:
    status, body = _fetch(_build(tmp_path), query=f"buckets={buckets}")

    assert status == 422
    assert cast(dict[str, object], body["detail"])["code"] == "peaks_buckets_invalid"


def test_unknown_asset_is_not_found(tmp_path: Path) -> None:
    status, body = _fetch(_build(tmp_path), uuid4())

    assert status == 404
    assert cast(dict[str, object], body["detail"])["code"] == "media_asset_not_found"


def test_decoder_failure_is_a_safe_500(tmp_path: Path) -> None:
    status, body = _fetch(_build(tmp_path, executable="/nonexistent/ffmpeg"))

    assert status == 500
    detail = cast(dict[str, object], body["detail"])
    assert detail["code"] == "waveform_unavailable"
    assert str(tmp_path) not in json.dumps(body)
