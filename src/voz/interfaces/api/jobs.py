"""Thin HTTP adapter for transcription jobs, cancellation and transcript segments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

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
from voz.application.ports.diarization import DiarizationOptions, SpeakerCountHint
from voz.application.ports.repositories import (
    SegmentRepository,
    SpeakerTurnRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
)
from voz.application.ports.transcription_checkpoint import (
    TranscriptionCheckpointStore,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.application.rediarize import (
    RediarizeError,
    RediarizeFailureCode,
    RediarizeTranscript,
)
from voz.application.word_speakers import SpeakerTimeline
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.interfaces.api.errors import api_error
from voz.interfaces.api.job_views import timing_view
from voz.interfaces.api.segments import segment_view

_CREATE_STATUS: dict[CreateJobFailureCode, int] = {
    CreateJobFailureCode.PROJECT_NOT_FOUND: 404,
    CreateJobFailureCode.MEDIA_ASSET_NOT_FOUND: 404,
    CreateJobFailureCode.OPTION_UNKNOWN: 404,
    CreateJobFailureCode.OPTION_NOT_STARTABLE: 409,
    CreateJobFailureCode.JOB_ALREADY_ACTIVE: 409,
    CreateJobFailureCode.INSUFFICIENT_VRAM: 409,
    CreateJobFailureCode.INSUFFICIENT_RAM: 409,
    CreateJobFailureCode.DIARIZATION_UNAVAILABLE: 409,
    CreateJobFailureCode.DIARIZATION_MODELS_MISSING: 409,
    CreateJobFailureCode.PROMPT_INVALID: 422,
    CreateJobFailureCode.QUALITY_PROFILE_UNKNOWN: 422,
}

MAX_DIARIZATION_SPEAKERS = 32
_SPEAKER_KEYS = ("exact", "minimum", "maximum")


@dataclass(frozen=True, slots=True)
class CreateJobRequest:
    project_id: UUID
    media_asset_id: UUID
    option_id: str
    language: str | None = None
    diarization: object = None
    """``{"enabled": bool, "speakers": {"exact"?, "minimum"?, "maximum"?}}``."""
    profile: str | None = None
    """Quality profile name (S13.02); ``None`` means ``default``."""
    prompt: str | None = None
    """Style instruction for the ASR engine; at most 600 characters once stripped."""


@dataclass(frozen=True, slots=True)
class RediarizeRequest:
    speakers: object = None
    """``{"exact"?, "minimum"?, "maximum"?}``; empty or missing means automatic."""


_REDIARIZE_STATUS: dict[RediarizeFailureCode, int] = {
    RediarizeFailureCode.TRANSCRIPT_NOT_FOUND: 404,
    RediarizeFailureCode.JOB_NOT_FOUND: 409,
    RediarizeFailureCode.JOB_ALREADY_ACTIVE: 409,
    RediarizeFailureCode.DIARIZATION_UNAVAILABLE: 409,
    RediarizeFailureCode.DIARIZATION_MODELS_MISSING: 409,
}


def _invalid_diarization(message: str) -> HTTPException:
    return api_error(422, "diarization_options_invalid", message)


def parse_diarization(raw: object) -> DiarizationOptions | None:
    """Validate the request body; ``None`` means diarization is disabled."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _invalid_diarization("diarization must be an object.")
    body = cast(dict[str, object], raw)
    if set(body) - {"enabled", "speakers"}:
        raise _invalid_diarization("diarization has unknown fields.")
    enabled = body.get("enabled", False)
    if not isinstance(enabled, bool):
        raise _invalid_diarization("diarization.enabled must be a boolean.")
    raw_speakers = body.get("speakers", {})
    if not isinstance(raw_speakers, dict):
        raise _invalid_diarization("diarization.speakers must be an object.")
    speakers = cast(dict[str, object], raw_speakers)
    if set(speakers) - set(_SPEAKER_KEYS):
        raise _invalid_diarization("diarization.speakers has unknown fields.")
    for value in speakers.values():
        if value is not None and (
            type(value) is not int or not 1 <= value <= MAX_DIARIZATION_SPEAKERS
        ):
            raise _invalid_diarization(
                f"Speaker counts must be integers from 1 to {MAX_DIARIZATION_SPEAKERS}."
            )
    try:
        hint = SpeakerCountHint(**cast(dict[str, int | None], speakers))
    except (TypeError, ValueError):
        raise _invalid_diarization(
            "Use either exact, or minimum not greater than maximum."
        ) from None
    return DiarizationOptions(hint) if enabled else None


def selection_view(selection: JobSelection) -> dict[str, object]:
    """Same profile/execution JSON shape as ``/api/transcription-options``."""
    model = selection.model
    hint = (selection.diarization or DiarizationOptions()).speakers
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
        "quality_profile": (
            None
            if selection.quality_profile is None
            else selection.quality_profile.to_dict()
        ),
        "glossary": list(selection.glossary),
        "prompt": selection.prompt,
        "diarization": {
            "enabled": selection.diarization is not None,
            "speakers": {
                "exact": hint.exact,
                "minimum": hint.minimum,
                "maximum": hint.maximum,
            },
        },
    }


