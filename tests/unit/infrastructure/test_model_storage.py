"""Tests for explicit, pinned local model installation."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock

import pytest

from voz.application.ports.model_installation import (
    ModelInstallation,
    ModelInstallationError,
    ModelInstallationFailureCode,
)
from voz.application.ports.transcription import TranscriptionError
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.model_storage import FileSystemModelStore


def _descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="fixture",
        display_name="Fixture model",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
        source="example/faster-whisper-fixture",
        revision="0123456789abcdef0123456789abcdef01234567",
    )


def test_install_requires_confirmation_before_constructing_downloader(
    tmp_path: Path,
) -> None:
    constructed = False

    def factory():  # type: ignore[no-untyped-def]
        nonlocal constructed
        constructed = True
        raise AssertionError

    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=factory,
    )

    with pytest.raises(ModelInstallationError) as raised:
        store.install(_descriptor(), confirmed=False)

    assert raised.value.code is ModelInstallationFailureCode.CONFIRMATION_REQUIRED
    assert not constructed


def test_install_records_exact_source_and_revision_outside_checkout(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "remote-snapshot"
    snapshot.mkdir()
    (snapshot / "model.bin").write_bytes(b"weights")
    calls: list[dict[str, object]] = []

    def download(**kwargs: object) -> str:
        calls.append(kwargs)
        return str(snapshot)

    installed_at = datetime(2026, 9, 5, tzinfo=UTC)
    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: download,
        clock=lambda: installed_at,
    )
    descriptor = _descriptor()

    installation = store.install(descriptor, confirmed=True)
    resolved = store.resolve_path(descriptor)

    assert installation.descriptor is descriptor
    assert installation.installed_at == installed_at
    assert calls == [
        {
            "repo_id": descriptor.source,
            "revision": descriptor.revision,
            "cache_dir": str((tmp_path / "cache" / "downloads").absolute()),
            "local_files_only": False,
        }
    ]
    assert resolved.is_relative_to((tmp_path / "data" / "models").absolute())
    assert (resolved / "model.bin").read_bytes() == b"weights"
    manifest = json.loads((resolved / ".voz-model.json").read_text())
    assert manifest["source"] == descriptor.source
    assert manifest["revision"] == descriptor.revision
    assert store.is_installed(descriptor)


def test_resolve_never_downloads_and_rejects_missing_model(tmp_path: Path) -> None:
    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: (_ for _ in ()).throw(AssertionError),
    )

    with pytest.raises(TranscriptionError, match="not installed"):
        store.resolve_path(_descriptor())


def test_install_rejects_unpinned_descriptor(tmp_path: Path) -> None:
    descriptor = ModelDescriptor(
        provider_id="faster-whisper",
        model_id="fixture",
        display_name="Fixture model",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    )
    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
    )

    with pytest.raises(ModelInstallationError) as raised:
        store.install(descriptor, confirmed=True)

    assert raised.value.code is ModelInstallationFailureCode.PROVENANCE_REQUIRED


def test_storage_identity_separates_distinct_model_sources(tmp_path: Path) -> None:
    first_snapshot = tmp_path / "first-snapshot"
    second_snapshot = tmp_path / "second-snapshot"
    first_snapshot.mkdir()
    second_snapshot.mkdir()
    (first_snapshot / "model.bin").write_bytes(b"first")
    (second_snapshot / "model.bin").write_bytes(b"second")
    first = replace(_descriptor(), source="organization-a/model")
    second = replace(_descriptor(), source="organization-b/model")

    def download(**kwargs: object) -> str:
        return str(
            first_snapshot if kwargs["repo_id"] == first.source else second_snapshot
        )

    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: download,
    )
    store.install(first, confirmed=True)
    store.install(second, confirmed=True)

    first_path = store.resolve_path(first)
    second_path = store.resolve_path(second)
    assert first_path != second_path
    assert (first_path / "model.bin").read_bytes() == b"first"
    assert (second_path / "model.bin").read_bytes() == b"second"


def test_reinstall_reuses_durable_installation_timestamp(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "model.bin").write_bytes(b"weights")
    installed_at = datetime(2026, 9, 5, tzinfo=UTC)
    later = datetime(2026, 9, 6, tzinfo=UTC)
    timestamps = iter((installed_at, later))
    download_calls = 0

    def download(**kwargs: object) -> str:
        del kwargs
        nonlocal download_calls
        download_calls += 1
        return str(snapshot)

    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: download,
        clock=lambda: next(timestamps),
    )
    descriptor = _descriptor()

    first = store.install(descriptor, confirmed=True)
    second = store.install(descriptor, confirmed=True)

    assert first.installed_at == installed_at
    assert second.installed_at == installed_at
    assert download_calls == 1


def test_concurrent_installers_reuse_the_winning_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "model.bin").write_bytes(b"weights")
    barrier = Barrier(2)
    calls_lock = Lock()
    download_calls = 0

    def download(**kwargs: object) -> str:
        del kwargs
        nonlocal download_calls
        with calls_lock:
            download_calls += 1
        barrier.wait(timeout=2)
        return str(snapshot)

    def build_store(installed_at: datetime) -> FileSystemModelStore:
        return FileSystemModelStore(
            data_root=tmp_path / "data",
            cache_root=tmp_path / "cache",
            downloader_factory=lambda: download,
            clock=lambda: installed_at,
        )

    stores: tuple[FileSystemModelStore, ...] = tuple(
        build_store(datetime(2026, 9, 5 + offset, tzinfo=UTC)) for offset in (0, 1)
    )
    descriptor = _descriptor()

    def install(store: FileSystemModelStore) -> ModelInstallation:
        return store.install(descriptor, confirmed=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        installations = tuple(executor.map(install, stores))

    assert len({item.installed_at for item in installations}) == 1
    assert download_calls == 2
    assert all(store.is_installed(descriptor) for store in stores)


def _write_manifest(store: FileSystemModelStore, **extra: object) -> ModelDescriptor:
    descriptor = _descriptor()
    directory = store._directory_for(descriptor)  # pyright: ignore[reportPrivateUsage]
    directory.mkdir(parents=True)
    (directory / ".voz-model.json").write_text(
        json.dumps(
            {
                "provider_id": descriptor.provider_id,
                "model_id": descriptor.model_id,
                "display_name": descriptor.display_name,
                "source": descriptor.source,
                "revision": descriptor.revision,
                "installed_at": "2026-01-01T00:00:00+00:00",
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return descriptor


def test_legacy_manifest_without_capabilities_still_reads(tmp_path: Path) -> None:
    store = FileSystemModelStore(data_root=tmp_path / "d", cache_root=tmp_path / "c")
    descriptor = _write_manifest(store)  # pre-V6-01: no "capabilities" key

    assert store.is_installed(descriptor)
    (registered,) = store.registered_descriptors()
    assert registered.identity == descriptor.identity
    assert registered.capabilities == frozenset({ModelCapability.TRANSCRIPTION})


def test_manifest_capabilities_never_come_from_disk(tmp_path: Path) -> None:
    store = FileSystemModelStore(data_root=tmp_path / "d", cache_root=tmp_path / "c")
    _write_manifest(store, capabilities=["synthesis", "wake_word", "unknown"])

    (registered,) = store.registered_descriptors()
    assert registered.capabilities == frozenset({ModelCapability.TRANSCRIPTION})
