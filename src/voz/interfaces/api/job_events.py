"""Server-Sent Events adapter streaming transcription job snapshots.

The browser must read job state from the API, never infer it from logs. This
router polls the synchronous job repository off the event loop and pushes a
``job`` event whenever the persisted snapshot changes, then an ``end`` event
once the job reaches a terminal state.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

import anyio
import anyio.to_thread
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from voz.application.ports.repositories import TranscriptionJobRepository
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.interfaces.api.job_views import job_view

_KEEPALIVE = b": ping\n\n"
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _event(name: str, data: dict[str, object]) -> bytes:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {name}\ndata: {payload}\n\n".encode()


def _fingerprint(
    job: TranscriptionJob,
) -> tuple[TranscriptionJobState, float, datetime]:
    return (job.state, job.progress, job.updated_at)


def create_job_events_router(
    jobs: TranscriptionJobRepository,
    *,
    poll_interval_s: float = 0.5,
    keepalive_s: float = 15.0,
) -> APIRouter:
    """Expose ``GET /api/jobs/{job_id}/events`` as a ``text/event-stream``."""
    if poll_interval_s <= 0 or keepalive_s <= 0:
        raise ValueError("poll_interval_s and keepalive_s must be positive")
    keepalive_polls = max(1, round(keepalive_s / poll_interval_s))
    router = APIRouter(prefix="/api", tags=["jobs"])

    async def stream(request: Request, first: TranscriptionJob) -> AsyncIterator[bytes]:
        job = first
        yield _event("job", job_view(job))
        idle_polls = 0
        while not job.state.is_terminal:
            if await request.is_disconnected():
                return
            await anyio.sleep(poll_interval_s)
            current = await anyio.to_thread.run_sync(jobs.get, job.id)
            if current is None:
                break
            if _fingerprint(current) != _fingerprint(job):
                job = current
                idle_polls = 0
                yield _event("job", job_view(job))
                continue
            idle_polls += 1
            if idle_polls >= keepalive_polls:
                idle_polls = 0
                yield _KEEPALIVE
        yield _event("end", {})

    async def job_events(request: Request, job_id: UUID) -> StreamingResponse:
        job = await anyio.to_thread.run_sync(jobs.get, job_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "job_not_found",
                    "message": "The transcription job does not exist.",
                },
            )
        return StreamingResponse(
            stream(request, job),
            media_type="text/event-stream",
            headers=_STREAM_HEADERS,
        )

    router.add_api_route(
        "/jobs/{job_id}/events",
        job_events,
        methods=["GET"],
        response_class=StreamingResponse,
        summary="Stream job snapshots as Server-Sent Events",
    )
    return router


__all__ = ["create_job_events_router"]
