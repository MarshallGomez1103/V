"""Explicit XDG model installation with pinned provenance and atomic publication."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from errno import EEXIST, ENOTEMPTY
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from voz.application.ports.model_installation import (
    ModelInstallation,
    ModelInstallationError,
    ModelInstallationFailureCode,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.domain.entities.model_descriptor import ModelDescriptor

_MANIFEST_NAME = ".voz-model.json"


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
    ) -> None:
        self._models_root = Path(data_root).absolute() / "models"
        self._downloads_root = Path(cache_root).absolute() / "downloads"
        self._downloader_factory = downloader_factory
        self._clock = clock

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
            self._write_manifest(staging, descriptor, installed_at)
            self._sync_tree(staging)
            try:
                os.rename(staging, final_directory)
            except OSError as error:
                if error.errno not in {EEXIST, ENOTEMPTY}:
                    raise
                winner_timestamp = self._installed_at(
                    final_directory,
                    descriptor,
                )
                if winner_timestamp is None:
                    raise
                installed_at = winner_timestamp
            self._sync_directory(final_directory.parent)
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

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        """Resolve a local path for infrastructure use without network access."""
        directory = self._directory_for(descriptor)
        if not self._matches_manifest(directory, descriptor):
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected transcription model is not installed.",
            )
        return directory

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
    def _manifest_payload(
        descriptor: ModelDescriptor,
        installed_at: datetime,
    ) -> dict[str, object]:
        return {
            "provider_id": descriptor.provider_id,
            "model_id": descriptor.model_id,
            "display_name": descriptor.display_name,
            "source": descriptor.source,
            "revision": descriptor.revision,
            "capabilities": sorted(item.value for item in descriptor.capabilities),
            "installed_at": installed_at.astimezone(UTC).isoformat(),
        }

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
        return installed_at

    def _write_manifest(
        self,
        directory: Path,
        descriptor: ModelDescriptor,
        installed_at: datetime,
    ) -> None:
        manifest = directory / _MANIFEST_NAME
        payload = self._manifest_payload(descriptor, installed_at)
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
                with path.open("rb") as source:
                    os.fsync(source.fileno())
        FileSystemModelStore._sync_directory(directory)

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


__all__ = ["FileSystemModelStore", "SnapshotDownloader"]
