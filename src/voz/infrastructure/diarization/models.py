"""Explicit install of the pinned local diarization models (ADR-0007).

Two upstream artifacts, both checked against a pinned size and SHA-256 before
they are published: the pyannote segmentation-3.0 ONNX export (a ``.tar.bz2``
from which only ``model.onnx`` and ``LICENSE`` are read) and the WeSpeaker
ResNet34 speaker-embedding ONNX. Everything lands atomically in
``<data>/models/diarization/``. Stdlib only; nothing is downloaded unless the
caller invokes :meth:`DiarizationModelStore.install`.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import tarfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from voz.application.ports.model_installation import (
    CancelCheck,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)

_Code = ModelInstallationFailureCode
_MANIFEST_NAME = ".voz-diarization.json"
_BLOCK_BYTES = 1024 * 1024
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
    license="Apache-2.0 (WeSpeaker)",
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
        self._timeout = network_timeout_seconds

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
            archive = self._fetch(
                self._segmentation,
                lambda n: report(n, done),
                cancelled,
            )
            done = self._segmentation.size_bytes
            model = self._fetch(
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

    def _fetch(
        self,
        artifact: DiarizationArtifact,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> Path:
        """Leave a verified ``artifact.name`` in staging, resuming a ``.part``."""
        finished = self._staging / artifact.name
        partial = self._staging / f"{artifact.name}.part"
        if finished.is_file() and self._matches(finished, artifact, cancelled):
            on_bytes(artifact.size_bytes)
            return finished
        finished.unlink(missing_ok=True)
        self._download_part(artifact, partial, on_bytes, cancelled)
        if not self._matches(partial, artifact, cancelled):
            partial.unlink(missing_ok=True)
            raise ModelInstallationError(
                _Code.CHECKSUM_MISMATCH,
                "The downloaded diarization model failed verification.",
            )
        os.replace(partial, finished)
        return finished

    def _download_part(
        self,
        artifact: DiarizationArtifact,
        partial: Path,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> None:
        for _attempt in range(2):
            try:
                offset = partial.stat().st_size
            except FileNotFoundError:
                offset = 0
            if offset > artifact.size_bytes:
                partial.unlink()
                offset = 0
            if offset == artifact.size_bytes:
                on_bytes(offset)
                return
            headers = {"Accept-Encoding": "identity", "User-Agent": "voz-model-store"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                response = urllib.request.urlopen(
                    urllib.request.Request(artifact.url, headers=headers),
                    timeout=self._timeout,
                )
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 416 and offset:  # stale partial: start over once
                    partial.unlink(missing_ok=True)
                    continue
                raise ModelInstallationError(
                    _Code.HTTP_ERROR,
                    "The model server rejected the request.",
                    status=error.code,
                ) from error
            except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
                raise self._network_failure() from error
            with response:
                status = int(response.status)
                resumed = False
                if offset and status == 206:
                    if not str(response.headers.get("Content-Range", "")).startswith(
                        f"bytes {offset}-"
                    ):
                        partial.unlink(missing_ok=True)
                        continue
                    resumed = True
                elif status != 200:
                    raise ModelInstallationError(
                        _Code.HTTP_ERROR,
                        "The model server rejected the request.",
                        status=status,
                    )
                written = offset if resumed else 0
                with partial.open("ab" if resumed else "wb") as output:
                    on_bytes(written)
                    while block := self._read(response):
                        if cancelled is not None and cancelled():
                            raise self._cancelled()
                        written += len(block)
                        if written > artifact.size_bytes:
                            break
                        output.write(block)
                        on_bytes(written)
                    output.flush()
                    os.fsync(output.fileno())
                if written == artifact.size_bytes and not response.length:
                    return
                # Too long, or a cut connection that read() reported as clean EOF.
                if written > artifact.size_bytes:
                    partial.unlink(missing_ok=True)
                    raise ModelInstallationError(
                        _Code.CHECKSUM_MISMATCH,
                        "The downloaded diarization model failed verification.",
                    )
                raise self._network_failure()
        raise ModelInstallationError(
            _Code.DOWNLOAD_FAILED, "The model file could not be downloaded."
        )

    def _read(self, response: http.client.HTTPResponse) -> bytes:
        try:
            return response.read(_BLOCK_BYTES)
        except (OSError, http.client.HTTPException) as error:
            raise self._network_failure() from error

    @staticmethod
    def _network_failure() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.NETWORK_ERROR, "The model server could not be reached in time."
        )

    @staticmethod
    def _cancelled() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.CANCELLED, "The installation was cancelled."
        )

    def _matches(
        self,
        path: Path,
        artifact: DiarizationArtifact,
        cancelled: CancelCheck | None,
    ) -> bool:
        if path.stat().st_size != artifact.size_bytes:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(_BLOCK_BYTES):
                if cancelled is not None and cancelled():
                    raise self._cancelled()
                digest.update(block)
        return digest.hexdigest() == artifact.sha256


__all__ = [
    "EMBEDDING_FILE",
    "EMBEDDING_MODEL",
    "SEGMENTATION_ARCHIVE",
    "SEGMENTATION_FILE",
    "DiarizationArtifact",
    "DiarizationModelPaths",
    "DiarizationModelStore",
]
