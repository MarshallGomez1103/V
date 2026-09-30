"""Thin HTTP adapter to list, restyle, merge and assign transcript speakers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, HTTPException

from voz.application.assign_speakers import TranscriptNotFound
from voz.application.edit_segment import SegmentNotFound
from voz.application.speakers import (
    AssignSegmentSpeaker,
    ListTranscriptSpeakers,
    MergeSpeakers,
    SegmentSpeakerInvalid,
    SpeakerMergeInvalid,
    SpeakerNotFound,
    SpeakerSummary,
    SpeakerUpdateInvalid,
    UpdateSpeaker,
)
from voz.interfaces.api.segments import segment_view


@dataclass(frozen=True, slots=True)
class UpdateSpeakerRequest:
    name: str | None = None
    color: str | None = None


@dataclass(frozen=True, slots=True)
class MergeSpeakerRequest:
    into: UUID


@dataclass(frozen=True, slots=True)
class AssignSpeakerRequest:
    speaker_id: UUID | None


def speaker_view(summary: SpeakerSummary) -> dict[str, object]:
    """Path-free speaker item shared by every speakers endpoint."""
    speaker = summary.speaker
    return {
        "id": str(speaker.id),
        "name": speaker.name,
        "color": speaker.color,
        "segment_count": summary.segment_count,
    }


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def create_speakers_router(
    list_speakers: ListTranscriptSpeakers,
    update_speaker: UpdateSpeaker,
    merge_speakers: MergeSpeakers,
    assign_segment_speaker: AssignSegmentSpeaker,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["speakers"])

    def get_speakers(transcript_id: UUID) -> dict[str, object]:
        try:
            summaries = list_speakers.execute(transcript_id)
        except TranscriptNotFound:
            raise _error(
                404, "transcript_not_found", "The transcript does not exist."
            ) from None
        return {"speakers": [speaker_view(summary) for summary in summaries]}

    def patch_speaker(
        speaker_id: UUID, request: UpdateSpeakerRequest
    ) -> dict[str, object]:
        try:
            return speaker_view(
                update_speaker.execute(
                    speaker_id, name=request.name, color=request.color
                )
            )
        except SpeakerNotFound:
            raise _error(
                404, "speaker_not_found", "The speaker does not exist."
            ) from None
        except SpeakerUpdateInvalid:
            raise _error(
                422,
                "speaker_update_invalid",
                "The name must have 1 to 80 characters and the color use #rrggbb.",
            ) from None

    def post_merge(speaker_id: UUID, request: MergeSpeakerRequest) -> dict[str, object]:
        try:
            return {
                "speaker": speaker_view(
                    merge_speakers.execute(speaker_id, request.into)
                )
            }
        except SpeakerNotFound:
            raise _error(
                404, "speaker_not_found", "The speaker does not exist."
            ) from None
        except SpeakerMergeInvalid:
            raise _error(
                409,
                "speaker_merge_invalid",
                "Only two different speakers of the same transcript can be merged.",
            ) from None

    def put_segment_speaker(
        segment_id: UUID, request: AssignSpeakerRequest
    ) -> dict[str, object]:
        try:
            return segment_view(
                assign_segment_speaker.execute(segment_id, request.speaker_id)
            )
        except SegmentNotFound:
            raise _error(
                404, "segment_not_found", "The segment does not exist."
            ) from None
        except SegmentSpeakerInvalid:
            raise _error(
                409,
                "segment_speaker_invalid",
                "The speaker does not belong to this segment's transcript.",
            ) from None

    router.add_api_route("/transcripts/{transcript_id}/speakers", get_speakers)
    router.add_api_route("/speakers/{speaker_id}", patch_speaker, methods=["PATCH"])
    router.add_api_route("/speakers/{speaker_id}/merge", post_merge, methods=["POST"])
    router.add_api_route(
        "/segments/{segment_id}/speaker", put_segment_speaker, methods=["PUT"]
    )
    return router


__all__ = ["create_speakers_router", "speaker_view"]
