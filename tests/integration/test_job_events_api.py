"""SSE job stream tested through ASGI with a mutable in-memory job repository."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from starlette.types import Message

from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.interfaces.api.job_events import create_job_events_router

JOB_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
MEDIA_ASSET_ID = UUID("33333333-3333-4333-8333-333333333333")
STARTED_AT = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def queued_job() -> TranscriptionJob:
    return TranscriptionJob(
        id=JOB_ID,
        project_id=PROJECT_ID,
        media_asset_id=MEDIA_ASSET_ID,
        state=TranscriptionJobState.QUEUED,
        progress=0.0,
        created_at=STARTED_AT,
        updated_at=STARTED_AT,
    )


def advance(job: TranscriptionJob, *targets: TranscriptionJobState) -> TranscriptionJob:
    for step, target in enumerate(targets, start=1):
        job = job.transition_to(target, at=job.updated_at + timedelta(seconds=step))
    return job


class FakeJobs:
    """Repository fake replaying a scripted sequence of snapshots per ``get``.

    The last snapshot repeats forever, which models a job left unchanged in the
    database. Mutation happens only through this timeline so tests stay
    deterministic regardless of wall-clock timing.
    """

    def __init__(self, *timeline: TranscriptionJob) -> None:
        self._timeline = list(timeline)
        self.gets = 0

    def add(self, job: TranscriptionJob) -> None:
        self._timeline.append(job)

    def save(self, job: TranscriptionJob) -> None:
        self._timeline.append(job)

    def get(self, job_id: UUID) -> TranscriptionJob | None:
        self.gets += 1
        if not self._timeline or self._timeline[0].id != job_id:
            return None
        if len(self._timeline) > 1:
            return self._timeline.pop(0)
        return self._timeline[0]

    def list_by_project(self, project_id: UUID) -> Sequence[TranscriptionJob]:
        return ()

    def list_by_media_asset(self, media_asset_id: UUID) -> Sequence[TranscriptionJob]:
        return ()

    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        return ()


def build_app(jobs: FakeJobs, **options: float) -> FastAPI:
    app = FastAPI()
    app.include_router(create_job_events_router(jobs, poll_interval_s=0.01, **options))
    return app


async def request(
    app: FastAPI,
    path: str,
    *,
    disconnect_after_chunks: int | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Drive one ASGI request, collecting streamed body chunks until completion."""
    messages: list[Message] = []
    body_chunks = 0
    disconnected = False

    async def receive() -> Message:
        if disconnected:
            return {"type": "http.disconnect"}
        if not messages:
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # a live client sends nothing more
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        nonlocal body_chunks, disconnected
        messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            body_chunks += 1
            if disconnect_after_chunks is not None:
                disconnected = body_chunks >= disconnect_after_chunks

    await asyncio.wait_for(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 1234),
                "root_path": "",
            },
            receive,
            send,
        ),
        timeout=5,
    )
    start = messages[0]
    headers = {
        key.decode().lower(): value.decode()
        for key, value in cast(list[tuple[bytes, bytes]], start["headers"])
    }
    body = b"".join(
        cast(bytes, message.get("body", b""))
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), headers, body


def parse_sse(body: bytes) -> list[tuple[str, object]]:
    """Return ``(event, data)`` pairs; comments become ``("comment", text)``."""
    events: list[tuple[str, object]] = []
    for block in body.decode().split("\n\n"):
        if not block:
            continue
        if block.startswith(":"):
            events.append(("comment", block[1:].strip()))
            continue
        fields = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_unknown_job_is_rejected_before_the_stream_opens() -> None:
    status, headers, body = asyncio.run(
        request(build_app(FakeJobs()), f"/api/jobs/{JOB_ID}/events")
    )
    assert status == 404
    assert headers["content-type"].startswith("application/json")
    assert json.loads(body) == {
        "detail": {
            "code": "job_not_found",
            "message": "The transcription job does not exist.",
        }
    }


