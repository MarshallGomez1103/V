"""ASGI coverage of PUT /api/segments/{id} over SQLite."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.types import Message

from voz.application.edit_segment import EditSegmentText
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
from voz.interfaces.api.segments import create_segments_router

NOW = datetime(2026, 9, 30, 9, tzinfo=UTC)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
        metadata.create_all(self.engine)
        project = Project("Demo", created_at=NOW)
        SqliteProjectRepository(self.engine).add(project)
        asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=250)
        SqliteMediaAssetRepository(self.engine).add(asset)
        transcript = Transcript(project.id, asset.id, created_at=NOW)
        SqliteTranscriptRepository(self.engine).add(transcript)
        self.speaker = Speaker(project.id, "Ana", "#112233")
        SqliteSpeakerRepository(self.engine).add(self.speaker)
        self.segments = SqliteSegmentRepository(self.engine)
        self.segment = Segment(
            transcript.id, 0, 250, "hola mundo", speaker_id=self.speaker.id
        )
        self.segments.add(self.segment)
        self.app = FastAPI()
        self.app.include_router(
            create_segments_router(EditSegmentText(self.segments), self.segments)
        )

    def put(self, segment_id: UUID, body: object) -> tuple[int, dict[str, object]]:
        return asyncio.run(_put(self.app, f"/api/segments/{segment_id}", body))


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    created = Harness(tmp_path)
    yield created
    created.engine.dispose()


async def _put(app: FastAPI, path: str, body: object) -> tuple[int, dict[str, object]]:
    payload = json.dumps(body).encode()
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "PUT",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    raw = b"".join(cast(bytes, m.get("body", b"")) for m in messages)
    return int(cast(int, messages[0]["status"])), cast(
        dict[str, object], json.loads(raw)
    )


def _detail(body: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], body["detail"])


def test_put_edits_text_and_preserves_literal_asr(harness: Harness) -> None:
    segment = harness.segment

    status, body = harness.put(segment.id, {"text": "  Hola, mundo.  ", "revision": 0})

    assert status == 200
    assert body == {
        "id": str(segment.id),
        "start_ms": 0,
        "end_ms": 250,
        "text": "Hola, mundo.",
        "edited": True,
        "revision": 1,
        "speaker_id": str(harness.speaker.id),
    }
    stored = harness.segments.get(segment.id)
    assert stored is not None
    assert stored.text == "Hola, mundo."
    assert stored.original_text == "hola mundo"

    status, second = harness.put(segment.id, {"text": "Hola.", "revision": 1})
    assert (status, second["revision"]) == (200, 2)
    stored = harness.segments.get(segment.id)
    assert stored is not None and stored.original_text == "hola mundo"


def test_put_stale_revision_returns_409_with_current_item(harness: Harness) -> None:
    segment = harness.segment
    harness.put(segment.id, {"text": "primero", "revision": 0})

    status, body = harness.put(segment.id, {"text": "segundo", "revision": 0})

    assert status == 409
    detail = _detail(body)
    assert detail["code"] == "segment_revision_conflict"
    current = cast(dict[str, object], detail["current"])
    assert current["text"] == "primero"
    assert (current["revision"], current["edited"]) == (1, True)
    stored = harness.segments.get(segment.id)
    assert stored is not None and stored.text == "primero"


def test_put_unknown_segment_and_invalid_text(harness: Harness) -> None:
    status, body = harness.put(uuid4(), {"text": "x", "revision": 0})
    assert (status, _detail(body)["code"]) == (404, "segment_not_found")

    status, body = harness.put(harness.segment.id, {"text": "   ", "revision": 0})
    assert (status, _detail(body)["code"]) == (422, "segment_text_invalid")
    stored = harness.segments.get(harness.segment.id)
    assert stored is not None and stored.revision == 0 and not stored.edited

    status, _ = harness.put(harness.segment.id, {"text": "x"})
    assert status == 422
