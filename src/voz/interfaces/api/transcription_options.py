"""Thin HTTP input adapter for canonical transcription options."""

from fastapi import APIRouter, HTTPException

from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    TranscriptionOptions,
)
from voz.application.ports.transcription_options import TranscriptionOptionsUnavailable


def create_transcription_options_router(query: GetTranscriptionOptions) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["transcription"])

    def get_transcription_options() -> TranscriptionOptions:
        try:
            return query.execute()
        except TranscriptionOptionsUnavailable:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "transcription_options_unavailable",
                    "message": "Transcription options could not be inspected.",
                },
            ) from None

    router.add_api_route(
        "/transcription-options",
        get_transcription_options,
        methods=["GET"],
        response_model=TranscriptionOptions,
    )
    return router
