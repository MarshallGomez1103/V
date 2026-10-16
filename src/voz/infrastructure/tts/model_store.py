"""Explicit install of the pinned speech synthesis models (ADR-0010, V4-03).

One ``.tar.bz2`` per model from :mod:`voz.infrastructure.tts.catalog`, checked
against its pinned size and SHA-256 **before** anything is extracted, then
unpacked by hand (never ``extractall``): only the files the catalog names, the
``espeak-ng-data`` tree and the license notices are written, as regular files,
under ``<data>/models/tts/<model_id>/``. A member with an absolute or ``..``
path, or a link or device node among the files to extract, rejects the whole
archive. Nothing in an archive is ever executed. Stdlib only.

ponytail: the archive digest is the only integrity root; extracted files are
checked by size on each ``is_installed`` call, not hashed again.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import tarfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from voz.application.ports.custom_models import CustomValidation
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.domain.entities.voice import Voice
from voz.infrastructure.artifact_download import ArtifactFetcher
from voz.infrastructure.tts.catalog import (
    DATA_DIR_MARKER,
    NOTICE_FILES,
    TTS_CATALOG,
    TtsModelEntry,
)
from voz.infrastructure.tts.families import (
    ModelFilesError,
    discover_files,
    model_config,
    read_voices,
)
from voz.infrastructure.tts.subprocess_provider import TtsModelManifest

_Code = ModelInstallationFailureCode
_MANIFEST_NAME = ".voz-tts.json"
_EXTRACTED = "model"
_MAX_EXTRACTED_BYTES = 1024 * 1024 * 1024  # decompression-bomb guard (largest: 190 MB)


@dataclass(frozen=True, slots=True)
class _ArchiveLayout:
    root: str
    files: tuple[tuple[str, str], ...]
    directories: tuple[tuple[str, str], ...] = ()


def validate_custom_tts_load(family: str, files: dict[str, Path]) -> CustomValidation:
    """Load weights in the import validation child; never called by the server."""
    sherpa: Any = importlib.import_module("sherpa_onnx")
    spec = model_config(family, files)
    family_config = getattr(sherpa, spec.config_class)(**spec.kwargs)
    config = sherpa.OfflineTtsConfig(
        model=sherpa.OfflineTtsModelConfig(
            **{spec.field: family_config}, num_threads=1, provider="cpu"
        )
    )
    if not config.validate():
        raise ModelFilesError("invalid model configuration")
    engine = sherpa.OfflineTts(config)
    count = int(engine.num_speakers)
    if not 1 <= count <= 4096 or int(engine.sample_rate) <= 0:
        raise ModelFilesError("invalid model metadata")
    try:
        named = {voice.id: voice for voice in read_voices(family, files)}
    except ModelFilesError:
        named = {}
    voices = tuple(
        named.get(str(sid), Voice(str(sid), f"Speaker {sid}")) for sid in range(count)
    )
    languages = tuple(sorted({lang for voice in voices for lang in voice.languages}))
    return CustomValidation(voices, languages)


def extract_custom_archive(
    archive: Path,
    target: Path,
    allowed: Callable[[str], bool],
    cancelled: CancelCheck,
) -> None:
    """Inspect an untrusted tar, then reuse the catalog's bounded safe extractor."""
    try:
        with tarfile.open(archive, "r:bz2") as bundle:
            members: list[tarfile.TarInfo] = []
            total = 0
            for info in bundle:
                if cancelled():
                    raise ModelInstallationError(
                        _Code.CANCELLED, "The import was cancelled."
                    )
                total += info.size
                if (
                    _unsafe(info.name)
                    or not (info.isdir() or info.isreg())
                    or total > _MAX_EXTRACTED_BYTES
                    or len(members) >= 10_000
                ):
                    raise _invalid()
                members.append(info)
            names = [info.name for info in members if info.isreg()]
            roots = {PurePosixPath(name).parts[0] for name in names}
            root = (
                next(iter(roots))
                if len(roots) == 1 and all("/" in name for name in names)
                else ""
            )
            relative = [name[len(root) + 1 :] if root else name for name in names]
            files = tuple((name, name) for name in relative if allowed(name))
            if not files:
                raise _invalid()
        _extract(archive, _ArchiveLayout(root, files), target, cancelled)
    except (tarfile.TarError, EOFError, IndexError):
        raise _invalid() from None


