"""HTTP adapter for speech synthesis jobs (V3-05, ADR-0010).

Options, create (or reuse), status, SSE progress, cancel, audio with ``Range``,
history and delete. Use cases and the runner do the work; this module only
translates JSON and stable error codes. Host paths never leave the server:
audio is addressed by job id and opened through the storage port.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from typing import BinaryIO, Final, Protocol
from uuid import UUID

import anyio
import anyio.to_thread
from fastapi import APIRouter, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictBool
from starlette.responses import JSONResponse, Response, StreamingResponse

from voz.application.ports.speech_synthesis import SynthesisError
from voz.application.ports.synthesis_audio_storage import (
    SynthesisAudioStorage,
    SynthesisStorageError,
    SynthesisStorageErrorCode,
)
from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.application.ports.transcription_options import InstallationStatus
from voz.application.synthesis import (
    CreateSynthesisJob,
    DeleteSynthesisResult,
    ListSynthesisHistory,
    SynthesisJobError,
    SynthesisJobFailureCode,
    SynthesisModelCatalog,
)
from voz.application.synthesis.list_synthesis_history import DEFAULT_HISTORY_LIMIT
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import (
    MAX_SYNTHESIS_SPEED,
    MAX_SYNTHESIS_TEXT_CHARS,
    MIN_SYNTHESIS_SPEED,
)
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.interfaces.api.errors import api_error

ACTION_HEADER: Final = "X-VOZ-Action"
DELETE_ACTION: Final = "delete-synthesis"
TEXT_PREVIEW_CHARS: Final = 160
_READ_BLOCK: Final = 64 * 1024
_KEEPALIVE: Final = b": ping\n\n"
_STREAM_HEADERS: Final = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_AUDIO_HEADERS: Final = {
    "Cache-Control": "private, max-age=3600",
    "Accept-Ranges": "bytes",
    "X-Content-Type-Options": "nosniff",
}
_RANGE: Final = re.compile(r"bytes=(\d*)-(\d*)", re.ASCII)
_UNSAFE_NAME: Final = re.compile(r"[^A-Za-z0-9_-]+", re.ASCII)

_Code = SynthesisJobFailureCode
_STATUS: Final[dict[SynthesisJobFailureCode, int]] = {
    _Code.PROVIDER_NOT_FOUND: 404,
    _Code.MODEL_UNKNOWN: 404,
    _Code.VOICE_NOT_FOUND: 404,
    _Code.MODEL_NOT_INSTALLED: 409,
    _Code.RUNTIME_UNAVAILABLE: 409,
    _Code.REQUEST_INVALID: 422,
    _Code.JOB_NOT_FOUND: 404,
    _Code.JOB_TERMINAL: 409,
    _Code.JOB_ACTIVE: 409,
    _Code.CLOUD_CONSENT_REQUIRED: 422,
}


class SynthesisQueue(Protocol):
    """What the router needs from ``SynthesisRunner``."""

    def enqueue(self, job_id: UUID) -> None: ...

    def cancel(self, job_id: UUID) -> SynthesisJob: ...


class CreateSynthesisBody(BaseModel):
    text: str = Field(max_length=2 * MAX_SYNTHESIS_TEXT_CHARS)
    """Coarse body cap; the use case enforces the real limit with a typed error."""
    provider_id: str
    model_id: str
    voice_id: str
    language: str | None = None
    speed: float = 1.0
    cloud_consent: StrictBool = False
    """Explicit consent to send the text to a cloud engine; local engines ignore it."""


def _job_error(error: SynthesisJobError) -> Exception:
    return api_error(_STATUS[error.code], error.code.value, error.user_message)


def _not_found() -> Exception:
    return api_error(
        404, _Code.JOB_NOT_FOUND.value, "The synthesis job does not exist."
    )


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def synthesis_view(
    job: SynthesisJob, audio: SynthesizedAudio | None, *, full_text: bool = False
) -> dict[str, object]:
    """Browser projection of a job; never carries the stored file path."""
    request = job.request
    view: dict[str, object] = {
        "id": str(job.id),
        "state": job.state.value,
        "progress": job.progress,
        "chunks_done": job.chunks_done,
        "chunks_total": job.chunks_total,
        "error_code": job.error_code,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "started_at": _iso(job.started_at),
        "provider_id": request.provider_id,
        "model_id": request.model_id,
        "voice_id": request.voice_id,
        "language": request.language,
        "speed": request.speed,
        "text_length": len(request.text),
        "text_preview": request.text[:TEXT_PREVIEW_CHARS],
        "audio": None
        if audio is None
        else {
            "duration_ms": audio.duration_ms,
            "sample_rate": audio.sample_rate,
            "size_bytes": audio.size_bytes,
            "url": f"/api/synthesis/{job.id}/audio",
        },
    }
    if full_text:
        view["text"] = request.text
    return view


def download_name(job: SynthesisJob) -> str:
    """``v-<date>-<voice>.wav`` with only ASCII letters, digits, ``-`` and ``_``."""
    voice = _UNSAFE_NAME.sub("-", job.request.voice_id).strip("-")[:40] or "voice"
    return f"v-{job.created_at.date().isoformat()}-{voice}.wav"


def _byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Inclusive ``(start, end)`` of a single satisfiable range, else ``None``.

    Raises ``ValueError`` when the range is well formed but unsatisfiable.
    Malformed or multi-range headers are ignored (full body), as RFC 9110 allows.
    """
    match = _RANGE.fullmatch((header or "").strip())
    if match is None or match.group(1) == match.group(2) == "":
        return None
    first, last = match.groups()
    if first == "":  # suffix: the last N bytes
        length = int(last)
        if length == 0 or size == 0:
            raise ValueError("unsatisfiable range")
        return max(0, size - length), size - 1
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if start >= size or start > end:
        raise ValueError("unsatisfiable range")
    return start, end


