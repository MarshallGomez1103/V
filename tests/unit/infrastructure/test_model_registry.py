"""Aggregated Model Manager catalog and store routing (MODELS-UI-002)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from voz.application.model_keys import model_key
from voz.application.ports.model_installation import CancelCheck, ProgressCallback
from voz.domain.entities.model_descriptor import ModelCapability
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
    ENGINE_CAPABILITIES,
    ManagedModelCatalog,
    RoutingModelStore,
    undeclarable_capabilities,
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
    assert "MIT" in entry.license and "CC-BY-4.0" in entry.license
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


def test_no_entry_declares_a_capability_without_an_engine_behind_it() -> None:
    entries = catalog(cpp=True).entries()

    assert {e.descriptor.provider_id for e in entries} <= set(ENGINE_CAPABILITIES)
    assert [
        (model_key(e.descriptor), sorted(undeclarable_capabilities(e.descriptor)))
        for e in entries
        if undeclarable_capabilities(e.descriptor)
    ] == []


def test_capabilities_without_an_engine_are_not_implemented_by_any_provider() -> None:
    implemented = {c for caps in ENGINE_CAPABILITIES.values() for c in caps}

    # No TTS, wake-word or standalone aligner engine is registered yet (ADR-0010).
    assert not implemented & {
        ModelCapability.SYNTHESIS,
        ModelCapability.WAKE_WORD,
        ModelCapability.ALIGNMENT,
    }


def test_the_invariant_rejects_an_undeclarable_capability() -> None:
    fake = replace(
        DIARIZATION_DESCRIPTOR,
        capabilities=frozenset({ModelCapability.SYNTHESIS, ModelCapability.CPU}),
    )

    assert undeclarable_capabilities(fake) == {ModelCapability.SYNTHESIS}
    assert undeclarable_capabilities(replace(fake, provider_id="unregistered")) == set(
        fake.capabilities
    )


def test_catalog_entries_declare_the_capabilities_of_their_family() -> None:
    by_provider = {
        e.descriptor.provider_id: e.descriptor.capabilities
        for e in catalog(cpp=True).entries()
    }

    assert ModelCapability.TRANSCRIPTION in by_provider["faster-whisper"]
    assert ModelCapability.TRANSCRIPTION in by_provider["whisper-cpp"]
    assert ModelCapability.DIARIZATION in by_provider["diarization"]
    assert ModelCapability.TRANSCRIPTION not in by_provider["diarization"]
    # Word timings are native (ADR-0008), not a separate aligner.
    assert all(ModelCapability.ALIGNMENT not in c for c in by_provider.values())
