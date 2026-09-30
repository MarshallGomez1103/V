"""Thin HTTP adapter for transcription jobs, cancellation and transcript segments."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, HTTPException

from voz.application.create_transcription_job import (
    CreateJobError,
    CreateJobFailureCode,
    CreateTranscriptionJob,
)
from voz.application.job_runner import (
    JobNotFound,
    JobRunner,
    JobTerminal,
    transcript_id_for,
)
from voz.application.ports.repositories import (
    SegmentRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.interfaces.api.segments import segment_view

_CREATE_STATUS: dict[CreateJobFailureCode, int] = {
    CreateJobFailureCode.PROJECT_NOT_FOUND: 404,
    CreateJobFailureCode.MEDIA_ASSET_NOT_FOUND: 404,
    CreateJobFailureCode.OPTION_UNKNOWN: 404,
    CreateJobFailureCode.OPTION_NOT_STARTABLE: 409,
    CreateJobFailureCode.JOB_ALREADY_ACTIVE: 409,
}


@dataclass(frozen=True, slots=True)
class CreateJobRequest:
    project_id: UUID
    media_asset_id: UUID
    option_id: str
    language: str | None = None


def _error(status_code: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
    )


def selection_view(selection: JobSelection) -> dict[str, object]:
    """Same profile/execution JSON shape as ``/api/transcription-options``."""
    model = selection.model
    profile = model.profile
    execution = selection.execution
    return {
        "option_id": selection.option_id,
        "provider_id": model.provider_id,
        "model_id": model.model_id,
        "source": model.source,
        "revision": model.revision,
        "profile": None
        if profile is None
        else {
            "name": profile.name.value,
            "device_preference": profile.device_preference.value,
            "gpu_precisions": [item.value for item in profile.gpu_precisions],
            "cpu_precision": profile.cpu_precision.value,
        },
        "execution": None
        if execution is None
        else {
            "device": execution.device.value,
            "precision": execution.precision.value,
            "fallback_reason": (
                None
                if execution.fallback_reason is None
                else execution.fallback_reason.value
            ),
        },
        "language": selection.language,
    }


def job_view(job: TranscriptionJob, selection: JobSelection) -> dict[str, object]:
    """Path-free job projection consumed by the browser."""
    completed = job.state is TranscriptionJobState.COMPLETED
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "media_asset_id": str(job.media_asset_id),
        "state": job.state.value,
        "progress": job.progress,
        "error_code": job.error_code,
        "transcript_id": str(transcript_id_for(job.id)) if completed else None,
        "selection": selection_view(selection),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def create_jobs_router(
    create_job: CreateTranscriptionJob,
    jobs_repo: TranscriptionJobRepository,
    selections_repo: TranscriptionJobSelectionRepository,
    transcripts_repo: TranscriptRepository,
    segments_repo: SegmentRepository,
    runner: JobRunner,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["jobs"])

    def view(job: TranscriptionJob) -> dict[str, object]:
        selection = selections_repo.get(job.id)
        if selection is None:
            raise _error(
                500, "job_selection_missing", "The job has no persisted selection."
            )
        return job_view(job, selection)

    def require_job(job_id: UUID) -> TranscriptionJob:
        job = jobs_repo.get(job_id)
        if job is None:
            raise _error(404, "job_not_found", "The job does not exist.")
        return job

    def post_job(request: CreateJobRequest) -> dict[str, object]:
        try:
            created = create_job.execute(
                project_id=request.project_id,
                media_asset_id=request.media_asset_id,
                option_id=request.option_id,
                language=request.language,
            )
        except CreateJobError as error:
            extra: dict[str, object] = {}
            if error.code is CreateJobFailureCode.OPTION_NOT_STARTABLE:
                extra["blocking_reasons"] = [
                    reason.value for reason in error.blocking_reasons
                ]
            raise _error(
                _CREATE_STATUS[error.code],
                error.code.value,
                error.user_message,
                **extra,
            ) from None
        runner.enqueue(created.job.id)
        return job_view(created.job, created.selection)

    def get_job(job_id: UUID) -> dict[str, object]:
        return view(require_job(job_id))

    def list_jobs(project_id: UUID) -> dict[str, object]:
        jobs = sorted(
            jobs_repo.list_by_project(project_id),
            key=lambda job: (job.created_at, str(job.id)),
            reverse=True,
        )
        return {"jobs": [view(job) for job in jobs]}

    def cancel_job(job_id: UUID) -> dict[str, object]:
        try:
            return view(runner.cancel(job_id))
        except JobNotFound:
            raise _error(404, "job_not_found", "The job does not exist.") from None
        except JobTerminal:
            raise _error(409, "job_terminal", "The job already finished.") from None

    def list_segments(transcript_id: UUID) -> dict[str, object]:
        if transcripts_repo.get(transcript_id) is None:
            raise _error(404, "transcript_not_found", "The transcript does not exist.")
        return {
            "segments": [
                segment_view(segment)
                for segment in segments_repo.list_by_transcript(transcript_id)
            ]
        }

    router.add_api_route("/jobs", post_job, methods=["POST"], status_code=201)
    router.add_api_route("/jobs", list_jobs, methods=["GET"])
    router.add_api_route("/jobs/{job_id}", get_job, methods=["GET"])
    router.add_api_route(
        "/jobs/{job_id}/cancel", cancel_job, methods=["POST"], status_code=202
    )
    router.add_api_route(
        "/transcripts/{transcript_id}/segments", list_segments, methods=["GET"]
    )
    return router


__all__ = ["CreateJobRequest", "create_jobs_router", "job_view", "selection_view"]
