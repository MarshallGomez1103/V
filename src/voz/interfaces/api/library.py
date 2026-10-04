"""``GET /api/library``: one summary row per project for the Home screen."""

from __future__ import annotations

from fastapi import APIRouter

from voz.application.library import ListLibrary
from voz.application.ports.library import LibraryEntry


def library_view(entry: LibraryEntry) -> dict[str, object]:
    media = entry.media
    job = entry.latest_job
    return {
        "project_id": str(entry.project_id),
        "name": entry.name,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.activity_at.isoformat(),
        "media": None
        if media is None
        else {
            "media_asset_id": str(media.media_asset_id),
            "filename": media.filename,
            "media_type": media.media_type,
            "duration_ms": media.duration_ms,
        },
        "latest_job": None
        if job is None
        else {
            "id": str(job.id),
            "state": job.state.value,
            "transcript_id": None
            if job.transcript_id is None
            else str(job.transcript_id),
            "model_id": job.model_id,
            "progress": job.progress,
            "error_code": job.error_code,
            "created_at": job.created_at.isoformat(),
        },
        "speaker_count": entry.speaker_count,
        "segment_count": entry.segment_count,
    }


def create_library_router(list_library: ListLibrary) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["library"])

    def get_library() -> dict[str, object]:
        return {"items": [library_view(entry) for entry in list_library.execute()]}

    router.add_api_route("/library", get_library, methods=["GET"])
    return router


__all__ = ["create_library_router", "library_view"]
