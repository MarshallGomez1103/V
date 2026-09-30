"""Application orchestration for probing, preserving, and persisting media."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

from voz.application.ports.disk_space import (
    DiskLocation,
    DiskSpacePort,
    require_free_space,
)
from voz.application.ports.media_probe import (
    MediaProbePort,
    MediaProbeResult,
    MediaStreamKind,
)
from voz.application.ports.media_storage import MediaStoragePort
from voz.application.ports.repositories import MediaAssetRepository
from voz.domain.entities.media_asset import MediaAsset

_AUDIO_MEDIA_TYPES = {
    "aac": "audio/aac",
    "aiff": "audio/aiff",
    "ape": "audio/ape",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
}
_VIDEO_MEDIA_TYPES = {
    "avi": "video/x-msvideo",
    "mpeg": "video/mpeg",
    "mpegts": "video/mp2t",
    "ogg": "video/ogg",
}
_MP4_FORMATS = frozenset({"3g2", "3gp", "m4a", "mj2", "mov", "mp4"})


@dataclass(frozen=True, slots=True)
class ImportedMedia:
    """Persisted asset plus path-free technical metadata from its probe."""

    media_asset: MediaAsset
    probe_result: MediaProbeResult


class MediaImportRollbackError(RuntimeError):
    """An import failure was followed by an unsuccessful file rollback."""


class MediaImportOutcomeUncertainError(RuntimeError):
    """Persistence failed and its committed outcome cannot be proven safely."""


@dataclass(slots=True)
class ImportMedia:
    """Coordinate media adapters without leaking infrastructure details."""

    media_probe: MediaProbePort
    media_storage: MediaStoragePort
    media_assets: MediaAssetRepository
    id_factory: Callable[[], UUID] = uuid4
    disk_space: DiskSpacePort | None = None

    def execute(self, *, source: Path, project_id: UUID) -> ImportedMedia:
        """Preserve bytes, probe that exact original, then persist metadata."""
        project_id = _require_uuid(project_id, field="project_id")
        media_asset_id = _require_uuid(self.id_factory(), field="id_factory result")

        # A missing/unreadable source is reported by the storage adapter instead.
        with suppress(OSError):
            source_size = Path(source).stat().st_size
            require_free_space(self.disk_space, DiskLocation.ORIGINALS, source_size)

        imported = self.media_storage.import_original(
            source=Path(source),
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

        try:
            with self.media_storage.open_original(
                project_id=project_id,
                media_asset_id=media_asset_id,
            ) as original:
                probe_result = self.media_probe.probe(original)
        except BaseException as probe_error:
            try:
                self._discard_or_raise(project_id, media_asset_id)
            except MediaImportRollbackError as rollback_error:
                if isinstance(probe_error, Exception):
                    raise
                probe_error.add_note(
                    f"Additional media-import rollback failure: {rollback_error}"
                )
                raise probe_error from rollback_error
            raise

        media_type = _media_type_for(probe_result)
        media_asset = replace(
            imported.media_asset,
            duration_ms=probe_result.duration_ms,
            media_type=media_type,
        )

        try:
            self.media_assets.add(media_asset)
        except Exception as persistence_error:
            try:
                persisted = self.media_assets.get(media_asset_id)
            except Exception as reconciliation_error:
                raise MediaImportOutcomeUncertainError(
                    "Media persistence failed and its committed outcome could "
                    "not be determined safely; the original was preserved."
                ) from reconciliation_error

            if persisted == media_asset:
                return ImportedMedia(
                    media_asset=media_asset,
                    probe_result=probe_result,
                )

            if persisted is not None:
                raise MediaImportOutcomeUncertainError(
                    "Media persistence failed and returned conflicting state; "
                    "the original was preserved."
                ) from persistence_error

            self._discard_or_raise(project_id, media_asset_id)
            raise

        return ImportedMedia(media_asset=media_asset, probe_result=probe_result)

    def _discard_or_raise(self, project_id: UUID, media_asset_id: UUID) -> None:
        try:
            self.media_storage.discard_original(
                project_id=project_id,
                media_asset_id=media_asset_id,
            )
        except Exception as rollback_error:
            raise MediaImportRollbackError(
                "Media import failed and its original could not be discarded safely."
            ) from rollback_error


def _require_uuid(value: object, *, field: str) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError(f"{field} must be a UUID")
    return value


def _media_type_for(probe_result: MediaProbeResult) -> str | None:
    """Map only trusted probe identifiers to conservative MIME types."""
    formats = frozenset(probe_result.format_names)
    has_video = any(
        stream.kind is MediaStreamKind.VIDEO and stream.is_decodable
        for stream in probe_result.streams
    )

    if "webm" in formats:
        return "video/webm" if has_video else "audio/webm"
    if "matroska" in formats:
        return "video/x-matroska" if has_video else "audio/x-matroska"
    if formats & _MP4_FORMATS:
        return "video/mp4" if has_video else "audio/mp4"

    known_types = _VIDEO_MEDIA_TYPES if has_video else _AUDIO_MEDIA_TYPES
    return next(
        (
            media_type
            for format_name, media_type in known_types.items()
            if format_name in formats
        ),
        None,
    )


__all__ = [
    "ImportMedia",
    "ImportedMedia",
    "MediaImportOutcomeUncertainError",
    "MediaImportRollbackError",
]
