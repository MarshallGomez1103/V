"""Explicit install of the pinned local diarization models (ADR-0007).

Two upstream artifacts, both checked against a pinned size and SHA-256 before
they are published: the pyannote segmentation-3.0 ONNX export (a ``.tar.bz2``
from which only ``model.onnx`` and ``LICENSE`` are read) and the WeSpeaker
ResNet34 speaker-embedding ONNX. Everything lands atomically in
``<data>/models/diarization/``. Stdlib only; nothing is downloaded unless the
caller invokes :meth:`DiarizationModelStore.install`.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from voz.application.ports.model_installation import (
    CancelCheck,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.infrastructure.artifact_download import ArtifactFetcher

_Code = ModelInstallationFailureCode
_MANIFEST_NAME = ".voz-diarization.json"
_SEGMENTATION_MEMBER = "sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
_SEGMENTATION_LICENSE_MEMBER = "sherpa-onnx-pyannote-segmentation-3-0/LICENSE"

SEGMENTATION_FILE = "pyannote-segmentation-3-0.onnx"
SEGMENTATION_LICENSE_FILE = "LICENSE-pyannote-segmentation-3-0.txt"
EMBEDDING_FILE = "wespeaker_en_voxceleb_resnet34_LM.onnx"


@dataclass(frozen=True, slots=True)
class DiarizationArtifact:
    """One pinned upstream download."""

    name: str
    url: str
    size_bytes: int
    sha256: str
    license: str


SEGMENTATION_ARCHIVE = DiarizationArtifact(
    name="sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    url=(
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
        "speaker-segmentation-models/"
        "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
    ),
    size_bytes=6_958_444,
    sha256="24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
    license="MIT (pyannote/segmentation-3.0)",
)
# The upstream release tag is misspelled "recongition"; keep it verbatim.
EMBEDDING_MODEL = DiarizationArtifact(
    name=EMBEDDING_FILE,
    url=(
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
        "speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx"
    ),
    size_bytes=26_530_550,
    sha256="e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012",
    # Weights follow their training dataset, not the Apache-2.0 code license
    # (WeSpeaker docs/pretrained.md; HF card "cc-by-4.0"). See V1-10a.
    license="CC-BY-4.0 (WeSpeaker, VoxCeleb-trained)",
)


@dataclass(frozen=True, slots=True)
class DiarizationModelPaths:
    """Installed model files; host paths stay inside the infrastructure."""

    segmentation: Path
    embedding: Path


class DiarizationModelStore:
    """Install and locate the diarization models under the XDG data root."""

    def __init__(
        self,
        *,
        data_root: Path,
        segmentation: DiarizationArtifact = SEGMENTATION_ARCHIVE,
        embedding: DiarizationArtifact = EMBEDDING_MODEL,
        network_timeout_seconds: float = 30.0,
    ) -> None:
        models_root = Path(data_root).absolute() / "models"
        self._directory = models_root / "diarization"
        # Stable name so an interrupted download resumes from its ``.part`` files.
        self._staging = models_root / "diarization.installing"
        self._segmentation = segmentation
        self._embedding = embedding
        self._fetcher = ArtifactFetcher(
            self._staging,
            label="diarization model",
            timeout_seconds=network_timeout_seconds,
        )

    def paths(self) -> DiarizationModelPaths | None:
        """Return the model files when a complete, intact install exists."""
        try:
            manifest = json.loads((self._directory / _MANIFEST_NAME).read_text())
            sizes = manifest["files"]
            if manifest["sources"] != self._sources():
                return None
            for name, size in sizes.items():
                if (self._directory / name).stat().st_size != size:
                    return None
            if {SEGMENTATION_FILE, EMBEDDING_FILE} - set(sizes):
                return None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return DiarizationModelPaths(
            segmentation=self._directory / SEGMENTATION_FILE,
            embedding=self._directory / EMBEDDING_FILE,
        )

    def is_installed(self) -> bool:
        """Return whether the pinned models are present and complete."""
        return self.paths() is not None

    def install(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> DiarizationModelPaths:
        """Download, verify and atomically publish; resumes leftover partials."""
        existing = self.paths()
        if existing is not None:
            return existing
        total = self._segmentation.size_bytes + self._embedding.size_bytes
        done = 0

        def report(artifact_done: int, base: int) -> None:
            if progress is not None:
                progress(min(base + artifact_done, total), total)

        try:
            self._staging.mkdir(mode=0o700, parents=True, exist_ok=True)
            archive = self._fetcher.fetch(
                self._segmentation,
                lambda n: report(n, done),
                cancelled,
            )
            done = self._segmentation.size_bytes
            model = self._fetcher.fetch(
                self._embedding,
                lambda n: report(n, done),
                cancelled,
            )
            sizes = self._extract_segmentation(archive)
            sizes[EMBEDDING_FILE] = self._embedding.size_bytes
            os.replace(model, self._staging / EMBEDDING_FILE)
            archive.unlink()
            self._publish(sizes)
        except OSError as error:
            raise ModelInstallationError(
                _Code.IO_ERROR, "The diarization models could not be written."
            ) from error
        published = self.paths()
        if published is None:
            raise ModelInstallationError(
                _Code.INVALID_SNAPSHOT, "The diarization models are incomplete."
            )
        return published

    def remove(self) -> int:
        """Delete the installed and partial files; return the bytes freed."""
        freed = 0
        for directory in (self._directory, self._staging):
            if directory.is_dir() and not directory.is_symlink():
                freed += sum(
                    item.stat().st_size
                    for item in directory.rglob("*")
                    if item.is_file()
                )
                shutil.rmtree(directory)
        return freed

    def _sources(self) -> dict[str, str]:
        return {
            self._segmentation.name: self._segmentation.sha256,
            self._embedding.name: self._embedding.sha256,
        }

    def _publish(self, sizes: dict[str, int]) -> None:
        manifest = {
            "sources": self._sources(),
            "files": sizes,
            "installed_at": datetime.now(UTC).isoformat(),
        }
        with (self._staging / _MANIFEST_NAME).open("w") as output:
            json.dump(manifest, output, indent=2)
            output.flush()
            os.fsync(output.fileno())  # the manifest is the commit marker
        if self._directory.exists():  # stale or corrupt copy: replace it
            shutil.rmtree(self._directory)
        os.rename(self._staging, self._directory)

    def _extract_segmentation(self, archive: Path) -> dict[str, int]:
        """Copy only the two known members; nothing else in the archive is read."""
        wanted = {
            _SEGMENTATION_MEMBER: SEGMENTATION_FILE,
            _SEGMENTATION_LICENSE_MEMBER: SEGMENTATION_LICENSE_FILE,
        }
        sizes: dict[str, int] = {}
        try:
            with tarfile.open(archive, "r:bz2") as bundle:
                for member, target in wanted.items():
                    try:
                        info = bundle.getmember(member)
                    except KeyError:
                        info = None
                    source = bundle.extractfile(info) if info else None
                    if info is None or source is None or not info.isreg():
                        if target == SEGMENTATION_FILE:
                            raise self._invalid()
                        continue  # the license is informational, never required
                    with source, (self._staging / target).open("wb") as output:
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fsync(output.fileno())
                    sizes[target] = info.size
        except (tarfile.TarError, EOFError) as error:
            raise self._invalid() from error
        return sizes

    @staticmethod
    def _invalid() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.INVALID_SNAPSHOT, "The segmentation model archive is invalid."
        )


__all__ = [
    "EMBEDDING_FILE",
    "EMBEDDING_MODEL",
    "SEGMENTATION_ARCHIVE",
    "SEGMENTATION_FILE",
    "DiarizationArtifact",
    "DiarizationModelPaths",
    "DiarizationModelStore",
]
