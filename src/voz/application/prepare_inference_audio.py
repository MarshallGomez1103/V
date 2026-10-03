"""Produce the missing inference derivative for a stored original, by identity."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from voz.application.import_media import ImportedMedia
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
    MediaNormalizationProgressCallback,
)
from voz.application.ports.media_probe import MediaProbePort
from voz.application.ports.media_storage import MediaStoragePort
from voz.application.ports.repositories import MediaAssetRepository


@dataclass(slots=True)
class PrepareInferenceAudio:
    """Re-probe the immutable original and normalize it without host paths."""

    media_storage: MediaStoragePort
    media_probe: MediaProbePort
    media_assets: MediaAssetRepository
    normalize: NormalizeImportedMedia

    def prepare(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        cancellation: MediaNormalizationCancellationToken | None = None,
        on_progress: MediaNormalizationProgressCallback | None = None,
    ) -> None:
        media_asset = self.media_assets.get(media_asset_id)
        if media_asset is None or media_asset.project_id != project_id:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.INVALID_SOURCE,
                "The media asset is not available for normalization.",
            )
        with self.media_storage.open_original(
            project_id=project_id,
            media_asset_id=media_asset_id,
        ) as original:
            probe_result = self.media_probe.probe(original)
        self.normalize.execute(
            imported_media=ImportedMedia(media_asset, probe_result),
            on_progress=on_progress,
            cancellation=cancellation,
        )


__all__ = ["PrepareInferenceAudio"]