def _invalid() -> ModelInstallationError:
    return ModelInstallationError(
        _Code.INVALID_SNAPSHOT, "The speech synthesis model archive is invalid."
    )


def _unsafe(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return (
        not name
        or "\\" in name
        or "\x00" in name
        or name.startswith("/")
        or ".." in parts
        or (len(name) > 1 and name[1] == ":")  # Windows drive
    )


def _clear(path: Path) -> int:
    """Delete a file, link or directory tree without following links."""
    if path.is_symlink() or path.is_file():
        size = 0 if path.is_symlink() else path.stat().st_size
        path.unlink()
        return size
    if not path.is_dir():
        return 0
    freed = sum(
        item.lstat().st_size
        for item in path.rglob("*")
        if item.is_file() and not item.is_symlink()
    )
    shutil.rmtree(path)
    return freed


def _extract(
    archive: Path,
    entry: TtsModelEntry | _ArchiveLayout,
    target: Path,
    cancelled: CancelCheck | None,
) -> dict[str, int]:
    """Write the wanted regular files under ``target``; return ``{relpath: size}``."""
    files = {rel for _, rel in entry.files}
    wanted = files | set(NOTICE_FILES)
    trees = tuple(f"{rel}/" for _, rel in entry.directories)
    sizes: dict[str, int] = {}
    total = 0
    try:
        with tarfile.open(archive, "r:bz2") as bundle:
            for info in bundle:
                if _unsafe(info.name):
                    raise _invalid()
                parts = PurePosixPath(info.name).parts
                if entry.root and (len(parts) < 2 or parts[0] != entry.root):
                    continue  # the root directory itself or foreign members
                rel = "/".join(parts[1:]) if entry.root else info.name
                if rel not in wanted and not rel.startswith(trees):
                    continue
                if cancelled is not None and cancelled():
                    raise ModelInstallationError(
                        _Code.CANCELLED, "The installation was cancelled."
                    )
                if info.isdir():
                    (target / rel).mkdir(parents=True, exist_ok=True)
                    continue
                total += info.size
                if (
                    not info.isreg()  # links and devices are never recreated
                    or rel in sizes
                    or total > _MAX_EXTRACTED_BYTES
                ):
                    raise _invalid()
                source = bundle.extractfile(info)
                if source is None:
                    raise _invalid()
                destination = target / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                # "xb" refuses to write through an existing file or link.
                with source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
                sizes[rel] = info.size
    except (tarfile.TarError, EOFError) as error:
        raise _invalid() from error
    complete = files <= set(sizes) and all(
        f"{tree}{DATA_DIR_MARKER}" in sizes for tree in trees
    )
    if not complete:
        raise _invalid()
    return {rel: size for rel, size in sizes.items() if rel in wanted}


class TtsModelStore:
    """Install, inspect and remove synthesis models under the XDG data root."""

    def __init__(
        self,
        *,
        data_root: Path,
        catalog: Sequence[TtsModelEntry] = TTS_CATALOG,
        network_timeout_seconds: float = 30.0,
        custom_manifest: Callable[[str], TtsModelManifest | None] | None = None,
    ) -> None:
        self._root = Path(data_root).absolute() / "models" / "tts"
        self._catalog = {entry.model_id: entry for entry in catalog}
        self._timeout = network_timeout_seconds
        self._custom_manifest = custom_manifest

    def _directory(self, entry: TtsModelEntry) -> Path:
        return self._root / entry.model_id

    def _staging(self, entry: TtsModelEntry) -> Path:
        # Stable name so an interrupted download resumes from its ``.part``.
        return self._root / f"{entry.model_id}.installing"

    # --- inspection ---------------------------------------------------------

    def is_installed(self, model_id: str) -> bool:
        entry = self._catalog.get(model_id)
        return entry is not None and self._intact(entry)

    def _intact(self, entry: TtsModelEntry) -> bool:
        directory = self._directory(entry)
        if directory.is_symlink():
            return False
        try:
            manifest = json.loads((directory / _MANIFEST_NAME).read_text())
            if manifest["sha256"] != entry.sha256:
                return False
            sizes = manifest["files"]
            for _, rel in entry.files:
                if (directory / rel).stat().st_size != sizes[rel]:
                    return False
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return False
        return all(
            (directory / rel / DATA_DIR_MARKER).is_file()
            for _, rel in entry.directories
        )

    def disk_usage(self, model_id: str) -> int | None:
        """Bytes on disk of an intact install, ``None`` if not installed."""
        entry = self._catalog.get(model_id)
        if entry is None or not self._intact(entry):
            return None
        return sum(
            item.lstat().st_size
            for item in self._directory(entry).rglob("*")
            if item.is_file() and not item.is_symlink()
        )

    def manifest(self, model_id: str) -> TtsModelManifest | None:
        """What the engine needs for an installed model; ``None`` otherwise."""
        entry = self._catalog.get(model_id)
        if entry is None and self._custom_manifest is not None:
            return self._custom_manifest(model_id)
        if entry is None or not self._intact(entry):
            return None
        directory = self._directory(entry)
        try:
            files = discover_files(entry.family, directory)
        except ModelFilesError:
            return None
        try:  # the ONNX metadata names the real speakers; the catalog backs it up
            voices = read_voices(entry.family, files, entry.languages, entry.voices)
        except ModelFilesError:
            voices = entry.voices  # unreadable metadata: the curated list
        return TtsModelManifest(
            family=entry.family,
            files=files,
            voices=voices,
            languages=entry.languages,
            ram_bytes=entry.ram_bytes,
            disk_bytes=self.disk_usage(model_id),
        )

    def manifests(self) -> dict[str, TtsModelManifest]:
        """Manifests of every installed model, keyed by ``model_id``."""
        found = {model_id: self.manifest(model_id) for model_id in self._catalog}
        return {model_id: item for model_id, item in found.items() if item}

    # --- install / remove ---------------------------------------------------

    def install(
        self,
        model_id: str,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> TtsModelManifest:
        """Download, verify, extract and publish atomically; resumes partials."""
        entry = self._catalog.get(model_id)
        if entry is None:
            raise ModelInstallationError(
                _Code.INVALID_SNAPSHOT, "The speech synthesis model is not known."
            )
        existing = self.manifest(model_id)
        if existing is not None:
            return existing
        staging = self._staging(entry)
        fetcher = ArtifactFetcher(
            staging,
            label="speech synthesis model",
            timeout_seconds=self._timeout,
        )

        def report(done: int) -> None:
            if progress is not None:
                progress(min(done, entry.size_bytes), entry.size_bytes)

        try:
            staging.mkdir(mode=0o700, parents=True, exist_ok=True)
            archive = fetcher.fetch(entry, report, cancelled)  # verified here
            extracted = staging / _EXTRACTED
            _clear(extracted)
            try:
                sizes = _extract(archive, entry, extracted, cancelled)
            except ModelInstallationError as error:
                if error.code is _Code.INVALID_SNAPSHOT:
                    _clear(staging)  # a verified archive that is unusable is final
                raise
            self._publish(entry, extracted, sizes)
            _clear(staging)
        except OSError as error:
            raise ModelInstallationError(
                _Code.IO_ERROR, "The speech synthesis model could not be written."
            ) from error
        published = self.manifest(model_id)
        if published is None:
            raise ModelInstallationError(
                _Code.INVALID_SNAPSHOT, "The speech synthesis model is incomplete."
            )
        return published

    def _publish(
        self, entry: TtsModelEntry, extracted: Path, sizes: dict[str, int]
    ) -> None:
        record = {
            "model_id": entry.model_id,
            "archive": entry.archive_name,
            "sha256": entry.sha256,
            "files": sizes,
            "installed_at": datetime.now(UTC).isoformat(),
        }
        with (extracted / _MANIFEST_NAME).open("w") as output:
            json.dump(record, output, indent=2)
            output.flush()
            os.fsync(output.fileno())  # the manifest is the commit marker
        directory = self._directory(entry)
        _clear(directory)  # stale or corrupt copy: replace it
        os.rename(extracted, directory)

    def remove(self, model_id: str) -> int:
        """Delete the install and any partial download; return the bytes freed."""
        entry = self._catalog.get(model_id)
        if entry is None:
            return 0
        return _clear(self._directory(entry)) + _clear(self._staging(entry))


__all__ = ["TtsModelStore"]
