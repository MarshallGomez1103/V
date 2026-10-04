"""ASGI coverage of the speakers endpoints (S6.09-S6.12) over SQLite."""

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

from voz.application.speakers import (
    AssignSegmentSpeaker,
    ListTranscriptSpeakers,
    MergeSpeakers,
    UpdateSpeaker,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.interfaces.api.speakers import create_speakers_router

NOW = datetime(2026, 9, 30, 9, tzinfo=UTC)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
        metadata.create_all(self.engine)
        self.project = Project("Demo", created_at=NOW)
        SqliteProjectRepository(self.engine).add(self.project)
        asset = MediaAsset(
            self.project.id, "a" * 64, "tone.wav", 8_044, duration_ms=900
        )
        SqliteMediaAssetRepository(self.engine).add(asset)
        self.transcripts = SqliteTranscriptRepository(self.engine)
        self.transcript = Transcript(self.project.id, asset.id, created_at=NOW)
        self.other_transcript = Transcript(self.project.id, asset.id, created_at=NOW)
        self.transcripts.add(self.transcript)
        self.transcripts.add(self.other_transcript)
        self.speakers = SqliteSpeakerRepository(self.engine)
        self.turns = SqliteSpeakerTurnRepository(self.engine)
        self.segments = SqliteSegmentRepository(self.engine)
        self.ana = Speaker(self.project.id, "Speaker 1", "#4e79a7")
        self.beto = Speaker(self.project.id, "Speaker 2", "#f28e2b")
        self.lejano = Speaker(self.project.id, "Speaker 1", "#59a14f")
        for speaker in (self.ana, self.beto, self.lejano):
            self.speakers.add(speaker)
        self.s1 = self._segment(self.transcript, 0, self.ana)
        self.s2 = self._segment(self.transcript, 300, self.ana)
        self.s3 = self._segment(self.transcript, 600, self.beto)
        self.s_other = self._segment(self.other_transcript, 0, self.lejano)
        self.turns.replace_for_transcript(
            self.transcript.id,
            (
                SpeakerTurn(self.transcript.id, "A", 0, 500, speaker_id=self.ana.id),
                SpeakerTurn(self.transcript.id, "B", 600, 900, speaker_id=self.beto.id),
            ),
        )
        self.app = FastAPI()
        self.app.include_router(
            create_speakers_router(
                ListTranscriptSpeakers(self.transcripts, self.segments, self.speakers),
                UpdateSpeaker(self.segments, self.speakers),
                MergeSpeakers(self.segments, self.speakers),
                AssignSegmentSpeaker(self.segments, self.speakers),
            )
        )

    def _segment(self, transcript: Transcript, start: int, speaker: Speaker) -> Segment:
        segment = Segment(
            transcript.id, start, start + 250, f"texto {start}", speaker_id=speaker.id
        )
        self.segments.add(segment)
        return segment

    def call(
        self, method: str, path: str, body: object = None
    ) -> tuple[int, dict[str, object]]:
        return asyncio.run(_call(self.app, method, path, body))


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    created = Harness(tmp_path)
    yield created
    created.engine.dispose()


async def _call(
    app: FastAPI, method: str, path: str, body: object
) -> tuple[int, dict[str, object]]:
    payload = b"" if body is None else json.dumps(body).encode()
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
            "method": method,
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


def _code(body: dict[str, object]) -> object:
    return cast(dict[str, object], body["detail"])["code"]


def test_list_returns_only_transcript_speakers_with_counts(harness: Harness) -> None:
    status, body = harness.call(
        "GET", f"/api/transcripts/{harness.transcript.id}/speakers"
    )

    assert status == 200
    assert body == {
        "speakers": [
            {
                "id": str(harness.ana.id),
                "name": "Speaker 1",
                "color": "#4e79a7",
                "segment_count": 2,
                "talk_ms": 500,
                "first_ms": 0,
            },
            {
                "id": str(harness.beto.id),
                "name": "Speaker 2",
                "color": "#f28e2b",
                "segment_count": 1,
                "talk_ms": 250,
                "first_ms": 600,
            },
        ]
    }


def test_list_unknown_transcript_is_404(harness: Harness) -> None:
    status, body = harness.call("GET", f"/api/transcripts/{uuid4()}/speakers")

    assert (status, _code(body)) == (404, "transcript_not_found")


def test_patch_renames_and_recolors_persistently(harness: Harness) -> None:
    status, body = harness.call(
        "PATCH",
        f"/api/speakers/{harness.ana.id}",
        {"name": "  Ana  ", "color": "#AABBCC"},
    )

    assert status == 200
    assert body == {
        "id": str(harness.ana.id),
        "name": "Ana",
        "color": "#aabbcc",
        "segment_count": 2,
        "talk_ms": 500,
        "first_ms": 0,
    }
    stored = harness.speakers.get(harness.ana.id)
    assert stored is not None and (stored.name, stored.color) == ("Ana", "#aabbcc")
    # Segments keep pointing to the same identity: no model re-run, no text change.
    assert harness.segments.get(harness.s1.id) == harness.s1


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": "   "}, {"name": "x" * 81}, {"color": "rojo"}, {"color": "#12345"}],
)
def test_patch_invalid_is_422_and_changes_nothing(
    harness: Harness, payload: dict[str, str]
) -> None:
    status, body = harness.call("PATCH", f"/api/speakers/{harness.ana.id}", payload)

    assert (status, _code(body)) == (422, "speaker_update_invalid")
    assert harness.speakers.get(harness.ana.id) == harness.ana


