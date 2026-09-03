"""Filesystem adapter for immutable project originals."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from voz.application.ports.media_storage import (
    ImportedOriginal,
    MediaStorageError,
    MediaStorageErrorCode,
)
from voz.domain.entities.media_asset import MediaAsset

_COPY_CHUNK_BYTES = 1024 * 1024
_READ_ONLY_MODE = 0o444


class FileSystemMediaStorage:
    """Store originals below a trusted runtime-data root.

    Destination names are derived exclusively from UUIDs. A temporary file is
    fully copied, hashed, flushed and made read-only before an atomic hard-link
    publishes it. Hard-link publication is intentionally non-replacing.
    """

    def __init__(self, storage_root: Path) -> None:
        self._storage_root = Path(storage_root).absolute()

    def import_original(
        self,
        *,
        source: Path,
        project_id: UUID,
        media_asset_id: UUID,
        media_type: str | None = None,
    ) -> ImportedOriginal:
        """Copy and hash ``source`` without ever mutating it."""
        self._require_uuid(project_id, field="project_id")
        self._require_uuid(media_asset_id, field="media_asset_id")
        source_path = Path(source)
        display_name = self._validate_display_name(source_path.name)
        destination = self.original_path_for(project_id, media_asset_id)

        source_fd = self._open_stable_regular_source(source_path)
        directory_fd: int | None = None
        temporary_name: str | None = None
        try:
            source_before = os.fstat(source_fd)
            directory_fd = self._open_originals_directory(project_id)
            self._reject_existing_destination(
                directory_fd=directory_fd,
                destination_name=destination.name,
                source_stat=source_before,
            )
            temporary_name, temporary_fd = self._create_temporary(directory_fd)
            digest, bytes_copied = self._copy_and_hash(
                source_fd=source_fd,
                source_before=source_before,
                temporary_fd=temporary_fd,
            )
            media_asset = MediaAsset(
                project_id=project_id,
                content_sha256=digest,
                display_name=display_name,
                size_bytes=bytes_copied,
                id=media_asset_id,
                media_type=media_type,
            )
            self._publish_without_replacement(
                directory_fd=directory_fd,
                temporary_name=temporary_name,
                destination_name=destination.name,
            )
            return ImportedOriginal(
                media_asset=media_asset,
                bytes_copied=bytes_copied,
            )
        except MediaStorageError:
            raise
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The original could not be stored due to a filesystem error.",
            ) from error
        finally:
            os.close(source_fd)
            if directory_fd is not None:
                if temporary_name is not None:
                    with suppress(OSError):
                        os.unlink(temporary_name, dir_fd=directory_fd)
                os.close(directory_fd)

    def original_path_for(self, project_id: UUID, media_asset_id: UUID) -> Path:
        """Resolve an infrastructure-only path for an original identity."""
        self._require_uuid(project_id, field="project_id")
        self._require_uuid(media_asset_id, field="media_asset_id")
        return (
            self._storage_root
            / "projects"
            / str(project_id)
            / "originals"
            / f"{media_asset_id}.original"
        )

    @staticmethod
    def _require_uuid(value: object, *, field: str) -> None:
        if not isinstance(value, UUID):
            raise TypeError(f"{field} must be a UUID")

    @staticmethod
    def _validate_display_name(name: str) -> str:
        if not name.strip() or name in {".", ".."} or "/" in name or "\\" in name:
            raise MediaStorageError(
                MediaStorageErrorCode.UNSAFE_DISPLAY_NAME,
                "The source filename is not safe to display.",
            )
        return name

    def _open_originals_directory(self, project_id: UUID) -> int:
        """Create and open the UUID-only directory chain without symlinks."""
        try:
            self._storage_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            root_lstat = self._storage_root.lstat()
            if stat.S_ISLNK(root_lstat.st_mode):
                raise OSError("storage root is a symbolic link")
            directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            directory_flags |= getattr(os, "O_DIRECTORY", 0)
            directory_flags |= getattr(os, "O_NOFOLLOW", 0)
            current_fd = os.open(self._storage_root, directory_flags)
            try:
                for component in ("projects", str(project_id), "originals"):
                    with suppress(FileExistsError):
                        os.mkdir(component, mode=0o700, dir_fd=current_fd)
                    next_fd = os.open(component, directory_flags, dir_fd=current_fd)
                    os.close(current_fd)
                    current_fd = next_fd
            except BaseException:
                os.close(current_fd)
                raise
            return current_fd
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.UNSAFE_STORAGE_PATH,
                "The configured media storage path is unsafe.",
            ) from error

    @staticmethod
    def _create_temporary(directory_fd: int) -> tuple[str, int]:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        for _ in range(10):
            name = f".import-{uuid4()}.tmp"
            try:
                return name, os.open(name, flags, 0o600, dir_fd=directory_fd)
            except FileExistsError:
                continue
        raise MediaStorageError(
            MediaStorageErrorCode.IO_ERROR,
            "A unique temporary original could not be created.",
        )

    @staticmethod
    def _open_stable_regular_source(source: Path) -> int:
        try:
            source_lstat = source.lstat()
        except FileNotFoundError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_NOT_FOUND,
                "The selected source file does not exist.",
            ) from error
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The selected source file could not be inspected.",
            ) from error

        if stat.S_ISLNK(source_lstat.st_mode):
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_IS_SYMLINK,
                "Symbolic links cannot be imported as originals.",
            )
        if not stat.S_ISREG(source_lstat.st_mode):
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_NOT_REGULAR,
                "The selected source must be a regular file.",
            )

        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            source_fd = os.open(source, flags)
        except FileNotFoundError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_CHANGED,
                "The selected source changed while the import was starting.",
            ) from error
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_CHANGED,
                "The selected source could not be opened safely.",
            ) from error

        source_fstat = os.fstat(source_fd)
        if not stat.S_ISREG(source_fstat.st_mode) or not os.path.samestat(
            source_lstat,
            source_fstat,
        ):
            os.close(source_fd)
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_CHANGED,
                "The selected source changed while the import was starting.",
            )
        if source_fstat.st_size <= 0:
            os.close(source_fd)
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_NOT_REGULAR,
                "The selected source is empty.",
            )
        return source_fd

    @staticmethod
    def _reject_existing_destination(
        *,
        directory_fd: int,
        destination_name: str,
        source_stat: os.stat_result,
    ) -> None:
        try:
            destination_lstat = os.stat(
                destination_name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The original destination could not be inspected.",
            ) from error

        try:
            destination_stat = os.stat(
                destination_name,
                dir_fd=directory_fd,
                follow_symlinks=True,
            )
        except OSError:
            destination_stat = destination_lstat
        if os.path.samestat(source_stat, destination_stat):
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_EQUALS_DESTINATION,
                "The source is already the selected original destination.",
            )
        raise MediaStorageError(
            MediaStorageErrorCode.DESTINATION_EXISTS,
            "An original already exists for this media identity.",
        )

    @staticmethod
    def _copy_and_hash(
        *,
        source_fd: int,
        source_before: os.stat_result,
        temporary_fd: int,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        bytes_copied = 0
        try:
            with os.fdopen(temporary_fd, "wb", closefd=True) as output:
                while chunk := os.read(source_fd, _COPY_CHUNK_BYTES):
                    output.write(chunk)
                    digest.update(chunk)
                    bytes_copied += len(chunk)
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), _READ_ONLY_MODE)
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The original could not be copied to temporary storage.",
            ) from error

        source_after = os.fstat(source_fd)
        source_changed = (
            not os.path.samestat(source_before, source_after)
            or source_before.st_size != source_after.st_size
            or source_before.st_mtime_ns != source_after.st_mtime_ns
            or source_before.st_ctime_ns != source_after.st_ctime_ns
            or bytes_copied != source_before.st_size
        )
        if source_changed:
            raise MediaStorageError(
                MediaStorageErrorCode.SOURCE_CHANGED,
                "The selected source changed while it was being imported.",
            )
        return digest.hexdigest(), bytes_copied

    @staticmethod
    def _publish_without_replacement(
        *,
        directory_fd: int,
        temporary_name: str,
        destination_name: str,
    ) -> None:
        try:
            os.link(
                temporary_name,
                destination_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.DESTINATION_EXISTS,
                "An original already exists for this media identity.",
            ) from error
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The original could not be published atomically.",
            ) from error


__all__ = ["FileSystemMediaStorage"]
