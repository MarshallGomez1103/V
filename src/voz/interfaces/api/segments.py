"""Thin HTTP adapter to edit the text of a transcript segment."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, HTTPException

from voz.application.edit_segment import (
    EditSegmentText,
    SegmentNotFound,
    SegmentRevisionConflict,
    SegmentTextInvalid,
)
from voz.application.ports.repositories import SegmentRepository
from voz.application.word_speakers import SpeakerTimeline, word_speaker_ids
from voz.domain.entities.segment import Segment


@dataclass(frozen=True, slots=True)
class EditSegmentRequest:
    text: str
    revision: int


def segment_view(
    segment: Segment, timeline: SpeakerTimeline | None = None
) -> dict[str, object]:
    """Path-free segment item shared by the list and edit endpoints.

    ``timeline`` (the transcript's speaker turns) refines each word's speaker;
    without it words inherit the speaker of their segment.
    """
    return {
        "id": str(segment.id),
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "text": segment.text,
        "edited": segment.edited,
        "revision": segment.revision,
        "speaker_id": None if segment.speaker_id is None else str(segment.speaker_id),
        # Timings describe the ASR text; once the text is edited they no longer
        # match it, so they are withheld (kept in storage, not exposed).
        "words": []
        if segment.edited
        else [
            {
                "start_ms": word.start_ms,
                "end_ms": word.end_ms,
                "text": word.text,
                "speaker_id": None if speaker_id is None else str(speaker_id),
            }
            for word, speaker_id in zip(
                segment.words, word_speaker_ids(segment, timeline), strict=True
            )
        ],
    }


def _error(status_code: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
    )


def create_segments_router(
    edit_segment: EditSegmentText, segments_repo: SegmentRepository
) -> APIRouter:
    del segments_repo  # ponytail: reserved for future read endpoints; unused today
    router = APIRouter(prefix="/api", tags=["segments"])

    def put_segment(segment_id: UUID, request: EditSegmentRequest) -> dict[str, object]:
        try:
            return segment_view(
                edit_segment.execute(segment_id, request.text, request.revision)
            )
        except SegmentNotFound:
            raise _error(
                404, "segment_not_found", "The segment does not exist."
            ) from None
        except SegmentTextInvalid:
            raise _error(
                422, "segment_text_invalid", "The segment text cannot be empty."
            ) from None
        except SegmentRevisionConflict as conflict:
            raise _error(
                409,
                "segment_revision_conflict",
                "The segment changed since it was loaded.",
                current=segment_view(conflict.current),
            ) from None

    router.add_api_route("/segments/{segment_id}", put_segment, methods=["PUT"])
    return router


__all__ = ["EditSegmentRequest", "create_segments_router", "segment_view"]