def test_patch_unknown_speaker_is_404(harness: Harness) -> None:
    status, body = harness.call("PATCH", f"/api/speakers/{uuid4()}", {"name": "X"})

    assert (status, _code(body)) == (404, "speaker_not_found")


def test_merge_moves_segments_and_turns_and_deletes_source(harness: Harness) -> None:
    status, body = harness.call(
        "POST", f"/api/speakers/{harness.ana.id}/merge", {"into": str(harness.beto.id)}
    )

    assert status == 200
    assert body == {
        "speaker": {
            "id": str(harness.beto.id),
            "name": "Speaker 2",
            "color": "#f28e2b",
            "segment_count": 3,
            "talk_ms": 750,
            "first_ms": 0,
        }
    }
    assert harness.speakers.get(harness.ana.id) is None
    assert {
        s.speaker_id for s in harness.segments.list_by_transcript(harness.transcript.id)
    } == {harness.beto.id}
    assert {
        t.speaker_id for t in harness.turns.list_by_transcript(harness.transcript.id)
    } == {harness.beto.id}
    # Text and revisions are untouched.
    assert harness.segments.get(harness.s1.id) == Segment(
        harness.transcript.id,
        0,
        250,
        "texto 0",
        id=harness.s1.id,
        speaker_id=harness.beto.id,
    )


@pytest.mark.parametrize("target", ["self", "other_transcript", "missing"])
def test_merge_invalid_is_409_and_changes_nothing(
    harness: Harness, target: str
) -> None:
    into: UUID = {
        "self": harness.ana.id,
        "other_transcript": harness.lejano.id,
        "missing": uuid4(),
    }[target]

    status, body = harness.call(
        "POST", f"/api/speakers/{harness.ana.id}/merge", {"into": str(into)}
    )

    assert (status, _code(body)) == (409, "speaker_merge_invalid")
    assert harness.speakers.get(harness.ana.id) == harness.ana
    assert harness.segments.get(harness.s1.id) == harness.s1


def test_merge_unknown_source_is_404(harness: Harness) -> None:
    status, body = harness.call(
        "POST", f"/api/speakers/{uuid4()}/merge", {"into": str(harness.ana.id)}
    )

    assert (status, _code(body)) == (404, "speaker_not_found")


def test_repository_merge_is_atomic_when_source_is_missing(harness: Harness) -> None:
    with pytest.raises(LookupError):
        harness.speakers.merge(uuid4(), harness.beto.id)

    assert harness.segments.get(harness.s3.id) == harness.s3


def test_assign_segment_speaker_changes_only_the_speaker(harness: Harness) -> None:
    status, body = harness.call(
        "PUT",
        f"/api/segments/{harness.s1.id}/speaker",
        {"speaker_id": str(harness.beto.id)},
    )

    assert status == 200
    assert body["speaker_id"] == str(harness.beto.id)
    assert (body["text"], body["edited"], body["revision"]) == ("texto 0", False, 0)
    stored = harness.segments.get(harness.s1.id)
    assert stored is not None and stored.speaker_id == harness.beto.id


def test_assign_null_clears_the_speaker(harness: Harness) -> None:
    status, body = harness.call(
        "PUT", f"/api/segments/{harness.s1.id}/speaker", {"speaker_id": None}
    )

    assert (status, body["speaker_id"]) == (200, None)


def test_assign_speaker_of_another_transcript_is_409(harness: Harness) -> None:
    status, body = harness.call(
        "PUT",
        f"/api/segments/{harness.s1.id}/speaker",
        {"speaker_id": str(harness.lejano.id)},
    )

    assert (status, _code(body)) == (409, "segment_speaker_invalid")
    assert harness.segments.get(harness.s1.id) == harness.s1


def test_assign_unknown_segment_or_speaker(harness: Harness) -> None:
    status, body = harness.call(
        "PUT", f"/api/segments/{uuid4()}/speaker", {"speaker_id": None}
    )
    assert (status, _code(body)) == (404, "segment_not_found")

    status, body = harness.call(
        "PUT", f"/api/segments/{harness.s1.id}/speaker", {"speaker_id": str(uuid4())}
    )
    assert (status, _code(body)) == (409, "segment_speaker_invalid")
