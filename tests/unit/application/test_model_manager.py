"""ListModels and RemoveModel with in-memory fakes; no filesystem or network."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from voz.application.model_manager import (
    ListModels,
    ModelManagementError,
    RemoveModel,
)
from voz.application.ports.diarization import DiarizationOptions
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
    kind: str = "asr"
    requires: str | None = None
    runtime_available: bool = True


TINY = descriptor("tiny", "a" * 40)
BASE = descriptor("base", "b" * 40)


class Catalog:
    def entries(self) -> tuple[Entry, ...]:
        return (Entry(TINY, (Item(10), Item(5))), Entry(BASE, (Item(100),)))


class Store:
    def __init__(self, *installed: ModelDescriptor, fail: bool = False) -> None:
        self.installed = {item: 1000 for item in installed}
        self.removed: list[ModelDescriptor] = []
        self.shared: dict[ModelDescriptor, int] = {}  # hardlinked with another cache
        self.fail = fail

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return descriptor in self.installed

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        return self.installed.get(descriptor)

    def reclaimable_usage(self, descriptor: ModelDescriptor) -> int | None:
        size = self.installed.get(descriptor)
        return None if size is None else size - self.shared.get(descriptor, 0)

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
    assert (tiny.key, tiny.provider_id, tiny.kind) == (
        "faster-whisper:tiny",
        "faster-whisper",
        "asr",
    )
    assert (tiny.size_bytes, tiny.installed, tiny.disk_bytes) == (15, True, 1000)
    assert [item.origin for item in tiny.external] == ["hf-cache"]
    assert (base.size_bytes, base.installed, base.disk_bytes) == (100, False, None)
    assert tiny.capabilities == tuple(sorted(c.value for c in TINY.capabilities))
    assert [item.origin for item in base.external] == ["buzz"]
    assert (result.disk.models_bytes, result.disk.free_bytes) == (1000, 777)


def test_hardlinked_imports_report_real_size_and_what_deleting_frees() -> None:
    store = Store(TINY)
    store.shared[TINY] = 1000  # imported from the Buzz cache: nothing to reclaim

    result = ListModels(Catalog(), store).execute()

    tiny = result.models[0]
    assert tiny.disk_bytes == 1000  # real size of the files, never 0
    assert (tiny.reclaimable_bytes, tiny.shared_bytes) == (0, 1000)
    assert (result.disk.models_bytes, result.disk.reclaimable_bytes) == (1000, 0)


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


def test_models_with_the_same_id_in_two_providers_are_addressed_by_key() -> None:
    cpp = replace(TINY, provider_id="whisper-cpp", revision="d" * 40)

    class Both:
        def entries(self) -> tuple[Entry, ...]:
            return (
                Entry(TINY, (Item(10),)),
                Entry(cpp, (Item(20),), requires="whisper-cli"),
            )

    store = Store(cpp)
    listed = ListModels(Both(), store).execute().models
    assert [m.key for m in listed] == ["faster-whisper:tiny", "whisper-cpp:tiny"]
    assert [m.installed for m in listed] == [False, True]
    assert listed[1].requires == "whisper-cli"

    with pytest.raises(ModelManagementError) as raised:  # bare id = faster-whisper
        RemoveModel(Both(), store, Jobs(), Selections()).execute("tiny", "tiny")
    assert raised.value.code == "model_not_installed"

    key = "whisper-cpp:tiny"
    removed = RemoveModel(Both(), store, Jobs(), Selections()).execute(key, key)
    assert (removed.key, removed.model_id, store.removed) == (key, "tiny", [cpp])


def test_diarization_entry_reports_kind_and_missing_runtime() -> None:
    diar = ModelDescriptor(
        provider_id="diarization",
        model_id="sherpa-default",
        display_name="Hablantes",
        capabilities=frozenset({ModelCapability.DIARIZATION}),
    )

    class Catalog1:
        def entries(self) -> tuple[Entry, ...]:
            return (
                Entry(
                    diar,
                    (Item(7),),
                    kind="diarization",
                    requires="diarization",
                    runtime_available=False,
                ),
            )

    (item,) = ListModels(Catalog1(), Store()).execute().models
    assert (item.key, item.kind, item.requires, item.runtime_available) == (
        "diarization:sherpa-default",
        "diarization",
        "diarization",
        False,
    )
    assert (item.source, item.revision, item.profile) == (None, None, None)


DIAR = ModelDescriptor(
    provider_id="diarization",
    model_id="sherpa-default",
    display_name="Hablantes",
    capabilities=frozenset({ModelCapability.DIARIZATION}),
)
DIAR_KEY = "diarization:sherpa-default"


class CatalogWithDiarization:
    def entries(self) -> tuple[Entry, ...]:
        return (
            Entry(TINY, (Item(10),)),
            Entry(BASE, (Item(100),)),
            Entry(DIAR, (Item(7),), kind="diarization"),
        )


def job_wanting_speakers(
    selections: Selections, *, error_code: str | None = None
) -> TranscriptionJob:
    job = running_job(selections, TINY)  # the ASR model is a different one
    selections.items[job.id] = replace(
        selections.items[job.id],
        diarization=DiarizationOptions(),
        diarization_error_code=error_code,
    )
    return job


def diarization_remover(
    store: Store,
    *jobs: TranscriptionJob,
    selections: Selections,
    on_removed: object = None,
) -> RemoveModel:
    return RemoveModel(
        CatalogWithDiarization(),
        store,
        Jobs(*jobs),
        selections,
        on_removed=on_removed,  # type: ignore[arg-type]
    )


def test_remove_refuses_diarization_models_while_a_job_wants_speakers() -> None:
    selections = Selections()
    store = Store(DIAR)
    job = job_wanting_speakers(selections)

    with pytest.raises(ModelManagementError) as raised:
        diarization_remover(store, job, selections=selections).execute(
            DIAR_KEY, DIAR_KEY
        )

    assert raised.value.code == "model_in_use"
    assert store.removed == []


def test_remove_diarization_models_ignores_jobs_without_speakers() -> None:
    selections = Selections()
    store = Store(DIAR)
    plain = running_job(selections, TINY)  # diarization disabled
    gave_up = job_wanting_speakers(selections, error_code="diarization_failed")
    removed: list[ModelDescriptor] = []

    result = diarization_remover(
        store, plain, gave_up, selections=selections, on_removed=removed.append
    ).execute(DIAR_KEY, DIAR_KEY)

    assert (result.key, store.removed) == (DIAR_KEY, [DIAR])
    assert removed == [DIAR]


def test_asr_removal_is_not_blocked_by_a_job_that_only_wants_speakers() -> None:
    selections = Selections()
    store = Store(BASE)
    job = job_wanting_speakers(selections)  # uses TINY, BASE is unrelated

    result = diarization_remover(store, job, selections=selections).execute(
        "base", "base"
    )

    assert result.model_id == "base"


def test_failed_removal_does_not_notify_the_listener() -> None:
    removed: list[ModelDescriptor] = []

    with pytest.raises(ModelManagementError):
        diarization_remover(
            Store(DIAR, fail=True), selections=Selections(), on_removed=removed.append
        ).execute(DIAR_KEY, DIAR_KEY)

    assert removed == []
