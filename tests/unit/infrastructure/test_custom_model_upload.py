from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from voz.application.ports.custom_model_upload import (
    CustomModelUploadFile,
    CustomModelUploadRequest,
)
from voz.application.ports.custom_models import CustomModelError
from voz.infrastructure.custom_model_upload import FileSystemCustomModelUpload


def manifest(**changes: object) -> CustomModelUploadRequest:
    return replace(
        CustomModelUploadRequest(
            engine="faster-whisper",
            family="ctranslate2",
            display_name="My model",
            files=(CustomModelUploadFile("model.bin", 4),),
        ),
        **changes,  # type: ignore[arg-type]
    )


async def chunks(*data: bytes) -> AsyncIterator[bytes]:
    for block in data:
        yield block


def test_streamed_upload_returns_only_opaque_metadata(tmp_path: Path) -> None:
    guard = Mock()
    store = FileSystemCustomModelUpload(tmp_path / "uploads", require_space=guard)
    receipt = store.create(manifest(license="MIT"))
    assert len(receipt.id) == 32
    assert receipt.total_bytes == 4 and receipt.file_count == 1
    assert str(tmp_path) not in repr(receipt)
    guard.assert_called_once_with(4)
    with pytest.raises(CustomModelError, match="not complete"):
        store.request(receipt.id)
    asyncio.run(store.write(receipt.id, 0, chunks(b"ab", b"cd")))
    request = store.request(receipt.id)
    assert request.source_type == "folder" and request.license == "MIT"
    assert (Path(request.source) / "model.bin").read_bytes() == b"abcd"
    assert str(tmp_path) not in repr(request)
    if os.name != "nt":
        assert Path(request.source).stat().st_mode & 0o777 == 0o700
        assert (Path(request.source) / "model.bin").stat().st_mode & 0o777 == 0o600
    store.discard(receipt.id)
    store.discard(receipt.id)
    assert not Path(request.source).exists()


@pytest.mark.parametrize(
    "name",
    [
        "../model.bin",
        "/model.bin",
        "C:/model.bin",
        "a\\model.bin",
        "a/../model.bin",
        "./model.bin",
        "model.bin\x00",
        "model.py",
        "model.pkl",
        "model.pt",
        "espeak-ng-data/../../model.bin",
    ],
)
def test_rejects_unsafe_or_unapproved_names(tmp_path: Path, name: str) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    with pytest.raises(CustomModelError) as failure:
        store.create(manifest(files=(CustomModelUploadFile(name, 1),)))
    assert failure.value.code == "custom_model_invalid"
    assert name not in str(failure.value)
    assert not list((tmp_path / "uploads").glob("*"))


@pytest.mark.parametrize(
    "files",
    [
        (),
        (CustomModelUploadFile("model.bin", 0),),
        (CustomModelUploadFile("model.bin", True),),
        (CustomModelUploadFile("model.bin", 16 * 1024**3 + 1),),
        (CustomModelUploadFile("model.bin", 1), CustomModelUploadFile("model.bin", 1)),
        tuple(CustomModelUploadFile("model.bin", 1) for _ in range(10_001)),
    ],
)
def test_enforces_count_size_and_duplicates(
    tmp_path: Path,
    files: tuple[CustomModelUploadFile, ...],
) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    with pytest.raises(CustomModelError):
        store.create(manifest(files=files))


@pytest.mark.parametrize("data", [(b"abc",), (b"abcde",)])
def test_wrong_actual_size_discards_entire_upload(
    tmp_path: Path, data: tuple[bytes, ...]
) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    receipt = store.create(manifest())
    with pytest.raises(CustomModelError):
        asyncio.run(store.write(receipt.id, 0, chunks(*data)))
    assert not (tmp_path / "uploads" / receipt.id).exists()
    with pytest.raises(CustomModelError) as expired:
        store.request(receipt.id)
    assert expired.value.code == "custom_model_upload_expired"


def test_expired_nested_source_cannot_be_treated_as_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100.0]
    monkeypatch.setattr(
        "voz.infrastructure.custom_model_upload.time.monotonic", lambda: now[0]
    )
    store = FileSystemCustomModelUpload(tmp_path / "uploads", ttl_seconds=10)
    receipt = store.create(manifest())
    asyncio.run(store.write(receipt.id, 0, chunks(b"abcd")))
    source = Path(store.request(receipt.id).source)
    now[0] = 111
    for operation in (
        lambda: store.request(receipt.id),
        lambda: store.hold_source(source / "nested").__enter__(),
    ):
        with pytest.raises(CustomModelError) as failure:
            operation()
        assert failure.value.code == "custom_model_upload_expired"
    assert not source.exists()


