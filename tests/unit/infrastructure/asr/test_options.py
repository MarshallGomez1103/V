"""Local options inspect synthetic manifests and fake modules, never weights."""

from pathlib import Path
from types import ModuleType

import pytest

from voz.application.ports.transcription_options import (
    InstallationStatus,
    TranscriptionOptionsUnavailable,
)
from voz.infrastructure.asr.catalog import (
    faster_whisper_catalog,
    faster_whisper_fast_descriptor,
)
from voz.infrastructure.asr.options import (
    FasterWhisperRuntimeProbe,
    LocalTranscriptionModelCatalog,
)
from voz.infrastructure.model_storage import FileSystemModelStore


def test_missing_runtime_is_a_valid_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(name: str) -> ModuleType:
        raise ImportError(name)

    monkeypatch.setattr(
        "voz.infrastructure.asr.options.importlib.import_module", unavailable
    )
    result = FasterWhisperRuntimeProbe().probe("faster-whisper")
    assert not result.available
    assert result.hardware is None


def test_available_runtime_is_probed_without_constructing_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_load() -> None:
        raise AssertionError("options must not load a model")

    def get_types(device: str) -> set[str]:
        return {"float16"} if device == "cuda" else {"int8"}

    def fake_import(name: str) -> ModuleType:
        module = ModuleType(name)
        if name == "faster_whisper":
            vars(module)["WhisperModel"] = forbidden_load
        elif name == "ctranslate2":
            vars(module)["get_supported_compute_types"] = get_types
        else:
            raise AssertionError(name)
        return module

    monkeypatch.setattr(
        "voz.infrastructure.asr.options.importlib.import_module", fake_import
    )
    result = FasterWhisperRuntimeProbe().probe("faster-whisper")
    assert result.available
    assert result.hardware is not None
    assert result.hardware.cuda_compute_types == {"float16"}
    assert "translation" not in result.capabilities
    assert "word_timestamps" in result.capabilities
    assert "diarization" not in result.capabilities


@pytest.mark.parametrize("files_present", [False, True])
def test_registered_model_is_not_automatically_file_ready(
    tmp_path: Path, files_present: bool
) -> None:
    snapshot = tmp_path / "synthetic"
    snapshot.mkdir()
    if files_present:
        for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
            (snapshot / name).write_text("synthetic", encoding="utf-8")

    def download(
        *, repo_id: str, revision: str, cache_dir: str, local_files_only: bool
    ) -> str:
        return str(snapshot)

    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: download,
    )
    descriptor = faster_whisper_fast_descriptor(revision="a" * 40)
    store.install(descriptor, confirmed=True)
    options = LocalTranscriptionModelCatalog(store).list_models()
    assert len(options) == 6
    fast = next(item for item in options if item.descriptor.model_id == "turbo")
    assert fast.installation_status is InstallationStatus.REGISTERED
    assert fast.descriptor == descriptor
    assert fast.files_available is files_present
    # Repeated observation does not install or rewrite anything.
    assert LocalTranscriptionModelCatalog(store).list_models() == options


@pytest.mark.parametrize(
    ("vocabulary", "present"),
    [("vocabulary.txt", True), ("vocabulary.json", False)],
)
def test_vocabulary_file_depends_on_the_model(
    tmp_path: Path, vocabulary: str, present: bool
) -> None:
    snapshot = tmp_path / "synthetic"
    snapshot.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json", vocabulary):
        (snapshot / name).write_text("synthetic", encoding="utf-8")

    def download(
        *, repo_id: str, revision: str, cache_dir: str, local_files_only: bool
    ) -> str:
        return str(snapshot)

    store = FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: download,
    )
    tiny = next(e for e in faster_whisper_catalog() if e.descriptor.model_id == "tiny")
    store.install(tiny.descriptor, confirmed=True)
    registration = next(
        item
        for item in LocalTranscriptionModelCatalog(store).list_models()
        if item.descriptor.model_id == "tiny"
    )
    assert registration.installation_status is InstallationStatus.REGISTERED
    assert registration.files_available is present


def test_empty_catalog_exposes_every_pinned_model_without_writes(
    tmp_path: Path,
) -> None:
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    options = LocalTranscriptionModelCatalog(store).list_models()
    assert [item.descriptor.model_id for item in options] == [
        entry.descriptor.model_id for entry in faster_whisper_catalog()
    ]
    assert all(item.descriptor.provenance is not None for item in options)
    assert all(
        item.installation_status is InstallationStatus.NOT_REGISTERED
        for item in options
    )
    assert list(tmp_path.iterdir()) == []


def test_unknown_provider_runtime_is_unavailable() -> None:
    assert not FasterWhisperRuntimeProbe().probe("other").available


@pytest.mark.parametrize("content", ["{", "[]", '{"provider_id": "faster-whisper"}'])
def test_invalid_manifests_do_not_become_registered_models(
    tmp_path: Path, content: str
) -> None:
    directory = tmp_path / "data" / "models" / "faster-whisper" / ("a" * 32)
    directory.mkdir(parents=True)
    (directory / ".voz-model.json").write_text(content, encoding="utf-8")
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    assert store.registered_descriptors() == ()
    assert all(
        item.installation_status is InstallationStatus.NOT_REGISTERED
        for item in LocalTranscriptionModelCatalog(store).list_models()
    )


def test_model_directory_symlink_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    provider = tmp_path / "data" / "models" / "faster-whisper"
    provider.mkdir(parents=True)
    (provider / ("a" * 32)).symlink_to(outside, target_is_directory=True)
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    assert store.registered_descriptors() == ()


def test_unavailable_registration_root_maps_to_safe_query_error(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "models").write_text("not a directory", encoding="utf-8")
    store = FileSystemModelStore(data_root=data, cache_root=tmp_path / "cache")
    with pytest.raises(TranscriptionOptionsUnavailable):
        LocalTranscriptionModelCatalog(store).list_models()


def test_registration_root_symlink_is_rejected(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (data / "models").symlink_to(outside, target_is_directory=True)
    store = FileSystemModelStore(data_root=data, cache_root=tmp_path / "cache")
    with pytest.raises(TranscriptionOptionsUnavailable):
        LocalTranscriptionModelCatalog(store).list_models()
