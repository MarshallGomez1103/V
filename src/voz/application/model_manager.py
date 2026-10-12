"""Query and remove locally installed models, always by canonical catalog id."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from voz.application.admission import AdmissionGate
from voz.application.model_keys import model_key, normalize_key
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
    @property
    def kind(self) -> str:
        """``asr`` or ``diarization``."""
        ...

    @property
    def requires(self) -> str | None:
        """Runtime the model needs to be usable (``whisper-cli``), if any."""
        ...

    @property
    def runtime_available(self) -> bool: ...


class ModelCatalog(Protocol):
    def entries(self) -> Sequence[CatalogItem]: ...


class ModelStore(Protocol):
    def is_installed(self, descriptor: ModelDescriptor) -> bool: ...
    def disk_usage(self, descriptor: ModelDescriptor) -> int | None: ...
    def reclaimable_usage(self, descriptor: ModelDescriptor) -> int | None: ...
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
    key: str
    provider_id: str
    kind: str
    requires: str | None
    runtime_available: bool
    model_id: str
    display_name: str
    source: str | None
    revision: str | None
    license: str
    multilingual: bool
    capabilities: tuple[str, ...]
    """``ModelCapability`` values the model declares, sorted (vocabulary in
    ``docs/api/models.md``)."""
    profile: str | None
    size_bytes: int
    installed: bool
    disk_bytes: int | None
    reclaimable_bytes: int | None
    """Bytes freed by deleting it: ``disk_bytes`` minus files shared (hardlinked)
    with another tool's cache, which stay on disk. ``None`` when not installed."""
    shared_bytes: int | None
    """``disk_bytes - reclaimable_bytes``: the model's size that deleting would not
    free because another copy (e.g. Buzz) still holds it."""
    external: tuple[ExternalOrigin, ...]


@dataclass(frozen=True, slots=True)
class DiskSummary:
    models_bytes: int
    free_bytes: int | None
    reclaimable_bytes: int = 0
    """Sum of ``reclaimable_bytes`` of the installed models."""


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
            disk_bytes = self.store.disk_usage(descriptor) if installed else None
            reclaimable = (
                self.store.reclaimable_usage(descriptor) if installed else None
            )
            origins = sorted(
                {
                    item.origin
                    for item in candidates
                    if (item.source, item.revision) == descriptor.provenance
                }
            )
            models.append(
                ModelStatus(
                    key=model_key(descriptor),
                    provider_id=descriptor.provider_id,
                    kind=entry.kind,
                    requires=entry.requires,
                    runtime_available=entry.runtime_available,
                    model_id=descriptor.model_id,
                    display_name=descriptor.display_name,
                    source=descriptor.source,
                    revision=descriptor.revision,
                    license=entry.license,
                    multilingual=entry.multilingual,
                    capabilities=tuple(
                        sorted(c.value for c in descriptor.capabilities)
                    ),
                    profile=None
                    if descriptor.profile is None
                    else descriptor.profile.name.value,
                    size_bytes=sum(file.size_bytes for file in entry.files),
                    installed=installed,
                    disk_bytes=disk_bytes,
                    reclaimable_bytes=reclaimable,
                    shared_bytes=(
                        None
                        if disk_bytes is None or reclaimable is None
                        else max(0, disk_bytes - reclaimable)
                    ),
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
        reclaimable_total = sum(item.reclaimable_bytes or 0 for item in models)
        return ModelList(tuple(models), DiskSummary(used, free, reclaimable_total))


@dataclass(frozen=True, slots=True)
class RemovedModel:
    key: str
    model_id: str
    freed_bytes: int


@dataclass(frozen=True, slots=True)
class RemoveModel:
    catalog: ModelCatalog
    store: ModelStore
    jobs: RecoverableJobs
    selections: SelectionLookup
    on_removed: Callable[[ModelDescriptor], None] | None = None
    """Called after a successful delete, e.g. to drop an engine cached on its files."""
    admission: AdmissionGate = field(default_factory=AdmissionGate)
    """Shared with job creation; the default is a private gate."""

    def execute(self, model_id: str, confirm: str | None) -> RemovedModel:
        """Delete the pinned install after exact-id confirmation and an in-use check.

        ``model_id`` is a key (``provider:model``) or a bare faster-whisper id;
        ``confirm`` must repeat it exactly as sent.
        """
        if confirm != model_id:
            raise ModelManagementError(
                ModelManagementFailureCode.DELETE_UNCONFIRMED,
                "Repeat the exact model id to confirm deletion.",
            )
        key = normalize_key(model_id)
        entry = next(
            (
                item
                for item in self.catalog.entries()
                if model_key(item.descriptor) == key
            ),
            None,
        )
        if entry is None or not self.store.is_installed(entry.descriptor):
            raise ModelManagementError(
                ModelManagementFailureCode.NOT_INSTALLED,
                "The model is not installed.",
            )
        descriptor = entry.descriptor
        # The in-use check and the delete are atomic against job creation.
        with self.admission.hold():
            for job in self.jobs.list_recoverable():
                selection = self.selections.get(job.id)
                if selection is not None and (
                    _uses_asr_model(selection, descriptor)
                    if entry.kind != "diarization"
                    else _wants_speakers(selection)
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
        if self.on_removed is not None:
            self.on_removed(descriptor)
        return RemovedModel(key, descriptor.model_id, freed)


def _uses_asr_model(selection: JobSelection, descriptor: ModelDescriptor) -> bool:
    return (
        selection.model.identity == descriptor.identity
        and selection.model.provenance == descriptor.provenance
    )


def _wants_speakers(selection: JobSelection) -> bool:
    """Diarization requested and not already given up on (a recorded error is final)."""
    return (
        selection.diarization is not None and selection.diarization_error_code is None
    )


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