def test_discard_and_expiry_are_deferred_until_nested_hold_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100.0]
    monkeypatch.setattr(
        "voz.infrastructure.custom_model_upload.time.monotonic", lambda: now[0]
    )
    store = FileSystemCustomModelUpload(tmp_path / "uploads", ttl_seconds=10)
    receipt = store.create(manifest())
    asyncio.run(store.write(receipt.id, 0, chunks(b"abcd")))
    source = Path(store.request(receipt.id).source)
    with store.hold_source(source / "nested"):
        now[0] = 111
        store.expire()
        store.discard(receipt.id)
        assert (source / "model.bin").read_bytes() == b"abcd"
    assert not source.exists()
    with store.hold_source(tmp_path / "external"):
        pass


def test_stream_abort_cleans_partial_files(tmp_path: Path) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    receipt = store.create(manifest())

    async def interrupted() -> AsyncIterator[bytes]:
        yield b"ab"
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(store.write(receipt.id, 0, interrupted()))
    assert not (tmp_path / "uploads" / receipt.id).exists()


def test_symlink_destination_is_rejected_without_touching_target(
    tmp_path: Path,
) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    receipt = store.create(manifest())
    target = tmp_path / "original"
    target.write_bytes(b"safe")
    (tmp_path / "uploads" / receipt.id / "model.bin").symlink_to(target)
    with pytest.raises(CustomModelError):
        asyncio.run(store.write(receipt.id, 0, chunks(b"abcd")))
    assert target.read_bytes() == b"safe"


def test_space_failure_creates_no_session(tmp_path: Path) -> None:
    guard = Mock(
        side_effect=CustomModelError("insufficient_disk_space", "Not enough space.")
    )
    store = FileSystemCustomModelUpload(tmp_path / "uploads", require_space=guard)
    with pytest.raises(CustomModelError) as failure:
        store.create(manifest())
    assert failure.value.code == "insufficient_disk_space"
    assert not list((tmp_path / "uploads").glob("*"))


def test_close_removes_only_own_sessions_and_defers_held_source(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    first = FileSystemCustomModelUpload(root)
    receipt = first.create(manifest())
    asyncio.run(first.write(receipt.id, 0, chunks(b"abcd")))
    source = Path(first.request(receipt.id).source)
    second = FileSystemCustomModelUpload(root)
    other = second.create(manifest())
    with first.hold(receipt.id):
        first.close()
        assert source.exists()
        assert (root / other.id).exists()
    assert not source.exists()
    assert (root / other.id).exists()
    with pytest.raises(CustomModelError):
        first.create(manifest())
    second.close()


def test_nested_tts_files_and_parent_symlink_rejection(tmp_path: Path) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    receipt = store.create(
        manifest(
            engine="sherpa-onnx-tts",
            family="vits",
            files=(CustomModelUploadFile("espeak-ng-data/nested/voice", 4),),
        )
    )
    asyncio.run(store.write(receipt.id, 0, chunks(b"abcd")))
    source = Path(store.request(receipt.id).source)
    with store.hold_source(source / "espeak-ng-data" / "nested"):
        assert (source / "espeak-ng-data/nested/voice").read_bytes() == b"abcd"
    store.discard(receipt.id)
    second = store.create(
        manifest(
            engine="sherpa-onnx-tts",
            family="vits",
            files=(CustomModelUploadFile("dict/voice.txt", 4),),
        )
    )
    external = tmp_path / "foreign"
    external.mkdir()
    (tmp_path / "uploads" / second.id / "dict").symlink_to(
        external, target_is_directory=True
    )
    with pytest.raises(CustomModelError):
        asyncio.run(store.write(second.id, 0, chunks(b"abcd")))
    assert not list(external.iterdir())


def test_preview_activity_renews_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [100.0]
    monkeypatch.setattr(
        "voz.infrastructure.custom_model_upload.time.monotonic", lambda: now[0]
    )
    store = FileSystemCustomModelUpload(tmp_path / "uploads", ttl_seconds=10)
    receipt = store.create(manifest())
    asyncio.run(store.write(receipt.id, 0, chunks(b"abcd")))
    now[0] = 105
    source = Path(store.request(receipt.id).source)
    now[0] = 111
    store.expire()
    assert source.exists()
    now[0] = 116
    store.expire()
    assert not source.exists()


def test_delete_during_stream_defers_removal_and_aborts_remaining_bytes(
    tmp_path: Path,
) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    receipt = store.create(manifest())

    async def deleted() -> AsyncIterator[bytes]:
        yield b"ab"
        store.discard(receipt.id)
        assert (tmp_path / "uploads" / receipt.id).exists()
        yield b"cd"

    with pytest.raises(CustomModelError) as failure:
        asyncio.run(store.write(receipt.id, 0, deleted()))
    assert failure.value.code == "custom_model_upload_expired"
    assert not (tmp_path / "uploads" / receipt.id).exists()


def test_binary_file_preserves_newlines_and_zero_bytes(tmp_path: Path) -> None:
    store = FileSystemCustomModelUpload(tmp_path / "uploads")
    receipt = store.create(manifest())
    asyncio.run(store.write(receipt.id, 0, chunks(b"\x00\n\r\xff")))
    assert (
        Path(store.request(receipt.id).source) / "model.bin"
    ).read_bytes() == b"\x00\n\r\xff"
