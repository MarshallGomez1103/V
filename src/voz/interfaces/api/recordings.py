"""``GET /api/projects/{project_id}/recordings``: the recordings of one project."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from voz.application.list_recordings import ListRecordings, Recording
from voz.application.project_glossary import ProjectNotFound
from voz.interfaces.api.errors import api_error


def recording_view(recording: Recording) -> dict[str, object]:
    job = recording.latest_job
    return {
        "media_asset_id": str(recording.media_asset_id),
        "filename": recording.filename,
        "media_type": recording.media_type,
        "duration_ms": recording.duration_ms,
        "created_at": recording.created_at.isoformat(),
        "latest_job": None
        if job is None
        else {
            "id": str(job.id),
            "state": job.state.value,
            "transcript_id": None
            if job.transcript_id is None
            else str(job.transcript_id),
            "model_id": job.model_id,
            "created_at": job.created_at.isoformat(),
        },
    }


def create_recordings_router(list_recordings: ListRecordings) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["recordings"])

    def get_recordings(project_id: UUID) -> dict[str, object]:
        try:
            recordings = list_recordings.execute(project_id)
        except ProjectNotFound:
            raise api_error(
                404, "project_not_found", "The project does not exist."
            ) from None
        return {"recordings": [recording_view(item) for item in recordings]}

    router.add_api_route(
        "/projects/{project_id}/recordings", get_recordings, methods=["GET"]
    )
    return router


__all__ = ["create_recordings_router", "recording_view"]
