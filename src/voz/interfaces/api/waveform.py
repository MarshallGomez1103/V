"""Thin HTTP adapter for precomputed waveform peaks."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import APIRouter, HTTPException

from voz.application.ports.waveform import WaveformError, WaveformFailureCode
from voz.application.waveform_peaks import GetWaveformPeaks

_DEFAULT_BUCKETS: Final = "2000"
_STATUS: Final = {
    WaveformFailureCode.MEDIA_ASSET_NOT_FOUND: 404,
    WaveformFailureCode.BUCKETS_INVALID: 422,
    WaveformFailureCode.UNAVAILABLE: 500,
}


def create_waveform_router(get_peaks: GetWaveformPeaks) -> APIRouter:
    """Expose ``GET /api/media/{media_asset_id}/peaks``."""
    router = APIRouter(prefix="/api", tags=["media"])

    # ``def`` (not ``async def``): FastAPI runs the FFmpeg decode in its threadpool.
    def read_peaks(
        media_asset_id: UUID, buckets: str = _DEFAULT_BUCKETS
    ) -> dict[str, object]:
        try:
            # ponytail: parsed here so non-numeric input gets the stable error code.
            count = int(buckets) if buckets.isascii() and buckets.isdigit() else -1
            result = get_peaks.execute(media_asset_id, count)
        except WaveformError as error:
            raise HTTPException(
                status_code=_STATUS[error.code],
                detail={"code": error.code.value, "message": error.user_message},
            ) from error
        return {
            "media_asset_id": str(result.media_asset_id),
            "duration_ms": result.duration_ms,
            "buckets": result.buckets,
            "peaks": [[low, high] for low, high in result.peaks],
        }

    router.add_api_route("/media/{media_asset_id}/peaks", read_peaks, methods=["GET"])
    return router


__all__ = ["create_waveform_router"]
