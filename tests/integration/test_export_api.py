"""Transcript export download exercised through ASGI over real SQLite repositories."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.types import Message

from voz.application.export.service import ExportTranscript
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.interfaces.api.export import create_export_router

NOW = datetime(2026, 9, 21, 9, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.body))

    def detail(self) -> dict[str, object]:
        return cast(dict[str, object], self.json()["detail"])


class Harness:
    def __init__(self, engine: Engine, project_name: str) -> None:
        project = Project(project_name, created_at=NOW)
        SqliteProjectRepository(engine).add(project)
        asset = MediaAsset(project.id, "a" * 64, "clase.wav", 10, duration_ms=5_000)
        SqliteMediaAssetRepository(engine).add(asset)
        transcript = Transcript(project.id, asset.id, language="es", created_at=NOW)
        SqliteTranscriptRepository(engine).add(transcript)
        speaker = Speaker(project.id, "Ana", "#112233")
        SqliteSpeakerRepository(engine).add(speaker)
        segments = SqliteSegmentRepository(engine)
        segments.add(Segment(transcript.id, 0, 1_000, "Hola", speaker_id=speaker.id))
        segments.add(Segment(transcript.id, 1_000, 2_500, "sin dueño"))
        self.transcript_id = transcript.id
        self.app = FastAPI()
        self.app.include_router(
            create_export_router(
                ExportTranscript(
                    SqliteTranscriptRepository(engine),
                    segments,
                    SqliteSpeakerRepository(engine),
                    SqliteProjectRepository(engine),
                    SqliteMediaAssetRepository(engine),
                )
            )
        )

    def get(self, transcript_id: UUID | None = None, query: str = "") -> Response:
        path = f"/api/transcripts/{transcript_id or self.transcript_id}/export"
        return asyncio.run(_get(self.app, path, query))


async def _get(app: FastAPI, path: str, query: str) -> Response:
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
    start = messages[0]
    headers = {
        key.decode().lower(): value.decode()
        for key, value in cast(list[tuple[bytes, bytes]], start["headers"])
    }
    body = b"".join(cast(bytes, m.get("body", b"")) for m in messages[1:])
    return Response(int(cast(int, start["status"])), headers, body)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "voz.sqlite3")
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.mark.parametrize(
    ("query", "media_type", "extension", "needle"),
    [
        ("", "text/plain; charset=utf-8", "txt", "Hola\nsin dueño\n"),
        ("format=txt", "text/plain; charset=utf-8", "txt", "Hola\nsin dueño\n"),
        ("format=markdown", "text/markdown; charset=utf-8", "md", "# Transcript"),
        ("format=srt", "application/x-subrip; charset=utf-8", "srt", "00:00:01,000"),
        ("format=vtt", "text/vtt; charset=utf-8", "vtt", "WEBVTT"),
        ("format=json", "application/json", "json", '"voz.transcript"'),
    ],
)
def test_export_formats_return_attachment_with_content_type(
    engine: Engine, query: str, media_type: str, extension: str, needle: str
) -> None:
    response = Harness(engine, "Clase 1").get(query=query)

    assert response.status == 200
    assert response.headers["content-type"] == media_type
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="Clase 1.{extension}"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert needle in response.body.decode("utf-8")


def test_export_options_change_the_document(engine: Engine) -> None:
    harness = Harness(engine, "Clase 1")

    timestamps = harness.get(query="format=txt&timestamps=true")
    grouped = harness.get(query="format=txt&group_by_speaker=true")

    assert timestamps.body.decode() == (
        "[00:00:00.000] Hola\n[00:00:01.000] sin dueño\n"
    )
    assert grouped.body.decode() == "Ana:\nHola\n\nSin speaker:\nsin dueño\n"


def test_export_unicode_project_name_adds_rfc5987_filename(engine: Engine) -> None:
    response = Harness(engine, "Reunión ñandú").get(query="format=txt")

    assert response.headers["content-disposition"] == (
        'attachment; filename="Reunion nandu.txt"; '
        "filename*=UTF-8''Reuni%C3%B3n%20%C3%B1and%C3%BA.txt"
    )


def test_export_filename_never_carries_paths(engine: Engine) -> None:
    response = Harness(engine, "../../etc/passwd").get(query="format=txt")

    disposition = response.headers["content-disposition"]
    assert disposition == 'attachment; filename="passwd.txt"'
    assert "/" not in disposition


def test_export_unknown_transcript_is_404(engine: Engine) -> None:
    response = Harness(engine, "Clase").get(uuid4(), "format=txt")

    assert response.status == 404
    assert response.detail()["code"] == "transcript_not_found"


def test_export_unknown_format_is_422(engine: Engine) -> None:
    response = Harness(engine, "Clase").get(query="format=docx")

    assert response.status == 422
    assert response.detail()["code"] == "export_format_unknown"


@pytest.mark.parametrize("fmt", ["srt", "vtt", "json"])
@pytest.mark.parametrize("option", ["timestamps=true", "group_by_speaker=true"])
def test_export_options_on_unsupported_format_are_422(
    engine: Engine, fmt: str, option: str
) -> None:
    response = Harness(engine, "Clase").get(query=f"format={fmt}&{option}")

    assert response.status == 422
    assert response.detail()["code"] == "export_option_unsupported"
