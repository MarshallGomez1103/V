"""Tests for immutable original-media filesystem storage."""

from __future__ import annotations

import hashlib
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest

from voz.application.ports.media_storage import (
    MediaStorageError,
    MediaStorageErrorCode,
    MediaStoragePort,
)
from voz.infrastructure.media_storage import FileSystemMediaStorage


def test_import_copies_hashes_and_makes_original_read_only(tmp_path: Path) -> None:
    source = tmp_path / "incoming" / "Clase final.m4a"
    source.parent.mkdir()
    payload = (b"audio bytes\x00" * 100_000) + b"tail"
    source.write_bytes(payload)
    source_mode = stat.S_IMODE(source.stat().st_mode)
    project_id = uuid4()
    media_asset_id = uuid4()
    storage = FileSystemMediaStorage(tmp_path / "data")

    result = storage.import_original(
        source=source,
        project_id=project_id,
        media_asset_id=media_asset_id,
        media_type="audio/mp4",
    )

    stored = storage.original_path_for(project_id, media_asset_id)
    assert result.media_asset.id == media_asset_id
    assert result.media_asset.project_id == project_id
    assert result.media_asset.display_name == source.name
    assert result.media_asset.content_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.media_asset.size_bytes == len(payload)
    assert result.media_asset.media_type == "audio/mp4"
    assert result.bytes_copied == len(payload)
    assert stored.read_bytes() == payload
    assert stat.S_IMODE(stored.stat().st_mode) == 0o444
    assert source.read_bytes() == payload
    assert stat.S_IMODE(source.stat().st_mode) == source_mode
    assert stored.name == f"{media_asset_id}.original"
    assert source.name not in stored.parts


def test_adapter_satisfies_media_storage_port(tmp_path: Path) -> None:
    assert isinstance(FileSystemMediaStorage(tmp_path / "data"), MediaStoragePort)


