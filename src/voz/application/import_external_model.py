"""Reuse a compatible model from another tool's cache without moving the original."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from voz.application.ports.external_models import (
    ExternalModelCandidate,
    ExternalModelError,
    ExternalModelFailureCode,
    ExternalModelSource,
)
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ModelInstallation,
    ProgressCallback,
)
from voz.domain.entities.model_descriptor import ModelDescriptor


class _CatalogEntry(Protocol):
    @property
    def descriptor(self) -> ModelDescriptor: ...
    @property
    def files(self) -> Sequence[ModelFile]: ...


class _LocalSnapshotStore(Protocol):
    def import_local_snapshot(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        snapshot_dir: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation: ...


class ImportExternalModel:
    """Match external candidates against the catalog and hand them to the store."""

    def __init__(
        self,
        source: ExternalModelSource,
        store: _LocalSnapshotStore,
        catalog: Sequence[_CatalogEntry],
    ) -> None:
        self._source = source
        self._store = store
        self._catalog = tuple(catalog)

    def available(
        self, origin: str = "buzz"
    ) -> tuple[tuple[ModelDescriptor, ExternalModelCandidate], ...]:
        """Catalog models that ``origin`` already holds, ready to import."""
        by_provenance = {
            candidate.source + "\0" + candidate.revision: candidate
            for candidate in self._source.find_candidates()
            if candidate.origin == origin
        }
        return tuple(
            (entry.descriptor, by_provenance[key])
            for entry in self._catalog
            if entry.descriptor.provenance is not None
            and (key := "\0".join(entry.descriptor.provenance)) in by_provenance
        )

    def execute(
        self,
        model_id: str,
        origin: str = "buzz",
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        entry = next(
            (item for item in self._catalog if item.descriptor.model_id == model_id),
            None,
        )
        if entry is None:
            raise ExternalModelError(
                ExternalModelFailureCode.UNKNOWN_MODEL,
                "The requested model is not in the VOZ catalog.",
            )
        candidate = next(
            (
                found
                for descriptor, found in self.available(origin)
                if descriptor == entry.descriptor
            ),
            None,
        )
        if candidate is None:
            raise ExternalModelError(
                ExternalModelFailureCode.NOT_FOUND,
                "No compatible copy of this model was found to reuse.",
            )
        return self._store.import_local_snapshot(
            entry.descriptor,
            entry.files,
            candidate.snapshot_dir,
            progress=progress,
            cancelled=cancelled,
        )


__all__ = ["ImportExternalModel"]
