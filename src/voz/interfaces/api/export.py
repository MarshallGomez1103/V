"""Thin HTTP adapter that downloads a transcript export (S10.14)."""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from voz.application.export.service import ExportError, ExportTranscript

_MEDIA_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "json": "application/json",
}
_STATUS = {
    "export_format_unknown": 422,
    "export_option_unsupported": 422,
    "transcript_not_found": 404,
}


def create_export_router(export: ExportTranscript) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["export"])

    def download(
        transcript_id: UUID,
        format: str = "txt",
        timestamps: bool = False,
        group_by_speaker: bool = False,
    ) -> Response:
        try:
            document = export.execute(
                transcript_id,
                format,
                timestamps=timestamps,
                group_by_speaker=group_by_speaker,
            )
        except ExportError as error:
            raise HTTPException(
                status_code=_STATUS[error.code],
                detail={"code": error.code, "message": error.message},
            ) from None
        disposition = f'attachment; filename="{document.ascii_filename}"'
        if document.filename != document.ascii_filename:
            disposition += f"; filename*=UTF-8''{quote(document.filename, safe='')}"
        return Response(
            document.content.encode("utf-8"),
            headers={
                "Content-Type": _MEDIA_TYPES[document.format_id],
                "Content-Disposition": disposition,
                "X-Content-Type-Options": "nosniff",
            },
        )

    router.add_api_route("/transcripts/{transcript_id}/export", download)
    return router


__all__ = ["create_export_router"]