def job_view(
    job: TranscriptionJob,
    selection: JobSelection,
    *,
    has_transcript: bool | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Path-free job projection consumed by the browser.

    ``has_transcript`` says whether the transcript row already exists (it does
    from the end of transcription, before the speakers); ``None`` falls back to
    "the job completed".
    """
    if has_transcript is None:
        has_transcript = job.state is TranscriptionJobState.COMPLETED
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "media_asset_id": str(job.media_asset_id),
        "state": job.state.value,
        "progress": job.progress,
        "error_code": job.error_code,
        "diarization_error_code": selection.diarization_error_code,
        "transcript_id": str(transcript_id_for(job.id)) if has_transcript else None,
        **timing_view(job, now),
        "selection": selection_view(selection),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


_NO_TRANSCRIPT_YET = frozenset(
    {
        TranscriptionJobState.QUEUED,
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
    }
)


def job_has_transcript(
    job: TranscriptionJob, transcripts: TranscriptRepository
) -> bool:
    """The transcript row exists from the end of transcription, before the speakers."""
    if job.state is TranscriptionJobState.COMPLETED:
        return True
    if job.state in _NO_TRANSCRIPT_YET:
        return False
    return transcripts.get(transcript_id_for(job.id)) is not None


def create_jobs_router(
    create_job: CreateTranscriptionJob,
    jobs_repo: TranscriptionJobRepository,
    selections_repo: TranscriptionJobSelectionRepository,
    transcripts_repo: TranscriptRepository,
    segments_repo: SegmentRepository,
    runner: JobRunner,
    speaker_turns_repo: SpeakerTurnRepository | None = None,
    checkpoints: TranscriptionCheckpointStore | None = None,
    rediarize: RediarizeTranscript | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["jobs"])

    def view(job: TranscriptionJob) -> dict[str, object]:
        selection = selections_repo.get(job.id)
        if selection is None:
            raise api_error(
                500, "job_selection_missing", "The job has no persisted selection."
            )
        return job_view(
            job, selection, has_transcript=job_has_transcript(job, transcripts_repo)
        )

    def require_job(job_id: UUID) -> TranscriptionJob:
        job = jobs_repo.get(job_id)
        if job is None:
            raise api_error(404, "job_not_found", "The job does not exist.")
        return job

    def post_job(request: CreateJobRequest) -> dict[str, object]:
        diarization = parse_diarization(request.diarization)
        try:
            created = create_job.execute(
                project_id=request.project_id,
                media_asset_id=request.media_asset_id,
                option_id=request.option_id,
                language=request.language,
                diarization=diarization,
                profile=request.profile,
                prompt=request.prompt,
            )
        except CreateJobError as error:
            extra: dict[str, object] = {}
            if error.code is CreateJobFailureCode.OPTION_NOT_STARTABLE:
                extra["blocking_reasons"] = [
                    reason.value for reason in error.blocking_reasons
                ]
            if error.required_mib is not None:
                extra["required_mib"] = error.required_mib
                extra["available_mib"] = error.available_mib
            raise api_error(
                _CREATE_STATUS[error.code],
                error.code.value,
                error.user_message,
                **extra,
            ) from None
        runner.enqueue(created.job.id)
        return job_view(created.job, created.selection, has_transcript=False)

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
            raise api_error(404, "job_not_found", "The job does not exist.") from None
        except JobTerminal:
            raise api_error(409, "job_terminal", "The job already finished.") from None

    def job_preview(job_id: UUID, after_ms: int = Query(0, ge=0)) -> dict[str, object]:
        """Segments confirmed in checkpoints; ``after_ms`` asks only for newer ones."""
        require_job(job_id)
        confirmed = () if checkpoints is None else checkpoints.list_for_job(job_id)
        return {
            "segments": [
                {"start_ms": item.start_ms, "end_ms": item.end_ms, "text": text}
                for checkpoint in confirmed
                if checkpoint.owned_end_ms > after_ms
                for item in checkpoint.segments
                if item.end_ms > after_ms and (text := item.text.strip())
            ]
        }

    def list_segments(transcript_id: UUID) -> dict[str, object]:
        if transcripts_repo.get(transcript_id) is None:
            raise api_error(
                404, "transcript_not_found", "The transcript does not exist."
            )
        # S7.05: each word takes the speaker of the turn covering its midpoint.
        timeline = (
            None
            if speaker_turns_repo is None
            else SpeakerTimeline(speaker_turns_repo.list_by_transcript(transcript_id))
        )
        return {
            "segments": [
                segment_view(segment, timeline)
                for segment in segments_repo.list_by_transcript(transcript_id)
            ]
        }

    def post_rediarize(
        transcript_id: UUID, request: RediarizeRequest
    ) -> dict[str, object]:
        assert rediarize is not None
        options = parse_diarization(
            {
                "enabled": True,
                "speakers": {} if request.speakers is None else request.speakers,
            }
        )
        assert options is not None
        try:
            started = rediarize.execute(transcript_id, options)
        except RediarizeError as error:
            raise api_error(
                _REDIARIZE_STATUS[error.code], error.code.value, error.user_message
            ) from None
        runner.enqueue(started.job.id)
        return job_view(started.job, started.selection, has_transcript=True)

    router.add_api_route("/jobs", post_job, methods=["POST"], status_code=201)
    if rediarize is not None:
        router.add_api_route(
            "/transcripts/{transcript_id}/rediarize",
            post_rediarize,
            methods=["POST"],
            status_code=202,
        )
    router.add_api_route("/jobs", list_jobs, methods=["GET"])
    router.add_api_route("/jobs/{job_id}", get_job, methods=["GET"])
    router.add_api_route(
        "/jobs/{job_id}/cancel", cancel_job, methods=["POST"], status_code=202
    )
    router.add_api_route("/jobs/{job_id}/preview", job_preview, methods=["GET"])
    router.add_api_route(
        "/transcripts/{transcript_id}/segments", list_segments, methods=["GET"]
    )
    return router


__all__ = [
    "CreateJobRequest",
    "create_jobs_router",
    "job_has_transcript",
    "job_view",
    "parse_diarization",
    "selection_view",
]
