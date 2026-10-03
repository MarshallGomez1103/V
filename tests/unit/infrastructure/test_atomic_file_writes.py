"""S14.02: a failure between "write" and "publish" leaves the prior state intact."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from voz.application.ports.model_installation import (
    ModelInstallationError,
    ModelInstallationFailureCode,
)
from voz.application.ports.waveform import PeakSeries
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.audio.media_args import path_of_descriptor
from voz.infrastructure.audio.waveform_peaks import FfmpegWaveformPeaks
from voz.infrastructure.diarization.models import (
    EMBEDDING_FILE,
    SEGMENTATION_FILE,
    DiarizationArtifact,
    DiarizationModelStore,
)
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.model_storage import FileSystemModelStore

_IO_ERROR = ModelInstallationFailureCode.IO_ERROR
_real_rename = os.rename
_real_replace = os.replace
_real_fsync = os.fsync


def _fail(*_: object, **__: object) -> None:
    raise OSError(5, "injected I/O failure")


# -- model manifests (model_storage.py) ---------------------------------------


def _descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="fixture",
        display_name="Fixture model",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
        source="example/faster-whisper-fixture",
        revision="0123456789abcdef0123456789abcdef01234567",
    )


def _model_store(tmp_path: Path) -> FileSystemModelStore:
    snapshot = tmp_path / "remote-snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "model.bin").write_bytes(b"weights")

    def download(**_: object) -> str:
        return str(snapshot)

    return FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        downloader_factory=lambda: download,
    )


@pytest.mark.parametrize("failing", ["rename", "fsync"])
def test_model_install_that_fails_before_publication_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    store = _model_store(tmp_path)
    descriptor = _descriptor()
    models = tmp_path / "data" / "models"
    with monkeypatch.context() as patched:
        patched.setattr(os, failing, _fail)
        with pytest.raises(ModelInstallationError) as caught:
            store.install(descriptor, confirmed=True)
    assert caught.value.code is _IO_ERROR

    assert not store.is_installed(descriptor)
    assert store.registered_descriptors() == ()
    leftovers = [p.name for p in models.rglob("*") if p.name.endswith(".tmp")]
    assert leftovers == []  # staging was cleaned
    # The next attempt is not poisoned by the failed one.
    assert store.install(descriptor, confirmed=True).descriptor == descriptor
    assert store.is_installed(descriptor)


def test_published_model_is_never_touched_by_a_later_failing_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _model_store(tmp_path)
    descriptor = _descriptor()
    installed_at = store.install(descriptor, confirmed=True).installed_at
    manifest = store.resolve_path(descriptor) / ".voz-model.json"
    before = manifest.read_bytes()

    monkeypatch.setattr(os, "rename", _fail)
    monkeypatch.setattr(os, "fsync", _fail)
    assert store.install(descriptor, confirmed=True).installed_at == installed_at

    assert manifest.read_bytes() == before


# -- waveform peaks cache (waveform_peaks.py) ---------------------------------


def _peaks_adapter(tmp_path: Path) -> FfmpegWaveformPeaks:
    return FfmpegWaveformPeaks(
        storage_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        media_storage=FileSystemMediaStorage(tmp_path / "data"),
    )


def _series(level: float) -> PeakSeries:
    return PeakSeries(duration_ms=1_000, peaks=((-level, level),))


def test_peaks_cache_write_syncs_the_file_before_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def spy_fsync(descriptor: int) -> None:
        events.append("fsync")
        _real_fsync(descriptor)

    def spy_replace(source: str | Path, target: str | Path) -> None:
        events.append("replace")
        _real_replace(source, target)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)
    target = tmp_path / "cache" / "waveforms" / "v1-x-1.json"

    _peaks_adapter(tmp_path)._write_cache(target, _series(0.5))  # pyright: ignore[reportPrivateUsage]

    assert events == ["fsync", "replace"]
    assert json.loads(target.read_text())["peaks"] == [[-0.5, 0.5]]


@pytest.mark.parametrize("failing", ["fsync", "replace"])
def test_failed_peaks_cache_write_keeps_the_previous_entry_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    adapter = _peaks_adapter(tmp_path)
    target = tmp_path / "cache" / "waveforms" / "v1-x-1.json"
    adapter._write_cache(target, _series(0.25))  # pyright: ignore[reportPrivateUsage]
    before = target.read_bytes()

    with monkeypatch.context() as patched:
        patched.setattr(os, failing, _fail)
        adapter._write_cache(target, _series(0.75))  # pyright: ignore[reportPrivateUsage]

    assert target.read_bytes() == before  # best effort: never raises, never half-writes
    assert [p.name for p in target.parent.iterdir()] == [target.name]


# -- diarization models (diarization/models.py) -------------------------------

_SEGMENTATION = b"fake-segmentation-onnx" * 100
_EMBEDDING = b"fake-embedding-onnx" * 400
_PREFIX = "sherpa-onnx-pyannote-segmentation-3-0/"


def _tar() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for name, data in (
            (_PREFIX + "model.onnx", _SEGMENTATION),
            (_PREFIX + "LICENSE", b"MIT"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _diarization_store(tmp_path: Path) -> DiarizationModelStore:
    """A store whose verified downloads already sit in staging: no network."""
    archive = _tar()

    def artifact(name: str, data: bytes) -> DiarizationArtifact:
        return DiarizationArtifact(
            name=name,
            url="http://127.0.0.1:9/unreachable",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            license="test",
        )

    staging = tmp_path / "models" / "diarization.installing"
    staging.mkdir(parents=True)
    (staging / "seg.tar.bz2").write_bytes(archive)
    (staging / EMBEDDING_FILE).write_bytes(_EMBEDDING)
    return DiarizationModelStore(
        data_root=tmp_path,
        segmentation=artifact("seg.tar.bz2", archive),
        embedding=artifact(EMBEDDING_FILE, _EMBEDDING),
        network_timeout_seconds=1,
    )


def test_diarization_publish_failure_leaves_no_half_installed_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _diarization_store(tmp_path)
    with monkeypatch.context() as patched:
        patched.setattr(os, "rename", _fail)
        with pytest.raises(ModelInstallationError) as caught:
            store.install()
    assert caught.value.code is _IO_ERROR

    assert not store.is_installed()
    assert not (tmp_path / "models" / "diarization").exists()
    # The archive was consumed before publishing; a resumed download (stood in
    # for here by putting it back) is all the retry needs.
    (tmp_path / "models" / "diarization.installing" / "seg.tar.bz2").write_bytes(_tar())
    assert store.install().segmentation.read_bytes() == _SEGMENTATION
    assert store.is_installed()


def test_diarization_files_and_manifest_are_synced_before_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _diarization_store(tmp_path)
    events: list[str] = []

    def name_of(descriptor: int) -> str:
        try:
            return Path(path_of_descriptor(descriptor)).name
        except OSError:
            return "?"

    def spy_fsync(descriptor: int) -> None:
        events.append(f"fsync:{name_of(descriptor)}")
        _real_fsync(descriptor)

    def spy_rename(source: str | Path, target: str | Path) -> None:
        events.append(f"rename:{Path(target).name}")
        _real_rename(source, target)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "rename", spy_rename)
    store.install()

    published = events.index("rename:diarization")
    before = events[:published]
    assert f"fsync:{SEGMENTATION_FILE}" in before
    assert "fsync:.voz-diarization.json" in before


def test_diarization_interrupted_before_the_manifest_is_not_installed(
    tmp_path: Path,
) -> None:
    # A directory renamed into place without its manifest (older crash, manual
    # copy) must read as "not installed", never as a usable model.
    store = _diarization_store(tmp_path)
    published = tmp_path / "models" / "diarization"
    published.mkdir()
    (published / SEGMENTATION_FILE).write_bytes(_SEGMENTATION)
    (published / EMBEDDING_FILE).write_bytes(_EMBEDDING)

    assert not store.is_installed()
    assert store.paths() is None
