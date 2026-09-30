"""ListModels and RemoveModel with in-memory fakes; no filesystem or network."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from voz.application.model_manager import (
    ListModels,
    ModelManagementError,
    RemoveModel,
)
from voz.application.ports.disk_space import DiskLocation
from voz.application.ports.external_models import ExternalModelCandidate
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)

NOW = datetime(2026, 9, 30, 10, tzinfo=UTC)
PROFILE = ProcessingProfile(
    ProcessingProfileName.QUALITY,
    DevicePreference.GPU_PREFERRED,
    (ComputePrecision.FLOAT16,),
    ComputePrecision.INT8,
)


def descriptor(model_id: str, revision: str) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id=model_id,
        display_name=model_id.title(),
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        source=f"publisher/{model_id}",
        revision=revision,
        profile=PROFILE,
    )


@dataclass(frozen=True)
class Item:
    size_bytes: int


@dataclass(frozen=True)
class Entry:
    descriptor: ModelDescriptor
    files: tuple[Item, ...]
    license: str = "MIT"
    multilingual: bool = True


TINY = descriptor("tiny", "a" * 40)
BASE = descriptor("base", "b" * 40)


class Catalog:
    def entries(self) -> tuple[Entry, ...]:
        return (Entry(TINY, (Item(10), Item(5))), Entry(BASE, (Item(100),)))


class Store:
    def __init__(self, *installed: ModelDescriptor, fail: bool = False) -> None:
        self.installed = {item: 1000 for item in installed}
        self.removed: list[ModelDescriptor] = []
        self.fail = fail

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return descriptor in self.installed

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        return self.installed.get(descriptor)

    def remove(self, descriptor: ModelDescriptor) -> int:
        if self.fail:
            raise OSError("/private/host/path")
        self.removed.append(descriptor)
        return self.installed.pop(descriptor)


class Disk:
    def free_bytes(self, location: DiskLocation) -> int:
        return 777


def candidate(source: str, revision: str, origin: str) -> ExternalModelCandidate:
    return ExternalModelCandidate(
        origin, source, revision, Path("/private/host/cache"), 1
    )


class External:
    def find_candidates(self) -> tuple[ExternalModelCandidate, ...]:
        return (
            candidate("publisher/base", "b" * 40, "buzz"),
            candidate("publisher/base", "b" * 40, "buzz"),
            candidate("publisher/base", "c" * 40, "other-revision"),
            candidate("publisher/tiny", "a" * 40, "hf-cache"),
        )


class Jobs:
    def __init__(self, *jobs: TranscriptionJob) -> None:
        self.jobs = jobs

    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        return self.jobs


class Selections:
    def __init__(self) -> None:
        self.items: dict[UUID, JobSelection] = {}

    def get(self, job_id: UUID) -> JobSelection | None:
        return self.items.get(job_id)


def running_job(selections: Selections, model: ModelDescriptor) -> TranscriptionJob:
    job = TranscriptionJob(
        uuid4(), uuid4(), uuid4(), TranscriptionJobState.QUEUED, 0.0, NOW, NOW
    )
    selections.items[job.id] = JobSelection(job.id, "option-x", model, None, None, NOW)
    return job


def test_list_reports_catalog_state_sizes_disk_and_external_origins() -> None:
    result = ListModels(Catalog(), Store(TINY), Disk(), External()).execute()

    tiny, base = result.models
    assert (tiny.model_id, tiny.profile, tiny.license, tiny.multilingual) == (
        "tiny",
        "quality",
        "MIT",
        True,
    )
    assert (tiny.size_bytes, tiny.installed, tiny.disk_bytes) == (15, True, 1000)
    assert [item.origin for item in tiny.external] == ["hf-cache"]
    assert (base.size_bytes, base.installed, base.disk_bytes) == (100, False, None)
    assert [item.origin for item in base.external] == ["buzz"]
    assert (result.disk.models_bytes, result.disk.free_bytes) == (1000, 777)


def test_list_without_optional_ports_has_no_free_bytes_or_external() -> None:
    result = ListModels(Catalog(), Store()).execute()

    assert result.disk.free_bytes is None
    assert result.disk.models_bytes == 0
    assert all(model.external == () for model in result.models)


def remover(
    store: Store, *jobs: TranscriptionJob, selections: Selections
) -> RemoveModel:
    return RemoveModel(Catalog(), store, Jobs(*jobs), selections)


@pytest.mark.parametrize("confirm", [None, "", "tin", "TINY", "base"])
def test_remove_requires_the_exact_model_id(confirm: str | None) -> None:
    store = Store(TINY)

    with pytest.raises(ModelManagementError) as raised:
        remover(store, selections=Selections()).execute("tiny", confirm)

    assert raised.value.code == "model_delete_unconfirmed"
    assert store.removed == []


@pytest.mark.parametrize("model_id", ["base", "unknown"])
def test_remove_rejects_models_that_are_not_installed(model_id: str) -> None:
    with pytest.raises(ModelManagementError) as raised:
        remover(Store(TINY), selections=Selections()).execute(model_id, model_id)

    assert raised.value.code == "model_not_installed"


def test_remove_refuses_a_model_used_by_an_unfinished_job() -> None:
    selections = Selections()
    store = Store(TINY)

    with pytest.raises(ModelManagementError) as raised:
        remover(store, running_job(selections, TINY), selections=selections).execute(
            "tiny", "tiny"
        )

    assert raised.value.code == "model_in_use"
    assert store.removed == []


def test_remove_ignores_jobs_using_other_models_or_revisions() -> None:
    selections = Selections()
    store = Store(TINY)
    jobs = (
        running_job(selections, BASE),
        running_job(selections, descriptor("tiny", "c" * 40)),
        TranscriptionJob(
            uuid4(), uuid4(), uuid4(), TranscriptionJobState.QUEUED, 0.0, NOW, NOW
        ),
    )

    result = remover(store, *jobs, selections=selections).execute("tiny", "tiny")

    assert (result.model_id, result.freed_bytes) == ("tiny", 1000)
    assert store.removed == [TINY]


def test_remove_translates_io_errors_without_leaking_paths() -> None:
    with pytest.raises(ModelManagementError) as raised:
        remover(Store(TINY, fail=True), selections=Selections()).execute("tiny", "tiny")

    assert raised.value.code == "model_remove_failed"
    assert "/private" not in raised.value.user_message
