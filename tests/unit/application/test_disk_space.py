"""Disk-space guard before import and normalization."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

import pytest

from voz.application.import_media import ImportedMedia, ImportMedia
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.disk_space import (
    DEFAULT_DISK_MARGIN_BYTES,
    PCM_BYTES_PER_MS,
    DiskLocation,
    InsufficientDiskSpace,
    require_free_space,
)
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationProgressCallback,
    NormalizedAudio,
)
from voz.application.ports.media_probe import (
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)
from voz.domain.entities.media_asset import MediaAsset


class FakeDisk:
    def __init__(self, free: int) -> None:
        self.free = free
        self.asked: list[DiskLocation] = []

    def free_bytes(self, location: DiskLocation) -> int:
        self.asked.append(location)
        return self.free


def test_insufficient_disk_space_error_is_typed_retryable_and_path_free() -> None:
    error = InsufficientDiskSpace()

    assert error.code == "disk_space_insufficient"
    assert error.retryable is True
    assert "/" not in error.user_message


def test_require_free_space_counts_the_margin() -> None:
    needed = 1_000
    require_free_space(
        FakeDisk(needed + DEFAULT_DISK_MARGIN_BYTES), DiskLocation.ORIGINALS, needed
    )
    with pytest.raises(InsufficientDiskSpace):
        require_free_space(
            FakeDisk(needed + DEFAULT_DISK_MARGIN_BYTES - 1),
            DiskLocation.ORIGINALS,
            needed,
        )
    require_free_space(None, DiskLocation.ORIGINALS, 10**18)


class ExplodingStorage:
    def import_original(self, **_: object) -> object:
        raise AssertionError("must not copy when there is no space")


class FakeStorage:
    def open_original(self, *, project_id: UUID, media_asset_id: UUID) -> BinaryIO:
        return BytesIO(b"x")


def test_import_checks_source_size_before_touching_storage(tmp_path: Path) -> None:
    source = tmp_path / "a.wav"
    source.write_bytes(b"x" * 100)
    disk = FakeDisk(free=DEFAULT_DISK_MARGIN_BYTES + 99)
    use_case = ImportMedia(
        media_probe=None,  # type: ignore[arg-type]
        media_storage=ExplodingStorage(),  # type: ignore[arg-type]
        media_assets=None,  # type: ignore[arg-type]
        disk_space=disk,
    )

    with pytest.raises(InsufficientDiskSpace):
        use_case.execute(source=source, project_id=uuid4())

    assert disk.asked == [DiskLocation.ORIGINALS]


class RecordingNormalizer:
    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        return NormalizedAudio(bytes_written=44)


def _imported(duration_ms: int) -> ImportedMedia:
    asset = MediaAsset(uuid4(), "a" * 64, "x.wav", 10, duration_ms=duration_ms)
    audio = ProbedMediaStream(0, MediaStreamKind.AUDIO, "pcm_s16le", True, 48_000, 2)
    return ImportedMedia(asset, MediaProbeResult(("wav",), (audio,), duration_ms))


def test_normalize_estimates_pcm_size_and_never_starts_without_space() -> None:
    duration_ms = 60_000
    needed = duration_ms * PCM_BYTES_PER_MS
    normalizer = RecordingNormalizer()

    def use_case(free: int) -> NormalizeImportedMedia:
        return NormalizeImportedMedia(
            media_storage=FakeStorage(),  # type: ignore[arg-type]
            media_normalization=normalizer,
            disk_space=FakeDisk(free),
        )

    with pytest.raises(InsufficientDiskSpace):
        use_case(needed + DEFAULT_DISK_MARGIN_BYTES - 1).execute(
            imported_media=_imported(duration_ms)
        )
    assert normalizer.calls == 0

    use_case(needed + DEFAULT_DISK_MARGIN_BYTES).execute(
        imported_media=_imported(duration_ms)
    )
    assert normalizer.calls == 1