def test_original_can_be_reopened_by_identity_and_discarded_idempotently(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.wav"
    payload = b"immutable original bytes"
    source.write_bytes(payload)
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    storage.import_original(
        source=source,
        project_id=project_id,
        media_asset_id=media_asset_id,
    )

    with storage.open_original(
        project_id=project_id,
        media_asset_id=media_asset_id,
    ) as original:
        assert original.read() == payload

    storage.discard_original(
        project_id=project_id,
        media_asset_id=media_asset_id,
    )
    storage.discard_original(
        project_id=project_id,
        media_asset_id=media_asset_id,
    )
    assert not storage.original_path_for(project_id, media_asset_id).exists()


def test_open_missing_original_returns_a_path_safe_typed_error(tmp_path: Path) -> None:
    storage_root = tmp_path / "private" / "data"
    storage = FileSystemMediaStorage(storage_root)

    with pytest.raises(MediaStorageError) as raised:
        storage.open_original(project_id=uuid4(), media_asset_id=uuid4())

    assert raised.value.code is MediaStorageErrorCode.ORIGINAL_NOT_FOUND
    assert str(tmp_path) not in str(raised.value)
    assert not storage_root.exists()


def test_discard_missing_original_is_idempotent_without_creating_storage(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "private" / "data"
    storage = FileSystemMediaStorage(storage_root)

    storage.discard_original(project_id=uuid4(), media_asset_id=uuid4())

    assert not storage_root.exists()


def test_existing_destination_is_never_replaced(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"new bytes")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    destination = storage.original_path_for(project_id, media_asset_id)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing original")

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.DESTINATION_EXISTS
    assert destination.read_bytes() == b"existing original"
    assert not list(destination.parent.glob(".import-*.tmp"))


def test_concurrent_import_publishes_exactly_once(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    payload = b"race-safe audio" * 100_000
    source.write_bytes(payload)
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()

    def import_once() -> MediaStorageErrorCode | None:
        try:
            storage.import_original(
                source=source,
                project_id=project_id,
                media_asset_id=media_asset_id,
            )
        except MediaStorageError as error:
            return error.code
        return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(import_once)
        second = executor.submit(import_once)
        outcomes = [first.result(), second.result()]

    assert outcomes.count(None) == 1
    assert outcomes.count(MediaStorageErrorCode.DESTINATION_EXISTS) == 1
    destination = storage.original_path_for(project_id, media_asset_id)
    assert destination.read_bytes() == payload
    assert not list(destination.parent.glob(".import-*.tmp"))


def test_source_equal_to_destination_is_rejected_without_modification(
    tmp_path: Path,
) -> None:
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    destination = storage.original_path_for(project_id, media_asset_id)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"same inode")

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=destination,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.SOURCE_EQUALS_DESTINATION
    assert destination.read_bytes() == b"same inode"


def test_source_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "actual.wav"
    source.write_bytes(b"private media")
    symlink = tmp_path / "selected.wav"
    symlink.symlink_to(source)
    storage = FileSystemMediaStorage(tmp_path / "data")

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=symlink,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.SOURCE_IS_SYMLINK
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    "source_name",
    [
        "   ",
        "unsafe\\name.wav",
        "line\nbreak.wav",
        "control\x01name.wav",
        "bidi\u202ename.wav",
        "isolate\u2066name.wav",
    ],
)
def test_unsafe_display_name_is_rejected_before_storage_is_created(
    tmp_path: Path,
    source_name: str,
) -> None:
    if os.name == "nt" and (
        not source_name.strip() or any(c in source_name for c in "\\\n\x01")
    ):
        pytest.skip("Windows cannot create a file with this name")
    source = tmp_path / source_name
    source.write_bytes(b"bytes")
    storage_root = tmp_path / "data"

    with pytest.raises(MediaStorageError) as raised:
        FileSystemMediaStorage(storage_root).import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.UNSAFE_DISPLAY_NAME
    assert not storage_root.exists()


def test_nul_display_name_is_rejected_before_source_is_inspected(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "data"

    with pytest.raises(MediaStorageError) as raised:
        FileSystemMediaStorage(storage_root).import_original(
            source=tmp_path / "nul\x00name.wav",
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.UNSAFE_DISPLAY_NAME
    assert not storage_root.exists()


def test_directory_and_empty_file_are_rejected(tmp_path: Path) -> None:
    storage = FileSystemMediaStorage(tmp_path / "data")
    empty = tmp_path / "empty.wav"
    empty.touch()

    for source in (tmp_path, empty):
        with pytest.raises(MediaStorageError) as raised:
            storage.import_original(
                source=source,
                project_id=uuid4(),
                media_asset_id=uuid4(),
            )
        assert raised.value.code is MediaStorageErrorCode.SOURCE_NOT_REGULAR


def test_missing_source_error_does_not_expose_host_path(tmp_path: Path) -> None:
    source = tmp_path / "secret" / "missing.wav"

    with pytest.raises(MediaStorageError) as raised:
        FileSystemMediaStorage(tmp_path / "data").import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.SOURCE_NOT_FOUND
    assert str(tmp_path) not in str(raised.value)


def test_invalid_metadata_does_not_publish_or_leave_temporary_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()

    with pytest.raises(ValueError, match="media_type"):
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
            media_type="not-a-media-type",
        )

    destination = storage.original_path_for(project_id, media_asset_id)
    assert not destination.exists()
    assert not list(destination.parent.glob(".import-*.tmp"))


def test_symlinked_storage_component_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    outside = tmp_path / "outside"
    outside.mkdir()
    storage_root = tmp_path / "data"
    storage_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(MediaStorageError) as raised:
        FileSystemMediaStorage(storage_root).import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.UNSAFE_STORAGE_PATH
    assert not list(outside.rglob("*.original"))


@pytest.mark.parametrize("symlink_component", ["projects", "project", "originals"])
def test_symlink_in_uuid_storage_chain_is_rejected(
    tmp_path: Path,
    symlink_component: str,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    project_id = uuid4()
    storage_root = tmp_path / "data"
    outside = tmp_path / "outside"
    outside.mkdir()

    if symlink_component == "projects":
        storage_root.mkdir()
        (storage_root / "projects").symlink_to(outside, target_is_directory=True)
    elif symlink_component == "project":
        (storage_root / "projects").mkdir(parents=True)
        (storage_root / "projects" / str(project_id)).symlink_to(
            outside,
            target_is_directory=True,
        )
    else:
        project_root = storage_root / "projects" / str(project_id)
        project_root.mkdir(parents=True)
        (project_root / "originals").symlink_to(outside, target_is_directory=True)

    with pytest.raises(MediaStorageError) as raised:
        FileSystemMediaStorage(storage_root).import_original(
            source=source,
            project_id=project_id,
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.UNSAFE_STORAGE_PATH
    assert not list(outside.rglob("*.original"))


def test_storage_root_identity_is_verified_after_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage_root = tmp_path / "data"
    storage_root.mkdir()
    substituted_root = tmp_path / "substituted"
    substituted_root.mkdir()
    real_open = os.open

    def substitute_root_fd(
        path: str | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(path) == storage_root and dir_fd is None:
            return real_open(substituted_root, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr("voz.infrastructure.media_storage.os.open", substitute_root_fd)

    with pytest.raises(MediaStorageError) as raised:
        FileSystemMediaStorage(storage_root).import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.UNSAFE_STORAGE_PATH
    assert not (substituted_root / "projects").exists()


def test_import_fsyncs_directory_after_publish_and_temporary_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    events: list[str] = []
    real_fsync = os.fsync
    real_link = os.link
    real_unlink = os.unlink
    real_fstat = os.fstat

    def record_fsync(fd: int) -> None:
        if stat.S_ISDIR(real_fstat(fd).st_mode):
            events.append("directory-fsync")
        real_fsync(fd)

    def record_link(
        source_name: str,
        destination_name: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        events.append("link")
        real_link(
            source_name,
            destination_name,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    def record_unlink(path: str, *, dir_fd: int | None = None) -> None:
        if path.startswith(".import-"):
            events.append("temporary-unlink")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr("voz.infrastructure.media_storage.os.fsync", record_fsync)
    monkeypatch.setattr("voz.infrastructure.media_storage.os.link", record_link)
    monkeypatch.setattr("voz.infrastructure.media_storage.os.unlink", record_unlink)

    storage.import_original(
        source=source,
        project_id=uuid4(),
        media_asset_id=uuid4(),
    )

    assert events == [
        "directory-fsync",
        "directory-fsync",
        "directory-fsync",
        "link",
        "directory-fsync",
        "temporary-unlink",
        "directory-fsync",
    ]


def test_source_fd_is_closed_and_error_is_typed_when_fstat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    real_open = os.open
    real_fstat = os.fstat
    source_fd: int | None = None

    def capture_source_fd(
        path: str | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal source_fd
        opened_fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if Path(path) == source and dir_fd is None:
            source_fd = opened_fd
        return opened_fd

    def fail_for_source(fd: int) -> os.stat_result:
        if source_fd is not None and fd == source_fd:
            raise OSError("synthetic source fstat failure")
        return real_fstat(fd)

    monkeypatch.setattr("voz.infrastructure.media_storage.os.open", capture_source_fd)
    monkeypatch.setattr("voz.infrastructure.media_storage.os.fstat", fail_for_source)

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert str(tmp_path) not in str(raised.value)
    assert source_fd is not None
    with pytest.raises(OSError):
        real_fstat(source_fd)


def test_source_fd_is_closed_when_fstat_is_interrupted_by_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ImportInterrupted(BaseException):
        pass

    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    real_open = os.open
    real_fstat = os.fstat
    source_fd: int | None = None

    def capture_source_fd(
        path: str | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal source_fd
        opened_fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if Path(path) == source and dir_fd is None:
            source_fd = opened_fd
        return opened_fd

    def interrupt_for_source(fd: int) -> os.stat_result:
        if source_fd is not None and fd == source_fd:
            raise ImportInterrupted
        return real_fstat(fd)

    monkeypatch.setattr("voz.infrastructure.media_storage.os.open", capture_source_fd)
    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.fstat",
        interrupt_for_source,
    )

    with pytest.raises(ImportInterrupted):
        storage.import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id=uuid4(),
        )

    assert source_fd is not None
    with pytest.raises(OSError):
        real_fstat(source_fd)


def test_temporary_fd_is_closed_and_error_is_typed_when_fdopen_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    temporary_fd: int | None = None
    real_fstat = os.fstat

    def fail_fdopen(
        fd: int,
        mode: str = "r",
        buffering: int = -1,
        *,
        closefd: bool = True,
    ) -> BinaryIO:
        del mode, buffering, closefd
        nonlocal temporary_fd
        temporary_fd = fd
        raise OSError("synthetic temporary fdopen failure")

    monkeypatch.setattr("voz.infrastructure.media_storage.os.fdopen", fail_fdopen)

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert str(tmp_path) not in str(raised.value)
    assert temporary_fd is not None
    with pytest.raises(OSError):
        real_fstat(temporary_fd)
    destination = storage.original_path_for(project_id, media_asset_id)
    assert not destination.exists()
    assert not list(destination.parent.glob(".import-*.tmp"))


def test_temporary_fd_is_closed_when_fdopen_is_interrupted_by_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ImportInterrupted(BaseException):
        pass

    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    temporary_fd: int | None = None
    real_fstat = os.fstat

    def interrupt_fdopen(
        fd: int,
        mode: str = "r",
        buffering: int = -1,
        *,
        closefd: bool = True,
    ) -> BinaryIO:
        del mode, buffering, closefd
        nonlocal temporary_fd
        temporary_fd = fd
        raise ImportInterrupted

    monkeypatch.setattr("voz.infrastructure.media_storage.os.fdopen", interrupt_fdopen)

    with pytest.raises(ImportInterrupted):
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert temporary_fd is not None
    with pytest.raises(OSError):
        real_fstat(temporary_fd)
    destination = storage.original_path_for(project_id, media_asset_id)
    assert not destination.exists()
    assert not list(destination.parent.glob(".import-*.tmp"))


def test_temporary_is_made_read_only_before_file_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    events: list[str] = []
    real_fchmod = os.fchmod
    real_fsync = os.fsync
    real_fstat = os.fstat

    def record_fchmod(fd: int, mode: int) -> None:
        events.append("fchmod")
        real_fchmod(fd, mode)

    def record_fsync(fd: int) -> None:
        if stat.S_ISREG(real_fstat(fd).st_mode):
            events.append("file-fsync")
        real_fsync(fd)

    monkeypatch.setattr("voz.infrastructure.media_storage.os.fchmod", record_fchmod)
    monkeypatch.setattr("voz.infrastructure.media_storage.os.fsync", record_fsync)

    storage.import_original(
        source=source,
        project_id=uuid4(),
        media_asset_id=uuid4(),
    )

    assert events[:2] == ["fchmod", "file-fsync"]


def test_publish_fsync_failure_rolls_back_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    real_fsync = os.fsync
    real_fstat = os.fstat
    directory_fsync_calls = 0

    def fail_first_directory_fsync(fd: int) -> None:
        nonlocal directory_fsync_calls
        if stat.S_ISDIR(real_fstat(fd).st_mode):
            directory_fsync_calls += 1
            if directory_fsync_calls == 4:
                raise OSError("synthetic publication fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.fsync",
        fail_first_directory_fsync,
    )

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert "was rolled back" in str(raised.value)
    destination = storage.original_path_for(project_id, media_asset_id)
    assert not destination.exists()
    assert not list(destination.parent.glob(".import-*.tmp"))
    assert directory_fsync_calls == 6


def test_publish_reports_when_rollback_cannot_be_confirmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "private" / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    destination_name = f"{media_asset_id}.original"
    real_fsync = os.fsync
    real_fstat = os.fstat
    real_unlink = os.unlink
    directory_fsync_calls = 0

    def fail_first_directory_fsync(fd: int) -> None:
        nonlocal directory_fsync_calls
        if stat.S_ISDIR(real_fstat(fd).st_mode):
            directory_fsync_calls += 1
            if directory_fsync_calls == 4:
                raise OSError("synthetic publication fsync failure")
        real_fsync(fd)

    def fail_destination_rollback(
        path: str,
        *,
        dir_fd: int | None = None,
    ) -> None:
        if path == destination_name:
            raise OSError("synthetic rollback unlink failure")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.fsync",
        fail_first_directory_fsync,
    )
    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.unlink",
        fail_destination_rollback,
    )

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert str(raised.value) == (
        "The original publication failed and rollback could not be confirmed."
    )
    assert str(tmp_path) not in str(raised.value)
    destination = storage.original_path_for(project_id, media_asset_id)
    assert destination.exists()
    assert not list(destination.parent.glob(".import-*.tmp"))


def test_discard_fsync_failure_is_typed_and_reports_post_unlink_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "private" / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    storage.import_original(
        source=source,
        project_id=project_id,
        media_asset_id=media_asset_id,
    )
    real_fstat = os.fstat

    def fail_directory_fsync(fd: int) -> None:
        if stat.S_ISDIR(real_fstat(fd).st_mode):
            raise OSError("synthetic discard fsync failure")

    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.fsync",
        fail_directory_fsync,
    )

    with pytest.raises(MediaStorageError) as raised:
        storage.discard_original(
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert "was removed" in str(raised.value)
    assert "durability could not be confirmed" in str(raised.value)
    assert str(tmp_path) not in str(raised.value)
    assert not storage.original_path_for(project_id, media_asset_id).exists()


def test_temporary_cleanup_failure_does_not_hide_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    real_unlink = os.unlink

    def fail_temporary_unlink(
        path: str,
        *,
        dir_fd: int | None = None,
    ) -> None:
        if path.startswith(".import-"):
            raise OSError("synthetic temporary cleanup failure")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.unlink",
        fail_temporary_unlink,
    )

    with pytest.raises(ValueError, match="media_type") as raised:
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
            media_type="not-a-media-type",
        )

    assert raised.value.__notes__ == [
        "Additional media-storage cleanup failure: Temporary original cleanup "
        "failed after the failed import."
    ]
    destination = storage.original_path_for(project_id, media_asset_id)
    assert not destination.exists()
    assert len(list(destination.parent.glob(".import-*.tmp"))) == 1


def test_temporary_cleanup_failure_after_publish_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "private" / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    real_unlink = os.unlink

    def fail_temporary_unlink(
        path: str,
        *,
        dir_fd: int | None = None,
    ) -> None:
        if path.startswith(".import-"):
            raise OSError("synthetic temporary cleanup failure")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(
        "voz.infrastructure.media_storage.os.unlink",
        fail_temporary_unlink,
    )

    with pytest.raises(MediaStorageError) as raised:
        storage.import_original(
            source=source,
            project_id=project_id,
            media_asset_id=media_asset_id,
        )

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert str(raised.value) == ("Temporary original cleanup failed after publication.")
    assert str(tmp_path) not in str(raised.value)
    destination = storage.original_path_for(project_id, media_asset_id)
    assert destination.exists()
    assert len(list(destination.parent.glob(".import-*.tmp"))) == 1


def test_open_original_closes_fd_when_fstat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    storage.import_original(
        source=source,
        project_id=project_id,
        media_asset_id=media_asset_id,
    )
    stored_stat = storage.original_path_for(project_id, media_asset_id).stat()
    real_fstat = os.fstat
    failed_fd: int | None = None

    def fail_for_original(fd: int) -> os.stat_result:
        nonlocal failed_fd
        current_stat = real_fstat(fd)
        if os.path.samestat(current_stat, stored_stat):
            failed_fd = fd
            raise OSError("synthetic fstat failure")
        return current_stat

    monkeypatch.setattr("voz.infrastructure.media_storage.os.fstat", fail_for_original)

    with pytest.raises(MediaStorageError) as raised:
        storage.open_original(project_id=project_id, media_asset_id=media_asset_id)

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert failed_fd is not None
    with pytest.raises(OSError):
        real_fstat(failed_fd)


def test_open_original_closes_fd_when_fdopen_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    media_asset_id = uuid4()
    storage.import_original(
        source=source,
        project_id=project_id,
        media_asset_id=media_asset_id,
    )
    failed_fd: int | None = None
    real_fstat = os.fstat

    def fail_fdopen(
        fd: int,
        mode: str = "r",
        buffering: int = -1,
        *,
        closefd: bool = True,
    ) -> BinaryIO:
        del mode, buffering, closefd
        nonlocal failed_fd
        failed_fd = fd
        raise OSError("synthetic fdopen failure")

    monkeypatch.setattr("voz.infrastructure.media_storage.os.fdopen", fail_fdopen)

    with pytest.raises(MediaStorageError) as raised:
        storage.open_original(project_id=project_id, media_asset_id=media_asset_id)

    assert raised.value.code is MediaStorageErrorCode.IO_ERROR
    assert failed_fd is not None
    with pytest.raises(OSError):
        real_fstat(failed_fd)


def test_identity_parameters_must_be_uuids(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    storage = FileSystemMediaStorage(tmp_path / "data")

    with pytest.raises(TypeError, match="project_id must be a UUID"):
        storage.import_original(
            source=source,
            project_id="../escape",  # type: ignore[arg-type]
            media_asset_id=uuid4(),
        )
    with pytest.raises(TypeError, match="media_asset_id must be a UUID"):
        storage.import_original(
            source=source,
            project_id=uuid4(),
            media_asset_id="../escape",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="project_id must be a UUID"):
        storage.open_original(
            project_id="../escape",  # type: ignore[arg-type]
            media_asset_id=uuid4(),
        )
    with pytest.raises(TypeError, match="media_asset_id must be a UUID"):
        storage.discard_original(
            project_id=uuid4(),
            media_asset_id="../escape",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="project_id must be a UUID"):
        storage.original_path_for(
            "../escape",  # type: ignore[arg-type]
            uuid4(),
        )

    assert not (tmp_path / "data").exists()
