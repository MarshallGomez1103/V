"""Filesystem adapter for immutable project originals."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import unicodedata
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from voz.application.ports.media_storage import (
    ImportedOriginal,
    MediaStorageError,
    MediaStorageErrorCode,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.infrastructure.safe_fs import (
    BINARY_FLAG,
    DirectoryDurabilityError,
    DirectoryHandle,
    fchmod,
    open_directory_chain,
)

_COPY_CHUNK_BYTES = 1024 * 1024
_READ_ONLY_MODE = 0o444
_UNSAFE_BIDI_CLASSES = frozenset(
    {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"}
)


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
        directory: DirectoryHandle | None = None
        temporary_name: str | None = None
        published = False
        try:
            source_before = os.fstat(source_fd)
            directory = self._create_originals_directory(project_id)
            self._reject_existing_destination(
                directory=directory,
                destination_name=destination.name,
                source_stat=source_before,
            )
            temporary_name, temporary_fd = self._create_temporary(directory)
            digest, bytes_copied = self._copy_and_hash(
                source_fd=source_fd,
                source_before=source_before,
                temporary_fd=temporary_fd,
            )
            if not hasattr(os, "fchmod"):  # Windows < 3.13: read-only by name
                directory.chmod(temporary_name, _READ_ONLY_MODE)
            media_asset = MediaAsset(
                project_id=project_id,
                content_sha256=digest,
                display_name=display_name,
                size_bytes=bytes_copied,
                id=media_asset_id,
                media_type=media_type,
            )
            self._publish_without_replacement(
                directory=directory,
                temporary_name=temporary_name,
                destination_name=destination.name,
            )
            published = True
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
            active_error = sys.exception()
            cleanup_error: MediaStorageError | None = None
            with suppress(OSError):
                os.close(source_fd)
            if directory is not None:
                if temporary_name is not None:
                    try:
                        self._remove_temporary(
                            directory=directory,
                            temporary_name=temporary_name,
                            published=published,
                        )
                    except MediaStorageError as error:
                        cleanup_error = error
                with suppress(OSError):
                    directory.close()
            if cleanup_error is not None:
                if active_error is not None:
                    active_error.add_note(
                        f"Additional media-storage cleanup failure: {cleanup_error}"
                    )
                else:
                    raise cleanup_error

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

    def open_original(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> BinaryIO:
        """Open a stored original without returning its host path to callers."""
        self._require_uuid(project_id, field="project_id")
        self._require_uuid(media_asset_id, field="media_asset_id")
        directory = self._open_existing_originals_directory(project_id)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            try:
                original_fd = directory.open_file(f"{media_asset_id}.original", flags)
            except FileNotFoundError as error:
                raise MediaStorageError(
                    MediaStorageErrorCode.ORIGINAL_NOT_FOUND,
                    "The requested original is not available.",
                ) from error
            except OSError as error:
                raise MediaStorageError(
                    MediaStorageErrorCode.UNSAFE_STORAGE_PATH,
                    "The stored original could not be opened safely.",
                ) from error

            try:
                original_stat = os.fstat(original_fd)
            except OSError as error:
                with suppress(OSError):
                    os.close(original_fd)
                raise MediaStorageError(
                    MediaStorageErrorCode.IO_ERROR,
                    "The stored original could not be inspected.",
                ) from error
            if not stat.S_ISREG(original_stat.st_mode):
                os.close(original_fd)
                raise MediaStorageError(
                    MediaStorageErrorCode.UNSAFE_STORAGE_PATH,
                    "The stored original is not a regular file.",
                )
            try:
                return os.fdopen(original_fd, "rb", closefd=True)
            except (OSError, ValueError) as error:
                with suppress(OSError):
                    os.close(original_fd)
                raise MediaStorageError(
                    MediaStorageErrorCode.IO_ERROR,
                    "The stored original could not be opened for reading.",
                ) from error
        finally:
            directory.close()

    def discard_original(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> None:
        """Idempotently remove an exact UUID-derived original after rollback."""
        self._require_uuid(project_id, field="project_id")
        self._require_uuid(media_asset_id, field="media_asset_id")
        try:
            directory = self._open_existing_originals_directory(project_id)
        except MediaStorageError as error:
            if error.code is MediaStorageErrorCode.ORIGINAL_NOT_FOUND:
                return
            raise
        try:
            try:
                directory.unlink(f"{media_asset_id}.original")
            except FileNotFoundError:
                return
            except OSError as error:
                raise MediaStorageError(
                    MediaStorageErrorCode.IO_ERROR,
                    "The original could not be discarded during rollback.",
                ) from error
            try:
                directory.fsync()
            except OSError as error:
                raise MediaStorageError(
                    MediaStorageErrorCode.IO_ERROR,
                    "The original was removed, but removal durability could not "
                    "be confirmed.",
                ) from error
        finally:
            directory.close()

    @staticmethod
    def _require_uuid(value: object, *, field: str) -> None:
        if not isinstance(value, UUID):
            raise TypeError(f"{field} must be a UUID")

    @staticmethod
    def _validate_display_name(name: str) -> str:
        contains_unsafe_control = any(
            unicodedata.category(character) in {"Cc", "Cf"}
            or unicodedata.bidirectional(character) in _UNSAFE_BIDI_CLASSES
            for character in name
        )
        if (
            not name.strip()
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or contains_unsafe_control
        ):
            raise MediaStorageError(
                MediaStorageErrorCode.UNSAFE_DISPLAY_NAME,
                "The source filename is not safe to display.",
            )
        return name

    def _create_originals_directory(self, project_id: UUID) -> DirectoryHandle:
        """Create and open the UUID-only directory chain durably."""
        return self._open_originals_directory(project_id, create=True)

    def _open_existing_originals_directory(self, project_id: UUID) -> DirectoryHandle:
        """Open the UUID-only directory chain without creating it."""
        return self._open_originals_directory(project_id, create=False)

    def _open_originals_directory(
        self, project_id: UUID, *, create: bool
    ) -> DirectoryHandle:
        """Open a UUID-only directory chain without following symlinks."""
        try:
            return open_directory_chain(
                self._storage_root,
                ("projects", str(project_id), "originals"),
                create=create,
                durable=True,
            )
        except DirectoryDurabilityError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The media storage directory could not be created durably.",
            ) from error
        except FileNotFoundError as error:
            if create:
                raise MediaStorageError(
                    MediaStorageErrorCode.UNSAFE_STORAGE_PATH,
                    "The configured media storage path is unsafe.",
                ) from error
            raise MediaStorageError(
                MediaStorageErrorCode.ORIGINAL_NOT_FOUND,
                "The requested original is not available.",
            ) from error
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.UNSAFE_STORAGE_PATH,
                "The configured media storage path is unsafe.",
            ) from error

    @staticmethod
    def _create_temporary(directory: DirectoryHandle) -> tuple[str, int]:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        for _ in range(10):
            name = f".import-{uuid4()}.tmp"
            try:
                return name, directory.open_file(name, flags, 0o600)
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

        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | BINARY_FLAG
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

        try:
            source_fstat = os.fstat(source_fd)
        except OSError as error:
            with suppress(OSError):
                os.close(source_fd)
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The selected source could not be inspected after opening.",
            ) from error
        except BaseException:
            with suppress(OSError):
                os.close(source_fd)
            raise
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
        directory: DirectoryHandle,
        destination_name: str,
        source_stat: os.stat_result,
    ) -> None:
        try:
            destination_lstat = directory.stat(destination_name, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The original destination could not be inspected.",
            ) from error

        try:
            destination_stat = directory.stat(destination_name, follow_symlinks=True)
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
            try:
                output = os.fdopen(temporary_fd, "wb", closefd=True)
            except (OSError, ValueError) as error:
                with suppress(OSError):
                    os.close(temporary_fd)
                raise MediaStorageError(
                    MediaStorageErrorCode.IO_ERROR,
                    "The temporary original could not be opened for writing.",
                ) from error
            except BaseException:
                with suppress(OSError):
                    os.close(temporary_fd)
                raise
            with output:
                while chunk := os.read(source_fd, _COPY_CHUNK_BYTES):
                    output.write(chunk)
                    digest.update(chunk)
                    bytes_copied += len(chunk)
                output.flush()
                fchmod(output.fileno(), _READ_ONLY_MODE)
                os.fsync(output.fileno())
        except MediaStorageError:
            raise
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
        directory: DirectoryHandle,
        temporary_name: str,
        destination_name: str,
    ) -> None:
        try:
            directory.link(temporary_name, destination_name)
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

        try:
            directory.fsync()
        except OSError as publish_error:
            rollback_confirmed = True
            try:
                directory.unlink(destination_name)
            except FileNotFoundError:
                pass
            except OSError:
                rollback_confirmed = False
            try:
                directory.fsync()
            except OSError:
                rollback_confirmed = False

            if not rollback_confirmed:
                raise MediaStorageError(
                    MediaStorageErrorCode.IO_ERROR,
                    "The original publication failed and rollback could not be "
                    "confirmed.",
                ) from publish_error
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The original publication failed and was rolled back.",
            ) from publish_error

    @staticmethod
    def _remove_temporary(
        *,
        directory: DirectoryHandle,
        temporary_name: str,
        published: bool,
    ) -> None:
        try:
            directory.unlink(temporary_name)
        except FileNotFoundError:
            return
        except OSError as error:
            state = "after publication" if published else "after the failed import"
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                f"Temporary original cleanup failed {state}.",
            ) from error

        try:
            directory.fsync()
        except OSError as error:
            raise MediaStorageError(
                MediaStorageErrorCode.IO_ERROR,
                "The temporary original was removed, but cleanup durability could "
                "not be confirmed.",
            ) from error


__all__ = ["FileSystemMediaStorage"]