def test_stream_emits_each_change_and_ends_on_terminal_state() -> None:
    queued = queued_job()
    transcribing = advance(
        queued,
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
    )
    halfway = transcribing.with_progress(
        0.5, at=transcribing.updated_at + timedelta(seconds=1)
    )
    completed = advance(
        halfway,
        TranscriptionJobState.ALIGNING,
        TranscriptionJobState.DIARIZING,
        TranscriptionJobState.MERGING,
        TranscriptionJobState.PERSISTING,
        TranscriptionJobState.COMPLETED,
    )
    jobs = FakeJobs(queued, queued, transcribing, halfway, halfway, completed)

    status, headers, body = asyncio.run(
        request(build_app(jobs), f"/api/jobs/{JOB_ID}/events")
    )

    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"
    events = parse_sse(body)
    assert [name for name, _ in events] == ["job", "job", "job", "job", "end"]
    views = [cast(dict[str, object], data) for name, data in events if name == "job"]
    assert [(view["state"], view["progress"]) for view in views] == [
        ("QUEUED", 0.0),
        ("TRANSCRIBING", 0.0),
        ("TRANSCRIBING", 0.5),
        ("COMPLETED", 1.0),
    ]
    assert views[0] == {
        "id": str(JOB_ID),
        "project_id": str(PROJECT_ID),
        "media_asset_id": str(MEDIA_ASSET_ID),
        "state": "QUEUED",
        "progress": 0.0,
        "error_code": None,
        "transcript_id": None,
        "created_at": "2026-09-21T12:00:00+00:00",
        "updated_at": "2026-09-21T12:00:00+00:00",
    }
    assert views[-1]["updated_at"] == completed.updated_at.isoformat()
    assert events[-1] == ("end", {})


def test_failed_job_carries_its_error_code_then_ends() -> None:
    queued = queued_job()
    failed = queued.transition_to(
        TranscriptionJobState.FAILED,
        at=STARTED_AT + timedelta(seconds=1),
        error_code="asr_provider_unavailable",
    )
    _, _, body = asyncio.run(
        request(build_app(FakeJobs(queued, failed)), f"/api/jobs/{JOB_ID}/events")
    )
    events = parse_sse(body)
    assert [name for name, _ in events] == ["job", "job", "end"]
    assert cast(dict[str, object], events[1][1])["error_code"] == (
        "asr_provider_unavailable"
    )


def test_terminal_job_ends_immediately_without_polling() -> None:
    completed = advance(
        queued_job(),
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
        TranscriptionJobState.ALIGNING,
        TranscriptionJobState.DIARIZING,
        TranscriptionJobState.MERGING,
        TranscriptionJobState.PERSISTING,
        TranscriptionJobState.COMPLETED,
    )
    jobs = FakeJobs(completed)
    _, _, body = asyncio.run(request(build_app(jobs), f"/api/jobs/{JOB_ID}/events"))
    assert [name for name, _ in parse_sse(body)] == ["job", "end"]
    assert jobs.gets == 1


def test_unchanged_snapshots_produce_keepalive_comments_not_events() -> None:
    queued = queued_job()
    completed = advance(
        queued,
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
        TranscriptionJobState.ALIGNING,
        TranscriptionJobState.DIARIZING,
        TranscriptionJobState.MERGING,
        TranscriptionJobState.PERSISTING,
        TranscriptionJobState.COMPLETED,
    )
    # Five unchanged polls with a keepalive every two polls -> exactly two pings.
    jobs = FakeJobs(queued, queued, queued, queued, queued, queued, completed)
    _, _, body = asyncio.run(
        request(build_app(jobs, keepalive_s=0.02), f"/api/jobs/{JOB_ID}/events")
    )
    events = parse_sse(body)
    assert events == [
        ("job", events[0][1]),
        ("comment", "ping"),
        ("comment", "ping"),
        ("job", events[3][1]),
        ("end", {}),
    ]
    assert cast(dict[str, object], events[0][1])["state"] == "QUEUED"
    assert cast(dict[str, object], events[3][1])["state"] == "COMPLETED"


def test_client_disconnect_stops_the_stream_cleanly() -> None:
    jobs = FakeJobs(queued_job())  # never reaches a terminal state
    status, _, body = asyncio.run(
        request(
            build_app(jobs), f"/api/jobs/{JOB_ID}/events", disconnect_after_chunks=1
        )
    )
    assert status == 200
    assert [name for name, _ in parse_sse(body)] == ["job"]
    assert jobs.gets <= 2
