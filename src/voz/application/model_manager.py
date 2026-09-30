"""Query and remove locally installed models, always by canonical catalog id."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from voz.application.ports.disk_space import DiskLocation, DiskSpacePort
from voz.application.ports.external_models import ExternalModelSource
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.transcription_job import TranscriptionJob


class CatalogFile(Protocol):
    @property
    def size_bytes(self) -> int: ...


class CatalogItem(Protocol):
    """Shape of an infrastructure catalog entry, without importing it."""

    @property
    def descriptor(self) -> ModelDescriptor: ...
    @property
    def files(self) -> Sequence[CatalogFile]: ...
    @property
    def license(self) -> str: ...
    @property
    def multilingual(self) -> bool: ...


class ModelCatalog(Protocol):
    def entries(self) -> Sequence[CatalogItem]: ...


class ModelStore(Protocol):
    def is_installed(self, descriptor: ModelDescriptor) -> bool: ...
    def disk_usage(self, descriptor: ModelDescriptor) -> int | None: ...
    def remove(self, descriptor: ModelDescriptor) -> int: ...


class RecoverableJobs(Protocol):
    """Subset of ``TranscriptionJobRepository``: jobs that have not finished."""

    def list_recoverable(self) -> Sequence[TranscriptionJob]: ...


class SelectionLookup(Protocol):
    """Subset of ``TranscriptionJobSelectionRepository``."""

    def get(self, job_id: UUID) -> JobSelection | None: ...


class ModelManagementFailureCode:
    DELETE_UNCONFIRMED = "model_delete_unconfirmed"
    NOT_INSTALLED = "model_not_installed"
    IN_USE = "model_in_use"
    REMOVE_FAILED = "model_remove_failed"


class ModelManagementError(Exception):
    """Typed failure with a stable code and a path-free message."""

    def __init__(self, code: str, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class ExternalOrigin:
    origin: str


@dataclass(frozen=True, slots=True)
class ModelStatus:
    model_id: str
    display_name: str
    source: str | None
    revision: str | None
    license: str
    multilingual: bool
    profile: str | None
    size_bytes: int
    installed: bool
    disk_bytes: int | None
    external: tuple[ExternalOrigin, ...]


@dataclass(frozen=True, slots=True)
class DiskSummary:
    models_bytes: int
    free_bytes: int | None


@dataclass(frozen=True, slots=True)
class ModelList:
    models: tuple[ModelStatus, ...]
    disk: DiskSummary


@dataclass(frozen=True, slots=True)
class ListModels:
    catalog: ModelCatalog
    store: ModelStore
    disk_space: DiskSpacePort | None = None
    external: ExternalModelSource | None = None

    def execute(self) -> ModelList:
        candidates = () if self.external is None else self.external.find_candidates()
        models: list[ModelStatus] = []
        for entry in self.catalog.entries():
            descriptor = entry.descriptor
            installed = self.store.is_installed(descriptor)
            origins = sorted(
                {
                    item.origin
                    for item in candidates
                    if (item.source, item.revision) == descriptor.provenance
                }
            )
            models.append(
                ModelStatus(
                    model_id=descriptor.model_id,
                    display_name=descriptor.display_name,
                    source=descriptor.source,
                    revision=descriptor.revision,
                    license=entry.license,
                    multilingual=entry.multilingual,
                    profile=None
                    if descriptor.profile is None
                    else descriptor.profile.name.value,
                    size_bytes=sum(file.size_bytes for file in entry.files),
                    installed=installed,
                    disk_bytes=self.store.disk_usage(descriptor) if installed else None,
                    external=tuple(ExternalOrigin(origin) for origin in origins),
                )
            )
        # ponytail: models share the data volume with originals/derivatives.
        free = (
            None
            if self.disk_space is None
            else self.disk_space.free_bytes(DiskLocation.ORIGINALS)
        )
        used = sum(item.disk_bytes or 0 for item in models)
        return ModelList(tuple(models), DiskSummary(used, free))


@dataclass(frozen=True, slots=True)
class RemovedModel:
    model_id: str
    freed_bytes: int


@dataclass(frozen=True, slots=True)
class RemoveModel:
    catalog: ModelCatalog
    store: ModelStore
    jobs: RecoverableJobs
    selections: SelectionLookup

    def execute(self, model_id: str, confirm: str | None) -> RemovedModel:
        """Delete the pinned install after exact-id confirmation and an in-use check."""
        if confirm != model_id:
            raise ModelManagementError(
                ModelManagementFailureCode.DELETE_UNCONFIRMED,
                "Repeat the exact model id to confirm deletion.",
            )
        descriptor = next(
            (
                entry.descriptor
                for entry in self.catalog.entries()
                if entry.descriptor.model_id == model_id
            ),
            None,
        )
        if descriptor is None or not self.store.is_installed(descriptor):
            raise ModelManagementError(
                ModelManagementFailureCode.NOT_INSTALLED,
                "The model is not installed.",
            )
        # ponytail: a job created between this check and remove() is not guarded.
        for job in self.jobs.list_recoverable():
            selection = self.selections.get(job.id)
            if (
                selection is not None
                and selection.model.identity == descriptor.identity
                and selection.model.provenance == descriptor.provenance
            ):
                raise ModelManagementError(
                    ModelManagementFailureCode.IN_USE,
                    "The model is used by a job that has not finished.",
                )
        try:
            freed = self.store.remove(descriptor)
        except OSError as error:
            raise ModelManagementError(
                ModelManagementFailureCode.REMOVE_FAILED,
                "The model could not be removed.",
            ) from error
        return RemovedModel(model_id, freed)


__all__ = [
    "DiskSummary",
    "ExternalOrigin",
    "ListModels",
    "ModelCatalog",
    "ModelList",
    "ModelManagementError",
    "ModelManagementFailureCode",
    "ModelStatus",
    "ModelStore",
    "RemoveModel",
    "RemovedModel",
]
