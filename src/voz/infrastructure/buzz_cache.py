"""Read-only discovery of faster-whisper models already cached by Buzz.

Buzz keeps a HuggingFace hub layout (``models--<org>--<repo>/snapshots/<rev>``
whose files are symlinks into ``../../blobs``). Nothing here writes, creates or
opens files: only ``os.stat`` and ``os.path.realpath`` are used.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from voz.application.ports.external_models import ExternalModelCandidate
from voz.infrastructure.asr.catalog import faster_whisper_catalog

ORIGIN = "buzz"
_FLATPAK_MODELS = Path(".var/app/io.github.chidiwilliams.Buzz/cache/Buzz/models")


class _CatalogFile(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def size_bytes(self) -> int: ...


class _CatalogDescriptor(Protocol):
    @property
    def provenance(self) -> tuple[str, str] | None: ...


class _CatalogEntry(Protocol):
    @property
    def descriptor(self) -> _CatalogDescriptor: ...
    @property
    def files(self) -> Sequence[_CatalogFile]: ...


def default_buzz_roots(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[Path, ...]:
    """Candidate Buzz model roots; ``BUZZ_MODEL_ROOT=`` (empty) disables detection."""
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else home
    override = env.get("BUZZ_MODEL_ROOT")
    if override is not None and not override.strip():
        return ()
    cache_home = env.get("XDG_CACHE_HOME") or str(home_dir / ".cache")
    roots = [
        *([Path(override)] if override else []),
        home_dir / _FLATPAK_MODELS,
        Path(cache_home) / "Buzz" / "models",
    ]
    return tuple(dict.fromkeys(roots))


def _is_inside(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent.rstrip(os.sep) + os.sep)


def _regular_size(path: str) -> int | None:
    try:
        info = os.stat(path)  # follows symlinks; realpath already contained
    except OSError:
        return None
    return info.st_size if stat.S_ISREG(info.st_mode) else None


class BuzzModelCache:
    """Find catalog-exact, complete snapshots in Buzz's cache without touching it."""

    def __init__(
        self,
        roots: Sequence[Path] | None = None,
        catalog: Callable[[], Iterable[_CatalogEntry]] | None = None,
    ) -> None:
        self._roots = tuple(default_buzz_roots() if roots is None else roots)
        self._catalog = catalog if catalog is not None else faster_whisper_catalog

    def find_candidates(self) -> tuple[ExternalModelCandidate, ...]:
        entries = tuple(self._catalog())
        found: dict[tuple[str, str], ExternalModelCandidate] = {}
        for root in self._roots:
            try:
                real_root = os.path.realpath(root)
                if not os.path.isdir(real_root):
                    continue
                os.listdir(real_root)  # unreadable root: skip it entirely
            except OSError:
                continue
            for entry in entries:
                provenance = entry.descriptor.provenance
                if provenance is None or provenance in found:
                    continue
                candidate = self._inspect(real_root, provenance, entry.files)
                if candidate is not None:
                    found[provenance] = candidate
        return tuple(found.values())

    @staticmethod
    def _inspect(
        real_root: str,
        provenance: tuple[str, str],
        files: Sequence[_CatalogFile],
    ) -> ExternalModelCandidate | None:
        source, revision = provenance
        repo = os.path.join(real_root, "models--" + source.replace("/", "--"))
        snapshot = os.path.join(repo, "snapshots", revision)
        try:
            # Blobs must stay inside this model's own HF repo directory, and that
            # directory inside the root (a repo symlinked elsewhere is rejected).
            real_repo = os.path.realpath(repo)
            if not _is_inside(real_repo, real_root) or real_repo == real_root:
                return None
            if not _is_inside(os.path.realpath(snapshot), real_repo):
                return None
            if not os.path.isdir(snapshot):
                return None
            for item in files:
                path = os.path.join(snapshot, item.name)
                if not _is_inside(os.path.realpath(path), real_repo):
                    return None
                if _regular_size(path) != item.size_bytes:
                    return None
        except OSError:
            return None
        return ExternalModelCandidate(
            origin=ORIGIN,
            source=source,
            revision=revision,
            snapshot_dir=Path(snapshot),
            total_bytes=sum(item.size_bytes for item in files),
        )


__all__ = ["BuzzModelCache", "default_buzz_roots"]
