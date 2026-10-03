"""Explicit XDG model installation with pinned provenance and atomic publication."""

from __future__ import annotations

import hashlib
import http.client
import importlib
import json
import os
import shutil
import stat
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from errno import EEXIST, ENOSPC, ENOTEMPTY
from pathlib import Path
from typing import BinaryIO, Protocol, cast
from urllib.parse import quote, urlsplit
from uuid import uuid4

from voz.application.ports.disk_space import (
    DiskLocation,
    DiskSpacePort,
    InsufficientDiskSpace,
    require_free_space,
)
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ModelInstallation,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.safe_fs import DirectoryHandle

_MANIFEST_NAME = ".voz-model.json"
_BLOCK_BYTES = 1024 * 1024
_Code = ModelInstallationFailureCode


class SnapshotDownloader(Protocol):
    """Narrow shape of huggingface_hub.snapshot_download used by this adapter."""

    def __call__(
        self,
        *,
        repo_id: str,
        revision: str,
        cache_dir: str,
        local_files_only: bool,
    ) -> str: ...


def _default_snapshot_downloader() -> SnapshotDownloader:
    try:
        module = importlib.import_module("huggingface_hub")
        candidate = vars(module)["snapshot_download"]
    except (ImportError, KeyError) as error:
        raise ModelInstallationError(
            ModelInstallationFailureCode.DOWNLOAD_FAILED,
            "The local ASR installation dependency is not available.",
        ) from error
    if not callable(candidate):
        raise ModelInstallationError(
            ModelInstallationFailureCode.DOWNLOAD_FAILED,
            "The local ASR installation dependency is invalid.",
        )
    return cast(SnapshotDownloader, candidate)


