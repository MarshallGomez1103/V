"""Transcribe a whole project: create, read and cancel its queue."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, HTTPException

from voz.application.create_transcription_job import CreateJobError
from voz.application.job_runner import JobRunner
from voz.application.transcription_queue import (
    CancelTranscriptionQueue,
    CreateTranscriptionQueue,
    GetTranscriptionQueue,
    QueueError,
    QueueFailureCode,
    QueueSnapshot,
    SkippedItem,
)
from voz.interfaces.api.errors import api_error
from voz.interfaces.api.jobs import create_job_http_error, parse_diarization

_QUEUE_STATUS: dict[QueueFailureCode, int] = {
    QueueFailureCode.ACTIVE: 409,
    QueueFailureCode.EMPTY: 409,
    QueueFailureCode.CLOUD_UNSUPPORTED: 422,
    QueueFailureCode.NOT_FOUND: 404,
    QueueFailureCode.FINISHED: 409,
    QueueFailureCode.PROJECT_NOT_FOUND: 404,
}


@dataclass(frozen=True, slots=True)
class CreateQueueRequest:
    option_id: str
    language: str | None = None
    diarization: object = None
    """``{"enabled": bool, "speakers": {...}}``, as in ``POST /api/jobs``."""
    profile: str | None = None
    prompt: str | None = None


def skipped_view(item: SkippedItem) -> dict[str, object]:
    return {
        "media_asset_id": str(item.media_asset_id),
        "filename": item.filename,
        "reason": item.reason.value,
    }


def queue_view(snapshot: QueueSnapshot) -> dict[str, object]:
    """Path-free projection of a queue; every field is derived from its jobs."""
    queue = snapshot.queue
    counts = snapshot.counts
    return {
        "id": str(queue.id),
        "project_id": str(queue.project_id),
        "created_at": queue.created_at.isoformat(),
        "state": snapshot.state.value,
        "progress": snapshot.progress,
        "counts": {
            "total": counts.total,
            "pending": counts.pending,
            "running": counts.running,
            "done": counts.done,
            "error": counts.error,
            "cancelled": counts.cancelled,
            "skipped": counts.skipped,
        },
        "items": [
            {
                "position": item.position,
                "media_asset_id": str(item.media_asset_id),
                "filename": item.filename,
                "job_id": str(item.job.id),
                "status": item.status.value,
                "job_state": item.job.state.value,
                "progress": item.job.progress,
                "error_code": item.job.error_code,
                "transcript_id": None
                if item.transcript_id is None
                else str(item.transcript_id),
            }
            for item in snapshot.items
        ],
        "skipped": [skipped_view(item) for item in snapshot.skipped],
    }


def _queue_http_error(error: QueueError) -> HTTPException:
    extra: dict[str, object] = {}
    if error.code is QueueFailureCode.EMPTY:
        extra["skipped"] = [skipped_view(item) for item in error.skipped]
    return api_error(
        _QUEUE_STATUS[error.code], error.code.value, error.user_message, **extra
    )


def create_transcription_queue_router(
    create: CreateTranscriptionQueue,
    get: GetTranscriptionQueue,
    cancel: CancelTranscriptionQueue,
    runner: JobRunner,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["transcription-queue"])

    def post_queue(project_id: UUID, request: CreateQueueRequest) -> dict[str, object]:
        diarization = parse_diarization(request.diarization)
        try:
            created = create.execute(
                project_id=project_id,
                option_id=request.option_id,
                language=request.language,
                diarization=diarization,
                profile=request.profile,
                prompt=request.prompt,
            )
        except CreateJobError as error:
            raise create_job_http_error(error) from None
        except QueueError as error:
            raise _queue_http_error(error) from None
        # Enqueue before reading the snapshot: the jobs are already committed, so a
        # failed read must not leave them QUEUED with nobody to run them.
        for job_id in created.job_ids:
            runner.enqueue(job_id)
        try:
            return queue_view(get.by_id(created.queue_id))
        except QueueError as error:
            raise _queue_http_error(error) from None

    def get_queue(project_id: UUID) -> dict[str, object]:
        try:
            snapshot = get.for_project(project_id)
        except QueueError as error:
            raise _queue_http_error(error) from None
        return {"queue": None if snapshot is None else queue_view(snapshot)}

    def cancel_queue(queue_id: UUID) -> dict[str, object]:
        try:
            cancel.execute(queue_id)
            return queue_view(get.by_id(queue_id))
        except QueueError as error:
            raise _queue_http_error(error) from None

    router.add_api_route(
        "/projects/{project_id}/transcription-queue",
        post_queue,
        methods=["POST"],
        status_code=201,
    )
    router.add_api_route(
        "/projects/{project_id}/transcription-queue", get_queue, methods=["GET"]
    )
    router.add_api_route(
        "/transcription-queues/{queue_id}/cancel",
        cancel_queue,
        methods=["POST"],
        status_code=202,
    )
    return router


__all__ = ["create_transcription_queue_router", "queue_view"]
