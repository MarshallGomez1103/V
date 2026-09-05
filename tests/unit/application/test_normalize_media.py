"""Unit tests for normalization orchestration across application ports."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

import pytest

from voz.application.import_media import ImportedMedia
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
    MediaNormalizationProgressCallback,
    NormalizedAudio,
)
from voz.application.ports.media_probe import (
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)
from voz.application.ports.media_storage import ImportedOriginal
from voz.domain.entities.media_asset import MediaAsset


class _Storage:
    def __init__(self) -> None:
        self.opened_identity: tuple[UUID, UUID] | None = None

    def import_original(
        self,
        *,
        source: Path,
        project_id: UUID,
        media_asset_id: UUID,
        media_type: str | None = None,
    ) -> ImportedOriginal:
        raise NotImplementedError

    def open_original(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> BinaryIO:
        self.opened_identity = (project_id, media_asset_id)
        return BytesIO(b"stored original")

    def discard_original(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> None:
        raise NotImplementedError


class _Normalizer:
    def __init__(self) -> None:
        self.original_bytes: bytes | None = None
        self.identity: tuple[UUID, UUID] | None = None
        self.duration_ms: int | None = None
        self.audio_stream_index: int | None = None

    def normalize(
        self,
        *,
        original: BinaryIO,
        project_id: UUID,
        media_asset_id: UUID,
        duration_ms: int,
        audio_stream_index: int,
        on_progress: MediaNormalizationProgressCallback | None = None,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> NormalizedAudio:
        self.original_bytes = original.read()
        self.identity = (project_id, media_asset_id)
        self.duration_ms = duration_ms
        self.audio_stream_index = audio_stream_index
        return NormalizedAudio(bytes_written=44)


def _imported_media(*, duration_ms: int | None = 2_500) -> ImportedMedia:
    project_id = uuid4()
    media_asset = MediaAsset(
        project_id=project_id,
        content_sha256="a" * 64,
        display_name="lecture.mkv",
        size_bytes=15,
        id=uuid4(),
        duration_ms=duration_ms,
    )
    return ImportedMedia(
        media_asset=media_asset,
        probe_result=MediaProbeResult(
            format_names=("matroska",),
            duration_ms=duration_ms,
            streams=(
                ProbedMediaStream(
                    index=0,
                    kind=MediaStreamKind.VIDEO,
                    codec_name="ffv1",
                    is_decodable=True,
                ),
                ProbedMediaStream(
                    index=1,
                    kind=MediaStreamKind.AUDIO,
                    codec_name="pcm_s16le",
                    is_decodable=True,
                    sample_rate_hz=48_000,
                    channels=2,
                ),
            ),
        ),
    )


def test_normalize_imported_media_opens_by_identity_and_preserves_stream_index() -> (
    None
):
    imported = _imported_media()
    storage = _Storage()
    normalizer = _Normalizer()

    result = NormalizeImportedMedia(
        media_storage=storage,
        media_normalization=normalizer,
    ).execute(imported_media=imported)

    identity = (imported.media_asset.project_id, imported.media_asset.id)
    assert result == NormalizedAudio(bytes_written=44)
    assert storage.opened_identity == identity
    assert normalizer.identity == identity
    assert normalizer.original_bytes == b"stored original"
    assert normalizer.duration_ms == 2_500
    assert normalizer.audio_stream_index == 1


def test_normalize_imported_media_rejects_missing_duration_before_opening() -> None:
    imported = _imported_media(duration_ms=None)
    storage = _Storage()
    normalizer = _Normalizer()

    with pytest.raises(MediaNormalizationError) as captured:
        NormalizeImportedMedia(
            media_storage=storage,
            media_normalization=normalizer,
        ).execute(imported_media=imported)

    assert captured.value.code is MediaNormalizationFailureCode.INVALID_SOURCE
    assert storage.opened_identity is None
    assert normalizer.identity is None