class FileSystemModelStore:
    """Install pinned snapshots outside the checkout and resolve exact local models."""

    def __init__(
        self,
        *,
        data_root: Path,
        cache_root: Path,
        downloader_factory: Callable[[], SnapshotDownloader] = (
            _default_snapshot_downloader
        ),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        disk_space: DiskSpacePort | None = None,
        network_timeout_seconds: float = 30.0,
    ) -> None:
        self._models_root = Path(data_root).absolute() / "models"
        self._downloads_root = Path(cache_root).absolute() / "downloads"
        self._downloader_factory = downloader_factory
        self._clock = clock
        self._disk_space = disk_space
        self._network_timeout = network_timeout_seconds

    def install(
        self,
        descriptor: ModelDescriptor,
        *,
        confirmed: bool,
    ) -> ModelInstallation:
        """Download a pinned snapshot only after explicit user confirmation."""
        if not confirmed:
            raise ModelInstallationError(
                ModelInstallationFailureCode.CONFIRMATION_REQUIRED,
                "Model download requires explicit confirmation.",
            )
        if descriptor.provenance is None:
            raise ModelInstallationError(
                ModelInstallationFailureCode.PROVENANCE_REQUIRED,
                "The model source and revision must be pinned before download.",
            )
        source, revision = descriptor.provenance
        final_directory = self._directory_for(descriptor)
        existing_timestamp = self._installed_at(final_directory, descriptor)
        if existing_timestamp is not None:
            return ModelInstallation(
                descriptor=descriptor,
                installed_at=existing_timestamp,
            )
        installed_at = self._clock()

        try:
            self._downloads_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            final_directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            downloader = self._downloader_factory()
            snapshot = Path(
                downloader(
                    repo_id=source,
                    revision=revision,
                    cache_dir=str(self._downloads_root),
                    local_files_only=False,
                )
            )
        except ModelInstallationError:
            raise
        except Exception as error:
            raise ModelInstallationError(
                ModelInstallationFailureCode.DOWNLOAD_FAILED,
                "The pinned model snapshot could not be downloaded.",
            ) from error

        if not snapshot.is_dir():
            raise ModelInstallationError(
                ModelInstallationFailureCode.INVALID_SNAPSHOT,
                "The downloaded model snapshot is invalid.",
            )

        staging = final_directory.parent / f".install-{uuid4()}.tmp"
        try:
            shutil.copytree(snapshot, staging, symlinks=False)
            installed_at = self._commit(
                staging, final_directory, descriptor, installed_at
            )
        except ModelInstallationError:
            raise
        except OSError as error:
            raise ModelInstallationError(
                ModelInstallationFailureCode.IO_ERROR,
                "The model snapshot could not be published safely.",
            ) from error
        finally:
            if staging.exists():
                shutil.rmtree(staging)

        return ModelInstallation(descriptor=descriptor, installed_at=installed_at)

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        """Return whether the exact pinned model has a valid local manifest."""
        return self._matches_manifest(self._directory_for(descriptor), descriptor)

    def registered_descriptors(self) -> tuple[ModelDescriptor, ...]:
        """Read only VOZ manifests, not remote catalogs or external caches.

        Registration verifies identity/location/timestamp, not model integrity.
        Capabilities and profiles must come from the trusted catalog, not disk.
        """
        descriptors: list[ModelDescriptor] = []
        if self._models_root.is_symlink():
            raise OSError("Model registration directory is unavailable.")
        if not self._models_root.exists():
            return ()
        for provider in sorted(self._models_root.iterdir()):
            if provider.is_symlink() or not provider.is_dir():
                continue
            for directory in sorted(provider.iterdir()):
                manifest = directory / _MANIFEST_NAME
                if (
                    directory.is_symlink()
                    or not directory.is_dir()
                    or manifest.is_symlink()
                    or not manifest.is_file()
                ):
                    continue
                try:
                    if manifest.stat().st_size > 65_536:
                        continue
                    payload: object = json.loads(manifest.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        continue
                    fields = cast(dict[str, object], payload)
                    values = [
                        fields.get(key)
                        for key in (
                            "provider_id",
                            "model_id",
                            "display_name",
                            "source",
                            "revision",
                        )
                    ]
                    if not all(isinstance(value, str) for value in values):
                        continue
                    strings = cast(list[str], values)
                    descriptor = ModelDescriptor(
                        provider_id=strings[0],
                        model_id=strings[1],
                        display_name=strings[2],
                        source=strings[3],
                        revision=strings[4],
                        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
                    )
                    if directory == self._directory_for(
                        descriptor
                    ) and self.is_installed(descriptor):
                        descriptors.append(descriptor)
                except (FileNotFoundError, ValueError, UnicodeError):
                    continue
        return tuple(descriptors)

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        """Resolve a local path for infrastructure use without network access."""
        directory = self._directory_for(descriptor)
        if not self._matches_manifest(directory, descriptor):
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected transcription model is not installed.",
            )
        return directory

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        base_url: str = "https://huggingface.co",
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        """Fetch pinned files over HTTP(S), verify them, and publish atomically.

        Partial downloads live in a deterministic per-model staging directory and
        are resumed with ``Range``; a cancelled or failed call keeps them.
        """
        source, revision = self._pinned(descriptor)
        items = self._checked_files(files)
        root = self._checked_base_url(base_url)
        final_directory = self._directory_for(descriptor)
        existing = self._installed_at(final_directory, descriptor)
        if existing is not None:
            return ModelInstallation(descriptor=descriptor, installed_at=existing)
        total = sum(item.size_bytes for item in items)
        staging = final_directory.parent / f".download-{final_directory.name}"

        def emit(done: int) -> None:
            if progress is not None:
                progress(done, total)

        try:
            staging.mkdir(mode=0o700, parents=True, exist_ok=True)
            pending = self._pending_bytes(staging, items)
            self._require_space(pending)
            done = 0
            emit(total - pending)  # bytes already on disk from earlier attempts
            for item in items:
                url = (
                    f"{root}/{quote(source, safe='/')}/resolve/{revision}/"
                    f"{quote(item.name, safe='')}"
                )
                self._fetch(
                    url,
                    staging,
                    item,
                    lambda count, base=done: emit(base + count),
                    cancelled,
                )
                done += item.size_bytes
                emit(done)
            installed_at = self._commit(
                staging, final_directory, descriptor, self._clock(), items
            )
            if staging.exists():  # lost the publication race to another installer
                shutil.rmtree(staging)
        except ModelInstallationError:
            raise
        except OSError as error:
            raise self._io_failure(error) from error
        return ModelInstallation(descriptor=descriptor, installed_at=installed_at)

    def import_local_snapshot(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        snapshot_dir: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        """Adopt a foreign snapshot (e.g. a Hugging Face cache) without touching it.

        Files are hardlinked when possible, otherwise copied; ``snapshot_dir`` is
        only ever read. Progress counts hashed bytes (or file size when the file
        has no digest).
        """
        self._pinned(descriptor)
        items = self._checked_files(files)
        final_directory = self._directory_for(descriptor)
        existing = self._installed_at(final_directory, descriptor)
        if existing is not None:
            return ModelInstallation(descriptor=descriptor, installed_at=existing)
        origins = self._resolve_snapshot(Path(snapshot_dir), items)
        total = sum(item.size_bytes for item in items)
        done = 0

        def emit(count: int) -> None:
            nonlocal done
            done += count
            if progress is not None:
                progress(done, total)

        staging = final_directory.parent / f".import-{uuid4()}.tmp"
        try:
            staging.mkdir(mode=0o700, parents=True)
            emit(0)
            for item, origin in zip(items, origins, strict=True):
                if cancelled is not None and cancelled():
                    raise self._cancelled()
                target = staging / item.name
                try:
                    os.link(origin, target)
                except OSError:
                    self._require_space(item.size_bytes)
                    shutil.copyfile(origin, target)
                if not self._matches(target, item, cancelled, emit):
                    raise self._mismatch()
            installed_at = self._commit(
                staging, final_directory, descriptor, self._clock(), items
            )
        except ModelInstallationError:
            raise
        except OSError as error:
            raise self._io_failure(error) from error
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return ModelInstallation(descriptor=descriptor, installed_at=installed_at)

    def remove(self, descriptor: ModelDescriptor) -> int:
        """Delete only this model's canonical VOZ directory; return bytes freed.

        Files hardlinked to a foreign cache free nothing and are not counted.
        """
        directory = self._directory_for(descriptor)
        if not self._is_registered(directory, descriptor):
            raise ModelInstallationError(
                _Code.NOT_INSTALLED, "The selected model is not installed."
            )
        freed = self._tree_size(directory, exclusive=True)
        try:
            self._discard(directory)
            self._sync_directory(directory.parent)
        except OSError as error:
            raise ModelInstallationError(
                _Code.IO_ERROR, "The model could not be removed safely."
            ) from error
        return freed

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        """Bytes occupied by the VOZ copy, or ``None`` when it is not installed."""
        directory = self._directory_for(descriptor)
        if not self._is_registered(directory, descriptor):
            return None
        return self._tree_size(directory, exclusive=False)

    def _directory_for(self, descriptor: ModelDescriptor) -> Path:
        digest = hashlib.sha256(
            "\0".join(
                (
                    *descriptor.identity,
                    descriptor.source or "",
                    descriptor.revision or "",
                )
            ).encode()
        ).hexdigest()[:32]
        return self._models_root / descriptor.provider_id / digest

    @staticmethod
    def _pinned(descriptor: ModelDescriptor) -> tuple[str, str]:
        if descriptor.provenance is None:
            raise ModelInstallationError(
                _Code.PROVENANCE_REQUIRED,
                "The model source and revision must be pinned before download.",
            )
        return descriptor.provenance

    @staticmethod
    def _checked_files(files: Sequence[ModelFile]) -> tuple[ModelFile, ...]:
        items = tuple(files)
        if not items or len({item.name for item in items}) != len(items):
            raise ModelInstallationError(
                _Code.INVALID_SNAPSHOT,
                "The model file list must be non-empty and free of duplicates.",
            )
        return items

    @staticmethod
    def _checked_base_url(base_url: str) -> str:
        parts = urlsplit(base_url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.query
            or parts.fragment
        ):
            raise ModelInstallationError(
                _Code.DOWNLOAD_FAILED, "The model download address is not supported."
            )
        return base_url.rstrip("/")

    @staticmethod
    def _cancelled() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.CANCELLED, "The model installation was cancelled."
        )

    @staticmethod
    def _mismatch() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.CHECKSUM_MISMATCH,
            "A model file does not match its expected size or checksum.",
        )

    @staticmethod
    def _http_failure(status: int) -> ModelInstallationError:
        return ModelInstallationError(
            _Code.HTTP_ERROR,
            f"The model server answered with HTTP {status}.",
            status=status,
        )

    @staticmethod
    def _io_failure(error: OSError) -> ModelInstallationError:
        if error.errno == ENOSPC:
            return ModelInstallationError(
                _Code.DISK_SPACE_INSUFFICIENT,
                "There is not enough free disk space for this operation.",
            )
        return ModelInstallationError(
            _Code.IO_ERROR, "The model files could not be written safely."
        )

    def _require_space(self, pending_bytes: int) -> None:
        # ponytail: DiskLocation has no MODELS area; models share the data root
        # with derivatives, so DERIVATIVES resolves to the right volume.
        if pending_bytes <= 0:
            return
        try:
            require_free_space(
                self._disk_space, DiskLocation.DERIVATIVES, pending_bytes
            )
        except InsufficientDiskSpace as error:
            raise ModelInstallationError(
                _Code.DISK_SPACE_INSUFFICIENT,
                "There is not enough free disk space to install the model.",
            ) from error

    def _pending_bytes(self, staging: Path, items: Sequence[ModelFile]) -> int:
        pending = 0
        for item in items:
            if self._regular_size(staging / item.name) is not None:
                continue
            partial = self._regular_size(staging / f"{item.name}.part") or 0
            pending += item.size_bytes - min(partial, item.size_bytes)
        return pending

    def _resolve_snapshot(
        self, snapshot: Path, items: Sequence[ModelFile]
    ) -> list[Path]:
        if not snapshot.is_dir():
            raise ModelInstallationError(
                _Code.INVALID_SNAPSHOT, "The local model snapshot is unavailable."
            )
        origins: list[Path] = []
        for item in items:
            try:
                # HF snapshots link ``x -> ../../blobs/<hash>``; adopt the target.
                origin = (snapshot / item.name).resolve(strict=True)
                size = origin.stat().st_size if origin.is_file() else None
            except (OSError, RuntimeError):
                raise ModelInstallationError(
                    _Code.INVALID_SNAPSHOT,
                    "The local model snapshot is missing a required file.",
                ) from None
            if size != item.size_bytes:
                raise self._mismatch()
            origins.append(origin)
        return origins

    def _fetch(
        self,
        url: str,
        staging: Path,
        item: ModelFile,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> None:
        """Leave a verified ``item.name`` in ``staging``, resuming a ``.part``."""
        finished = staging / item.name
        partial = staging / f"{item.name}.part"
        if finished.is_symlink() or finished.exists():
            if self._matches(finished, item, cancelled):
                on_bytes(item.size_bytes)
                return
            finished.unlink()
        self._download_part(url, partial, item, on_bytes, cancelled)
        if not self._matches(partial, item, cancelled):
            partial.unlink(missing_ok=True)
            raise self._mismatch()
        os.replace(partial, finished)

    def _download_part(
        self,
        url: str,
        partial: Path,
        item: ModelFile,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> None:
        for _attempt in range(2):
            offset = self._regular_size(partial)
            if offset is None or offset > item.size_bytes:
                partial.unlink(missing_ok=True)
                offset = 0
            if offset == item.size_bytes:
                on_bytes(offset)
                return
            headers = {"Accept-Encoding": "identity", "User-Agent": "voz-model-store"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                response = urllib.request.urlopen(
                    urllib.request.Request(url, headers=headers),
                    timeout=self._network_timeout,
                )
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 416 and offset:  # stale partial: start over once
                    partial.unlink(missing_ok=True)
                    continue
                raise self._http_failure(error.code) from error
            except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
                raise self._network_failure() from error
            with response:
                status = int(response.status)
                if offset and status == 206:
                    if not str(response.headers.get("Content-Range", "")).startswith(
                        f"bytes {offset}-"
                    ):
                        partial.unlink(missing_ok=True)
                        continue
                    resumed = True
                elif status == 200:
                    resumed = False  # no Range support: restart the file
                else:
                    raise self._http_failure(status)
                start = offset if resumed else 0
                with partial.open("ab" if resumed else "wb") as output:
                    written = self._stream(
                        response, output, start, item.size_bytes, on_bytes, cancelled
                    )
            if written != item.size_bytes:
                partial.unlink(missing_ok=True)
                raise self._mismatch()
            return
        raise ModelInstallationError(
            _Code.DOWNLOAD_FAILED, "The model file could not be downloaded."
        )

    @staticmethod
    def _network_failure() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.NETWORK_ERROR, "The model server could not be reached in time."
        )

    def _stream(
        self,
        response: http.client.HTTPResponse,
        output: BinaryIO,
        start: int,
        expected: int,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> int:
        """Copy the body block by block; return bytes on disk (may exceed expected)."""
        written = start
        on_bytes(written)
        while True:
            if cancelled is not None and cancelled():
                raise self._cancelled()
            try:
                block = response.read(_BLOCK_BYTES)
            except (OSError, http.client.HTTPException) as error:
                raise self._network_failure() from error
            if not block:
                break
            written += len(block)
            if written > expected:
                return written
            output.write(block)
            on_bytes(written)
        output.flush()
        os.fsync(output.fileno())
        if response.length:  # read() reports a cut connection as a clean EOF
            raise self._network_failure()
        return written

    def _matches(
        self,
        path: Path,
        item: ModelFile,
        cancelled: CancelCheck | None,
        on_bytes: Callable[[int], None] | None = None,
    ) -> bool:
        """Exact size and, when known, SHA-256; ``on_bytes`` gets hashed increments."""
        if self._regular_size(path) != item.size_bytes:
            return False
        if item.sha256 is None:
            if on_bytes is not None:
                on_bytes(item.size_bytes)
            return True
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(_BLOCK_BYTES):
                if cancelled is not None and cancelled():
                    raise self._cancelled()
                digest.update(block)
                if on_bytes is not None:
                    on_bytes(len(block))
        return digest.hexdigest() == item.sha256

    def _commit(
        self,
        staging: Path,
        final_directory: Path,
        descriptor: ModelDescriptor,
        installed_at: datetime,
        files: Sequence[ModelFile] | None = None,
    ) -> datetime:
        """Manifest, fsync and atomic rename; return the winning ``installed_at``."""
        if files is not None:
            names = {item.name for item in files}
            for entry in staging.iterdir():
                if entry.name in names:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            if any(
                self._regular_size(staging / item.name) != item.size_bytes
                for item in files
            ):
                raise ModelInstallationError(
                    _Code.INVALID_SNAPSHOT, "The model files are incomplete."
                )
        self._write_manifest(staging, descriptor, installed_at, files)
        self._sync_tree(staging)
        if (
            files is not None
            and (final_directory.is_symlink() or final_directory.exists())
            and self._installed_at(final_directory, descriptor) is None
        ):
            self._discard(final_directory)  # published but corrupt: replace it
        try:
            os.rename(staging, final_directory)
        except OSError as error:
            if error.errno not in {EEXIST, ENOTEMPTY}:
                raise
            winner_timestamp = self._installed_at(final_directory, descriptor)
            if winner_timestamp is None:
                raise
            installed_at = winner_timestamp
        self._sync_directory(final_directory.parent)
        return installed_at

    @staticmethod
    def _discard(path: Path) -> None:
        """Remove a canonical directory so a crash never leaves it half-deleted."""
        if path.is_symlink() or not path.is_dir():
            path.unlink()
            return
        trash = path.parent / f".remove-{uuid4()}.tmp"
        os.rename(path, trash)
        shutil.rmtree(trash)

    def _is_registered(self, directory: Path, descriptor: ModelDescriptor) -> bool:
        return (
            not directory.is_symlink()
            and directory.is_dir()
            and self._load_manifest(directory, descriptor) is not None
        )

    def _tree_size(self, directory: Path, *, exclusive: bool) -> int:
        total = 0
        for path in directory.rglob("*"):
            try:
                info = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and (not exclusive or info.st_nlink == 1):
                total += info.st_size
        return total

    @staticmethod
    def _manifest_payload(
        descriptor: ModelDescriptor,
        installed_at: datetime,
        files: Sequence[ModelFile] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider_id": descriptor.provider_id,
            "model_id": descriptor.model_id,
            "display_name": descriptor.display_name,
            "source": descriptor.source,
            "revision": descriptor.revision,
            "capabilities": sorted(item.value for item in descriptor.capabilities),
            "installed_at": installed_at.astimezone(UTC).isoformat(),
        }
        if files is not None:
            payload["files"] = [
                {
                    "name": item.name,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in files
            ]
        return payload

    def _matches_manifest(
        self,
        directory: Path,
        descriptor: ModelDescriptor,
    ) -> bool:
        return self._installed_at(directory, descriptor) is not None

    def _installed_at(
        self,
        directory: Path,
        descriptor: ModelDescriptor,
    ) -> datetime | None:
        loaded = self._load_manifest(directory, descriptor)
        if loaded is None or not self._files_intact(directory, loaded[0].get("files")):
            return None
        return loaded[1]

    @staticmethod
    def _load_manifest(
        directory: Path,
        descriptor: ModelDescriptor,
    ) -> tuple[dict[str, object], datetime] | None:
        """Manifest fields and timestamp when identity matches (no file checks)."""
        try:
            raw_payload: object = json.loads(
                (directory / _MANIFEST_NAME).read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw_payload, dict):
            return None
        payload = cast(dict[str, object], raw_payload)
        if not (
            payload.get("provider_id") == descriptor.provider_id
            and payload.get("model_id") == descriptor.model_id
            and payload.get("source") == descriptor.source
            and payload.get("revision") == descriptor.revision
        ):
            return None
        raw_installed_at = payload.get("installed_at")
        if not isinstance(raw_installed_at, str):
            return None
        try:
            installed_at = datetime.fromisoformat(raw_installed_at)
        except ValueError:
            return None
        if installed_at.tzinfo is None or installed_at.utcoffset() is None:
            return None
        return payload, installed_at

    @staticmethod
    def _files_intact(directory: Path, raw_files: object) -> bool:
        """Manifests written by download/import list files; sizes must still match.

        Legacy ``install`` manifests carry no list and are trusted as before.
        """
        if raw_files is None:
            return True
        if not isinstance(raw_files, list) or not raw_files:
            return False
        for raw in cast(list[object], raw_files):
            if not isinstance(raw, dict):
                return False
            entry = cast(dict[str, object], raw)
            try:
                item = ModelFile(
                    cast(str, entry.get("name")),
                    cast(int, entry.get("size_bytes")),
                    cast("str | None", entry.get("sha256")),
                )
            except (TypeError, ValueError):
                return False
            if FileSystemModelStore._regular_size(directory / item.name) != (
                item.size_bytes
            ):
                return False
        return True

    @staticmethod
    def _regular_size(path: Path) -> int | None:
        """Size of a regular, non-symlink file, else None."""
        try:
            info = path.lstat()
        except OSError:
            return None
        return info.st_size if stat.S_ISREG(info.st_mode) else None

    def _write_manifest(
        self,
        directory: Path,
        descriptor: ModelDescriptor,
        installed_at: datetime,
        files: Sequence[ModelFile] | None = None,
    ) -> None:
        manifest = directory / _MANIFEST_NAME
        payload = self._manifest_payload(descriptor, installed_at, files)
        with manifest.open("x", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())

    @staticmethod
    def _sync_tree(directory: Path) -> None:
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ModelInstallationError(
                    ModelInstallationFailureCode.INVALID_SNAPSHOT,
                    "The downloaded model snapshot contains an unsafe link.",
                )
            if path.is_file():
                FileSystemModelStore._sync_file(path)
        FileSystemModelStore._sync_directory(directory)

    @staticmethod
    def _sync_file(path: Path) -> None:
        # Windows can only flush a descriptor opened for writing.
        windows = os.name == "nt"
        try:
            with path.open("r+b" if windows else "rb") as source:
                os.fsync(source.fileno())
        except PermissionError:
            # ponytail: a read-only (hard-linked) file on Windows keeps whatever
            # durability the OS gives it; its size and digest are verified on use.
            if not windows:
                raise

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        DirectoryHandle(directory, None).fsync()


__all__ = ["FileSystemModelStore", "SnapshotDownloader"]
