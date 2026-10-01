"""Aggregated Model Manager catalog and store routing (MODELS-UI-002)."""

from __future__ import annotations

import json
from pathlib import Path

from voz.application.model_keys import model_key
from voz.application.ports.model_installation import CancelCheck, ProgressCallback
from voz.infrastructure.diarization.models import (
    EMBEDDING_FILE,
    EMBEDDING_MODEL,
    SEGMENTATION_ARCHIVE,
    SEGMENTATION_FILE,
    DiarizationModelPaths,
    DiarizationModelStore,
)
from voz.infrastructure.model_registry import (
    DIARIZATION_DESCRIPTOR,
    ManagedModelCatalog,
    RoutingModelStore,
)
from voz.infrastructure.model_storage import FileSystemModelStore


def catalog(*, cpp: bool, sherpa: bool = True) -> ManagedModelCatalog:
    return ManagedModelCatalog(
        whisper_cpp_available=lambda: cpp, diarization_runtime_available=lambda: sherpa
    )


def test_keys_are_unique_even_when_ids_collide_across_providers() -> None:
    entries = catalog(cpp=True).entries()
    keys = [model_key(e.descriptor) for e in entries]

    assert len(keys) == len(set(keys))
    assert {"faster-whisper:small", "whisper-cpp:small"} <= set(keys)
    assert keys[-1] == "diarization:sherpa-default"


def test_whisper_cpp_is_listed_only_with_its_runtime() -> None:
    without = {e.descriptor.provider_id for e in catalog(cpp=False).entries()}
    with_cli = [
        e
        for e in catalog(cpp=True).entries()
        if e.descriptor.provider_id == "whisper-cpp"
    ]

    assert "whisper-cpp" not in without
    assert with_cli
    assert {e.requires for e in with_cli} == {"whisper-cli"}


def test_diarization_entry_carries_size_licenses_and_runtime_flag() -> None:
    (asr,) = {e.kind for e in catalog(cpp=False).entries()} - {"diarization"}
    entry = catalog(cpp=False, sherpa=False).entries()[-1]

    assert asr == "asr"
    assert (entry.kind, entry.requires, entry.runtime_available) == (
        "diarization",
        "diarization",
        False,
    )
    assert sum(f.size_bytes for f in entry.files) == 6_958_444 + 26_530_550
    assert "MIT" in entry.license and "Apache" in entry.license
    assert catalog(cpp=False).entries()[-1].runtime_available is True


def _install_fake_diarization(root: Path) -> None:
    directory = root / "models" / "diarization"
    directory.mkdir(parents=True)
    sizes = {SEGMENTATION_FILE: 3, EMBEDDING_FILE: 4}
    for name, size in sizes.items():
        (directory / name).write_bytes(b"x" * size)
    (directory / ".voz-diarization.json").write_text(
        json.dumps(
            {
                "sources": {
                    SEGMENTATION_ARCHIVE.name: SEGMENTATION_ARCHIVE.sha256,
                    EMBEDDING_MODEL.name: EMBEDDING_MODEL.sha256,
                },
                "files": sizes,
            }
        )
    )


def routing(tmp_path: Path) -> RoutingModelStore:
    return RoutingModelStore(
        FileSystemModelStore(data_root=tmp_path, cache_root=tmp_path / "cache"),
        DiarizationModelStore(data_root=tmp_path),
    )


def test_routing_store_installs_inspects_and_removes_diarization(
    tmp_path: Path,
) -> None:
    store = routing(tmp_path)
    assert store.is_installed(DIARIZATION_DESCRIPTOR) is False
    assert store.disk_usage(DIARIZATION_DESCRIPTOR) is None

    _install_fake_diarization(tmp_path)

    assert store.is_installed(DIARIZATION_DESCRIPTOR) is True
    assert (store.disk_usage(DIARIZATION_DESCRIPTOR) or 0) >= 7
    assert store.remove(DIARIZATION_DESCRIPTOR) >= 7
    assert store.is_installed(DIARIZATION_DESCRIPTOR) is False


def test_routing_store_sends_diarization_downloads_to_its_own_store(
    tmp_path: Path,
) -> None:
    calls: list[tuple[bool, bool]] = []

    class Spy(DiarizationModelStore):
        def install(
            self,
            *,
            progress: ProgressCallback | None = None,
            cancelled: CancelCheck | None = None,
        ) -> DiarizationModelPaths:
            calls.append((progress is not None, cancelled is not None))
            return DiarizationModelPaths(Path("a"), Path("b"))

    store = RoutingModelStore(
        FileSystemModelStore(data_root=tmp_path, cache_root=tmp_path / "cache"),
        Spy(data_root=tmp_path),
    )
    store.download(
        DIARIZATION_DESCRIPTOR,
        (),
        progress=lambda done, total: None,
        cancelled=lambda: False,
    )

    assert calls == [(True, True)]
