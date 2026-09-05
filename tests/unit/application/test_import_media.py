"""Unit tests for the media import application use case."""

from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

import pytest

from voz.application.import_media import (
    ImportMedia,
    MediaImportOutcomeUncertainError,
    MediaImportRollbackError,
)
from voz.application.ports.media_probe import (
    MediaProbeError,
    MediaProbeFailureCode,
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)
from voz.application.ports.media_storage import ImportedOriginal
from voz.domain.entities.media_asset import MediaAsset


class FakeProbe:
    def __init__(
        self,
        result: MediaProbeResult,
        events: list[str],
        *,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.events = events
        self.error = error
        self.observed_bytes: bytes | None = None

    def probe(self, source: BinaryIO) -> MediaProbeResult:
        self.events.append("probe")
        self.observed_bytes = source.read()
        if self.error is not None:
            raise self.error
        return self.result


class FakeStorage:
    def __init__(
        self,
        events: list[str],
        *,
        rollback_fails: bool = False,
        stored_bytes: bytes = b"original",
        mutate_source_after_copy: bytes | None = None,
    ) -> None:
        self.events = events
        self.rollback_fails = rollback_fails
        self.stored_bytes = stored_bytes
        self.mutate_source_after_copy = mutate_source_after_copy
        self.imported = False
        self.received_media_type: str | None = None

    def import_original(
        self,
        *,
        source: Path,
        project_id: UUID,
        media_asset_id: UUID,
        media_type: str | None = None,
    ) -> ImportedOriginal:
        self.events.append("store")
        self.imported = True
        self.received_media_type = media_type
        if self.mutate_source_after_copy is not None:
            Path(source).write_bytes(self.mutate_source_after_copy)
        asset = MediaAsset(
            project_id=project_id,
            content_sha256="a" * 64,
            display_name=source.name,
            size_bytes=len(self.stored_bytes),
            id=media_asset_id,
            media_type=media_type,
        )
        return ImportedOriginal(
            media_asset=asset,
            bytes_copied=len(self.stored_bytes),
        )

    def open_original(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> BinaryIO:
        self.events.append("open")
        return BytesIO(self.stored_bytes)

    def discard_original(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> None:
        self.events.append("discard")
        if self.rollback_fails:
            raise OSError("simulated rollback failure")
        self.imported = False


class FakeMediaAssetRepository:
    def __init__(
        self,
        events: list[str],
        *,
        add_error: BaseException | None = None,
        commit_before_raise: bool = False,
        get_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.add_error = add_error
        self.commit_before_raise = commit_before_raise
        self.get_error = get_error
        self.added: MediaAsset | None = None

    def add(self, media_asset: MediaAsset) -> None:
        self.events.append("persist")
        if self.commit_before_raise:
            self.added = media_asset
        if self.add_error is not None:
            raise self.add_error
        self.added = media_asset

    def save(self, media_asset: MediaAsset) -> None:
        self.added = media_asset

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        self.events.append("get")
        if self.get_error is not None:
            raise self.get_error
        return (
            self.added
            if self.added is not None and self.added.id == media_asset_id
            else None
        )

    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]:
        if self.added is not None and self.added.project_id == project_id:
            return (self.added,)
        return ()


def audio_probe_result(
    *,
    format_names: tuple[str, ...] = ("wav",),
    duration_ms: int | None = 2_500,
) -> MediaProbeResult:
    return MediaProbeResult(
        format_names=format_names,
        duration_ms=duration_ms,
        streams=(
            ProbedMediaStream(
                index=0,
                kind=MediaStreamKind.AUDIO,
                codec_name="pcm_s16le",
                is_decodable=True,
                sample_rate_hz=16_000,
                channels=1,
            ),
        ),
    )


def test_import_coordinates_probe_storage_and_persistence_without_a_path() -> None:
    events: list[str] = []
    project_id = uuid4()
    media_asset_id = uuid4()
    probe_result = audio_probe_result()
    storage = FakeStorage(events)
    repository = FakeMediaAssetRepository(events)
    use_case = ImportMedia(
        media_probe=FakeProbe(probe_result, events),
        media_storage=storage,
        media_assets=repository,
        id_factory=lambda: media_asset_id,
    )
    source = Path("/private/course/Class recording.unrelated")

    result = use_case.execute(source=source, project_id=project_id)

    assert events == ["store", "open", "probe", "persist"]
    assert repository.added == result.media_asset
    assert result.media_asset.id == media_asset_id
    assert result.media_asset.content_sha256 == "a" * 64
    assert result.media_asset.duration_ms == 2_500
    assert result.media_asset.media_type == "audio/wav"
    assert storage.received_media_type is None
    assert result.probe_result.audio_streams[0].codec_name == "pcm_s16le"
    assert result.probe_result.audio_streams[0].sample_rate_hz == 16_000
    assert result.probe_result.audio_streams[0].channels == 1
    assert str(source.parent) not in repr(result)


def test_probe_content_selects_video_media_type_independent_of_extension() -> None:
    events: list[str] = []
    probe_result = MediaProbeResult(
        format_names=("mov", "mp4", "m4a"),
        duration_ms=1_000,
        streams=(
            ProbedMediaStream(
                index=0,
                kind=MediaStreamKind.VIDEO,
                codec_name="h264",
                is_decodable=True,
            ),
            ProbedMediaStream(
                index=1,
                kind=MediaStreamKind.AUDIO,
                codec_name="aac",
                is_decodable=True,
                sample_rate_hz=48_000,
                channels=2,
            ),
        ),
    )
    storage = FakeStorage(events)

    result = ImportMedia(
        media_probe=FakeProbe(probe_result, events),
        media_storage=storage,
        media_assets=FakeMediaAssetRepository(events),
    ).execute(source=Path("recording.bin"), project_id=uuid4())

    assert storage.received_media_type is None
    assert result.media_asset.media_type == "video/mp4"


def test_unknown_probe_format_is_persisted_without_an_untrusted_media_type() -> None:
    events: list[str] = []
    storage = FakeStorage(events)

    result = ImportMedia(
        media_probe=FakeProbe(audio_probe_result(format_names=("mystery",)), events),
        media_storage=storage,
        media_assets=FakeMediaAssetRepository(events),
    ).execute(source=Path("recording.wav"), project_id=uuid4())

    assert storage.received_media_type is None
    assert result.media_asset.media_type is None


def test_probe_reads_the_published_copy_even_if_source_changes_after_copy(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    source = tmp_path / "lecture.wav"
    source.write_bytes(b"copied bytes")
    probe = FakeProbe(audio_probe_result(), events)
    storage = FakeStorage(
        events,
        stored_bytes=b"copied bytes",
        mutate_source_after_copy=b"changed source",
    )

    ImportMedia(
        media_probe=probe,
        media_storage=storage,
        media_assets=FakeMediaAssetRepository(events),
    ).execute(source=source, project_id=uuid4())

    assert probe.observed_bytes == b"copied bytes"
    assert source.read_bytes() == b"changed source"
    assert events == ["store", "open", "probe", "persist"]


def test_probe_failure_discards_original_without_persisting_metadata() -> None:
    events: list[str] = []
    storage = FakeStorage(events)
    repository = FakeMediaAssetRepository(events)
    failure = MediaProbeError(
        MediaProbeFailureCode.INVALID_MEDIA,
        "The selected file is not readable media.",
    )

    with pytest.raises(MediaProbeError) as captured:
        ImportMedia(
            media_probe=FakeProbe(audio_probe_result(), events, error=failure),
            media_storage=storage,
            media_assets=repository,
        ).execute(source=Path("broken.wav"), project_id=uuid4())

    assert captured.value is failure
    assert events == ["store", "open", "probe", "discard"]
    assert repository.added is None
    assert not storage.imported


def test_base_exception_during_probe_discards_original_and_reraises() -> None:
    events: list[str] = []
    storage = FakeStorage(events)
    interruption = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt) as captured:
        ImportMedia(
            media_probe=FakeProbe(
                audio_probe_result(),
                events,
                error=interruption,
            ),
            media_storage=storage,
            media_assets=FakeMediaAssetRepository(events),
        ).execute(source=Path("recording.wav"), project_id=uuid4())

    assert captured.value is interruption
    assert events == ["store", "open", "probe", "discard"]
    assert not storage.imported


def test_probe_interruption_remains_primary_when_rollback_also_fails() -> None:
    events: list[str] = []
    interruption = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt) as captured:
        ImportMedia(
            media_probe=FakeProbe(
                audio_probe_result(),
                events,
                error=interruption,
            ),
            media_storage=FakeStorage(events, rollback_fails=True),
            media_assets=FakeMediaAssetRepository(events),
        ).execute(source=Path("recording.wav"), project_id=uuid4())

    assert captured.value is interruption
    assert isinstance(captured.value.__cause__, MediaImportRollbackError)
    assert any("rollback failure" in note for note in captured.value.__notes__)
    assert events == ["store", "open", "probe", "discard"]


def test_repository_failure_discards_published_original_and_reraises() -> None:
    events: list[str] = []
    storage = FakeStorage(events)
    failure = RuntimeError("database rejected row")
    use_case = ImportMedia(
        media_probe=FakeProbe(audio_probe_result(), events),
        media_storage=storage,
        media_assets=FakeMediaAssetRepository(events, add_error=failure),
    )

    with pytest.raises(RuntimeError) as captured:
        use_case.execute(source=Path("recording.wav"), project_id=uuid4())

    assert captured.value is failure
    assert events == ["store", "open", "probe", "persist", "get", "discard"]
    assert not storage.imported


def test_failed_compensation_reports_an_explicit_rollback_error() -> None:
    events: list[str] = []
    use_case = ImportMedia(
        media_probe=FakeProbe(audio_probe_result(), events),
        media_storage=FakeStorage(events, rollback_fails=True),
        media_assets=FakeMediaAssetRepository(
            events,
            add_error=RuntimeError("database rejected row"),
        ),
    )

    with pytest.raises(MediaImportRollbackError) as captured:
        use_case.execute(source=Path("recording.wav"), project_id=uuid4())

    assert "could not be discarded safely" in str(captured.value)
    assert isinstance(captured.value.__cause__, OSError)
    assert events == ["store", "open", "probe", "persist", "get", "discard"]


def test_post_commit_exception_reconciles_equivalent_row_and_keeps_original() -> None:
    events: list[str] = []
    storage = FakeStorage(events)
    repository = FakeMediaAssetRepository(
        events,
        add_error=RuntimeError("connection dropped after commit"),
        commit_before_raise=True,
    )

    result = ImportMedia(
        media_probe=FakeProbe(audio_probe_result(), events),
        media_storage=storage,
        media_assets=repository,
    ).execute(source=Path("recording.wav"), project_id=uuid4())

    assert repository.added == result.media_asset
    assert storage.imported
    assert events == ["store", "open", "probe", "persist", "get"]


def test_unknown_persistence_outcome_keeps_original_and_raises_typed_error() -> None:
    events: list[str] = []
    storage = FakeStorage(events)
    repository = FakeMediaAssetRepository(
        events,
        add_error=RuntimeError("database connection dropped"),
        get_error=RuntimeError("database remains unavailable"),
    )

    with pytest.raises(MediaImportOutcomeUncertainError) as captured:
        ImportMedia(
            media_probe=FakeProbe(audio_probe_result(), events),
            media_storage=storage,
            media_assets=repository,
        ).execute(source=Path("recording.wav"), project_id=uuid4())

    assert "original was preserved" in str(captured.value)
    assert storage.imported
    assert events == ["store", "open", "probe", "persist", "get"]


def test_base_exception_is_not_caught_for_destructive_compensation() -> None:
    events: list[str] = []
    storage = FakeStorage(events)

    with pytest.raises(KeyboardInterrupt):
        ImportMedia(
            media_probe=FakeProbe(audio_probe_result(), events),
            media_storage=storage,
            media_assets=FakeMediaAssetRepository(
                events,
                add_error=KeyboardInterrupt(),
            ),
        ).execute(source=Path("recording.wav"), project_id=uuid4())

    assert storage.imported
    assert "discard" not in events
