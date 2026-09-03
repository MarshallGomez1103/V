"""Tests for immutable original-media filesystem storage."""

from __future__ import annotations

import hashlib
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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


@pytest.mark.parametrize("source_name", ["   ", "unsafe\\name.wav"])
def test_unsafe_display_name_is_rejected_before_storage_is_created(
    tmp_path: Path,
    source_name: str,
) -> None:
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

    assert not (tmp_path / "data").exists()
