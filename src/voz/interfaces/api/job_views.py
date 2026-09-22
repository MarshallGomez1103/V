"""Transport projection of a transcription job snapshot.

Shared by the SSE stream and the REST job endpoints so both emit the same
browser-facing shape. Timestamps are ISO 8601 with their UTC offset; UUIDs are
canonical strings. No host paths ever leave through this view.
"""

from __future__ import annotations

from voz.domain.entities.transcription_job import TranscriptionJob


def job_view(job: TranscriptionJob) -> dict[str, object]:
    """Serialize one job snapshot to JSON-ready primitives."""
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "media_asset_id": str(job.media_asset_id),
        "state": job.state.value,
        "progress": job.progress,
        "error_code": job.error_code,
        # The domain entity does not link a transcript yet; the field is part of
        # the frontend contract so it is emitted as ``null`` until it exists.
        "transcript_id": None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


__all__ = ["job_view"]