def _read_span(stream: BinaryIO, start: int, end: int) -> Iterator[bytes]:
    with stream:
        stream.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            block = stream.read(min(_READ_BLOCK, remaining))
            if not block:
                return
            remaining -= len(block)
            yield block


def _sse(name: str, data: dict[str, object]) -> bytes:
    # ponytail: same frame as job_events._event; two copies, not a shared module.
    return (
        f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()
    )


def create_synthesis_router(
    *,
    providers: SynthesisProviderRegistry,
    catalog: SynthesisModelCatalog,
    create: CreateSynthesisJob,
    history: ListSynthesisHistory,
    delete: DeleteSynthesisResult,
    jobs: SynthesisJobRepository,
    audio: SynthesizedAudioRepository,
    storage: SynthesisAudioStorage,
    runner: SynthesisQueue,
    poll_interval_s: float = 0.25,
    keepalive_s: float = 15.0,
) -> APIRouter:
    """Expose ``/api/synthesis`` (see ``docs/api/synthesis.md``)."""
    if poll_interval_s <= 0 or keepalive_s <= 0:
        raise ValueError("poll_interval_s and keepalive_s must be positive")
    keepalive_polls = max(1, round(keepalive_s / poll_interval_s))
    router = APIRouter(prefix="/api", tags=["synthesis"])

    def view_of(job: SynthesisJob, *, full_text: bool = False) -> dict[str, object]:
        stored = (
            audio.get_by_job(job.id)
            if job.state is SynthesisJobState.COMPLETED
            else None
        )
        return synthesis_view(job, stored, full_text=full_text)

    def get_job(job_id: UUID) -> SynthesisJob:
        job = jobs.get(job_id)
        if job is None:
            raise _not_found()
        return job

    def options() -> dict[str, object]:
        registered = {
            provider.describe().provider_id: provider
            for provider in providers.list_all()
        }
        models: list[dict[str, object]] = []
        for item in catalog.list_models():
            model = item.descriptor
            provider = registered.get(model.provider_id)
            if (
                provider is None
                or not model.supports(ModelCapability.SYNTHESIS)
                or item.installation_status is not InstallationStatus.REGISTERED
                or not item.files_available
            ):
                continue
            try:
                ready = provider.requirements(model).runtime_ready
                voices = provider.voices(model)
                languages = provider.languages(model)
            except SynthesisError:
                continue  # broken install: the Model Manager shows why
            models.append(
                {
                    "provider_id": model.provider_id,
                    "model_id": model.model_id,
                    "display_name": model.display_name,
                    "runtime_ready": ready,
                    "capabilities": sorted(cap.value for cap in model.capabilities),
                    "languages": list(languages),
                    "voices": [
                        {
                            "id": voice.id,
                            "name": voice.name,
                            "languages": list(voice.languages),
                        }
                        for voice in voices
                    ],
                }
            )
        return {
            "providers": [
                {
                    "provider_id": info.provider_id,
                    "display_name": info.display_name,
                    "locality": info.locality.value,
                }
                for info in (provider.describe() for provider in registered.values())
            ],
            "models": models,
            "max_chars": MAX_SYNTHESIS_TEXT_CHARS,
            "speed": {"min": MIN_SYNTHESIS_SPEED, "max": MAX_SYNTHESIS_SPEED},
        }

    async def get_options() -> dict[str, object]:
        return await run_in_threadpool(options)

    def post(body: CreateSynthesisBody) -> JSONResponse:
        try:
            created = create.execute(
                text=body.text,
                provider_id=body.provider_id,
                model_id=body.model_id,
                voice_id=body.voice_id,
                language=body.language,
                speed=body.speed,
                cloud_consent=body.cloud_consent,
            )
        except SynthesisJobError as error:
            raise _job_error(error) from None
        if created.audio is None:  # new, or identical job still in progress
            runner.enqueue(created.job.id)
        view = synthesis_view(created.job, created.audio)
        view["reused"] = created.reused
        return JSONResponse(view, status_code=200 if created.reused else 201)

    async def post_synthesis(body: CreateSynthesisBody) -> JSONResponse:
        return await run_in_threadpool(post, body)

    async def get_synthesis(job_id: UUID) -> dict[str, object]:
        job = await run_in_threadpool(get_job, job_id)
        return await run_in_threadpool(lambda: view_of(job, full_text=True))

    async def list_synthesis(
        limit: int = Query(default=DEFAULT_HISTORY_LIMIT),
    ) -> dict[str, object]:
        items = await run_in_threadpool(history.execute, limit)
        return {"items": [synthesis_view(item.job, item.audio) for item in items]}

    def cancel(job_id: UUID) -> dict[str, object]:
        try:
            return view_of(runner.cancel(job_id))
        except SynthesisJobError as error:
            raise _job_error(error) from None

    async def cancel_synthesis(job_id: UUID) -> dict[str, object]:
        return await run_in_threadpool(cancel, job_id)

    def remove(job_id: UUID) -> None:
        try:
            delete.execute(job_id)
        except SynthesisJobError as error:
            raise _job_error(error) from None
        except SynthesisStorageError:
            raise api_error(
                500, "synthesis_delete_failed", "The audio could not be deleted."
            ) from None

    async def delete_synthesis(
        job_id: UUID,
        action: str | None = Header(default=None, alias=ACTION_HEADER),
    ) -> Response:
        if action != DELETE_ACTION:
            raise api_error(
                403,
                "synthesis_delete_forbidden",
                f"Send the header {ACTION_HEADER}: {DELETE_ACTION}.",
            )
        await run_in_threadpool(remove, job_id)
        return Response(status_code=204)

    def open_audio(job_id: UUID) -> tuple[SynthesisJob, BinaryIO, int]:
        job = get_job(job_id)
        stored = (
            audio.get_by_job(job_id)
            if job.state is SynthesisJobState.COMPLETED
            else None
        )
        if stored is None:
            raise api_error(
                409, "synthesis_audio_not_ready", "The audio is not ready yet."
            )
        try:
            stream = storage.open_for_reading(stored.relative_path)
        except SynthesisStorageError as error:
            if error.code is SynthesisStorageErrorCode.AUDIO_NOT_FOUND:
                raise api_error(
                    404, "synthesis_audio_missing", "The audio file is not available."
                ) from None
            raise api_error(
                500, "synthesis_audio_unreadable", "The audio could not be opened."
            ) from None
        return job, stream, os.fstat(stream.fileno()).st_size

    async def get_audio(
        job_id: UUID,
        range_header: str | None = Header(default=None, alias="Range"),
        download: bool = False,
    ) -> Response:
        job, stream, size = await run_in_threadpool(open_audio, job_id)
        kind = "attachment" if download else "inline"
        headers = {
            **_AUDIO_HEADERS,
            "Content-Disposition": f'{kind}; filename="{download_name(job)}"',
        }
        try:
            span = _byte_range(range_header, size)
        except ValueError:
            stream.close()
            return Response(
                status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"}
            )
        start, end, status = (0, size - 1, 200) if span is None else (*span, 206)
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            _read_span(stream, start, end),
            status_code=status,
            media_type="audio/wav",
            headers=headers,
        )

    async def stream(request: Request, first: SynthesisJob) -> AsyncIterator[bytes]:
        job = first
        yield _sse("job", await anyio.to_thread.run_sync(view_of, job))
        idle_polls = 0
        while not job.state.is_terminal:
            if await request.is_disconnected():
                return
            await anyio.sleep(poll_interval_s)
            current = await anyio.to_thread.run_sync(jobs.get, job.id)
            if current is None:
                break
            if (current.state, current.chunks_done, current.updated_at) != (
                job.state,
                job.chunks_done,
                job.updated_at,
            ):
                job = current
                idle_polls = 0
                yield _sse("job", await anyio.to_thread.run_sync(view_of, job))
                continue
            idle_polls += 1
            if idle_polls >= keepalive_polls:
                idle_polls = 0
                yield _KEEPALIVE
        yield _sse("end", {})

    async def synthesis_events(request: Request, job_id: UUID) -> StreamingResponse:
        job = await run_in_threadpool(get_job, job_id)
        return StreamingResponse(
            stream(request, job),
            media_type="text/event-stream",
            headers=_STREAM_HEADERS,
        )

    # ``options`` before ``{job_id}`` so the literal path wins.
    router.add_api_route("/synthesis/options", get_options, methods=["GET"])
    router.add_api_route(
        "/synthesis", post_synthesis, methods=["POST"], status_code=201
    )
    router.add_api_route("/synthesis", list_synthesis, methods=["GET"])
    router.add_api_route("/synthesis/{job_id}", get_synthesis, methods=["GET"])
    router.add_api_route(
        "/synthesis/{job_id}", delete_synthesis, methods=["DELETE"], status_code=204
    )
    router.add_api_route(
        "/synthesis/{job_id}/cancel",
        cancel_synthesis,
        methods=["POST"],
        status_code=202,
    )
    router.add_api_route(
        "/synthesis/{job_id}/audio",
        get_audio,
        methods=["GET"],
        response_class=StreamingResponse,
    )
    router.add_api_route(
        "/synthesis/{job_id}/events",
        synthesis_events,
        methods=["GET"],
        response_class=StreamingResponse,
        summary="Stream synthesis job snapshots as Server-Sent Events",
    )
    return router


__all__ = ["create_synthesis_router", "download_name", "synthesis_view"]
