"""Transport projection of a transcription job snapshot.

Shared by the SSE stream and the REST job endpoints so both emit the same
browser-facing shape. Timestamps are ISO 8601 with their UTC offset; UUIDs are
canonical strings. No host paths ever leave through this view.
"""

from __future__ import annotations

from datetime import UTC, datetime

from voz.domain.entities.transcription_job import TranscriptionJob

_MIN_ETA_BASIS = 0.02
"""Below this stage fraction the elapsed time says too little to extrapolate."""


def eta_seconds(job: TranscriptionJob, now: datetime | None = None) -> float | None:
    """Seconds left in the current stage, from its progress and elapsed time.

    ``None`` without a basis: the job is not running, the stage has no measure
    yet, or its clock is unknown. The estimate assumes a constant rate.
    """
    if (
        not job.state.is_processable
        or job.stage_progress is None
        or job.stage_started_at is None
    ):
        return None
    if job.stage_progress >= 1.0:
        return 0.0
    if job.stage_progress < _MIN_ETA_BASIS:
        return None
    elapsed = ((now or datetime.now(UTC)) - job.stage_started_at).total_seconds()
    if elapsed <= 0:
        return None
    return round(elapsed * (1.0 - job.stage_progress) / job.stage_progress, 1)


def timing_view(
    job: TranscriptionJob, now: datetime | None = None
) -> dict[str, object]:
    """Per-stage timing and progress fields shared by every job projection."""
    return {
        "started_at": None if job.started_at is None else job.started_at.isoformat(),
        "stage_started_at": (
            None if job.stage_started_at is None else job.stage_started_at.isoformat()
        ),
        "stage_progress": job.stage_progress,
        "eta_seconds": eta_seconds(job, now),
    }


def job_view(job: TranscriptionJob, now: datetime | None = None) -> dict[str, object]:
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
        **timing_view(job, now),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


__all__ = ["eta_seconds", "job_view", "timing_view"]
