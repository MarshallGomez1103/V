"""Application orchestration for inference-audio normalization."""

from __future__ import annotations

from dataclasses import dataclass

from voz.application.import_media import ImportedMedia
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
    MediaNormalizationPort,
    MediaNormalizationProgressCallback,
    NormalizedAudio,
)
from voz.application.ports.media_probe import MediaStreamKind
from voz.application.ports.media_storage import MediaStoragePort


@dataclass(slots=True)
class NormalizeImportedMedia:
    """Normalize a stored original without exposing its filesystem location."""

    media_storage: MediaStoragePort
    media_normalization: MediaNormalizationPort

    def execute(
        self,
        *,
        imported_media: ImportedMedia,
        on_progress: MediaNormalizationProgressCallback | None = None,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> NormalizedAudio:
        """Select the first decodable audio stream and normalize the original."""
        duration_ms = imported_media.probe_result.duration_ms
        if duration_ms is None:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.INVALID_SOURCE,
                "The imported media has no usable duration.",
            )

        audio_stream = next(
            (
                stream
                for stream in imported_media.probe_result.streams
                if stream.kind is MediaStreamKind.AUDIO and stream.is_decodable
            ),
            None,
        )
        if audio_stream is None:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.INVALID_SOURCE,
                "The imported media has no decodable audio stream.",
            )

        media_asset = imported_media.media_asset
        with self.media_storage.open_original(
            project_id=media_asset.project_id,
            media_asset_id=media_asset.id,
        ) as original:
            return self.media_normalization.normalize(
                original=original,
                project_id=media_asset.project_id,
                media_asset_id=media_asset.id,
                duration_ms=duration_ms,
                audio_stream_index=audio_stream.index,
                on_progress=on_progress,
                cancellation=cancellation,
            )


__all__ = ["NormalizeImportedMedia"]
