"""Use case: peaks for the waveform view of one imported media asset."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from voz.application.ports.repositories import MediaAssetRepository
from voz.application.ports.waveform import (
    WaveformError,
    WaveformFailureCode,
    WaveformPeaks,
    WaveformPeaksProvider,
)

MIN_BUCKETS: Final = 100
MAX_BUCKETS: Final = 20_000


class GetWaveformPeaks:
    """Validate the request, resolve the asset and delegate decoding to a port."""

    def __init__(
        self,
        media_assets: MediaAssetRepository,
        provider: WaveformPeaksProvider,
    ) -> None:
        self._media_assets = media_assets
        self._provider = provider

    def execute(self, media_asset_id: UUID, buckets: int) -> WaveformPeaks:
        if type(buckets) is not int or not MIN_BUCKETS <= buckets <= MAX_BUCKETS:
            raise WaveformError(
                WaveformFailureCode.BUCKETS_INVALID,
                f"buckets must be an integer between {MIN_BUCKETS} and {MAX_BUCKETS}.",
            )
        asset = self._media_assets.get(media_asset_id)
        if asset is None:
            raise WaveformError(
                WaveformFailureCode.MEDIA_ASSET_NOT_FOUND,
                "The media asset does not exist.",
            )
        series = self._provider.peaks(
            project_id=asset.project_id,
            media_asset_id=asset.id,
            content_sha256=asset.content_sha256,
            buckets=buckets,
        )
        return WaveformPeaks(
            media_asset_id=asset.id,
            duration_ms=asset.duration_ms or series.duration_ms,
            buckets=buckets,
            peaks=series.peaks,
        )


__all__ = ["MAX_BUCKETS", "MIN_BUCKETS", "GetWaveformPeaks"]
