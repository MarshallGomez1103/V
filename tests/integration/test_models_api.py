"""HTTP contract of /api/models tested through ASGI with fake ports."""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from starlette.types import Message

from voz.application.model_manager import ListModels, RemoveModel
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
from voz.interfaces.api.models import create_models_router

NOW = datetime(2026, 9, 30, 10, tzinfo=UTC)


def descriptor(model_id: str, revision: str) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id=model_id,
        display_name=model_id.title(),
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        source=f"publisher/{model_id}",
        revision=revision,
        profile=ProcessingProfile(
            ProcessingProfileName.QUALITY,
            DevicePreference.GPU_PREFERRED,
            (ComputePrecision.FLOAT16,),
            ComputePrecision.INT8,
        ),
    )


TINY = descriptor("tiny", "a" * 40)
BASE = descriptor("base", "b" * 40)


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


class Catalog:
    def entries(self) -> tuple[Entry, ...]:
        return (Entry(TINY, (Item(10), Item(5))), Entry(BASE, (Item(100),)))


class Store:
    def __init__(self, *installed: ModelDescriptor) -> None:
        self.installed = {item: 1000 for item in installed}
        self.removed: list[ModelDescriptor] = []
        self.shared: dict[ModelDescriptor, int] = {}  # hardlinked with another cache

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return descriptor in self.installed

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        return self.installed.get(descriptor)

    def reclaimable_usage(self, descriptor: ModelDescriptor) -> int | None:
        size = self.installed.get(descriptor)
        return None if size is None else size - self.shared.get(descriptor, 0)

    def remove(self, descriptor: ModelDescriptor) -> int:
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


async def request(
    app: FastAPI, method: str, path: str, query: str = ""
) -> tuple[int, dict[str, object]]:
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": [],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    body = b"".join(message.get("body", b"") for message in messages)
    return int(messages[0]["status"]), cast(dict[str, object], json.loads(body))


def build(store: Store, selections: Selections, *jobs: TranscriptionJob) -> FastAPI:
    app = FastAPI()
    catalog = Catalog()
    app.include_router(
        create_models_router(
            ListModels(catalog, store, Disk(), External()),
            RemoveModel(catalog, store, Jobs(*jobs), selections),
        )
    )
    return app


def test_get_models_serializes_the_documented_contract_without_paths() -> None:
    status, body = asyncio.run(
        request(build(Store(TINY), Selections()), "GET", "/api/models")
    )

    assert status == 200
    assert body["disk"] == {
        "models_bytes": 1000,
        "free_bytes": 777,
        "reclaimable_bytes": 1000,
    }
    models = cast(list[dict[str, object]], body["models"])
    assert models[0] == {
        "key": "faster-whisper:tiny",
        "provider_id": "faster-whisper",
        "kind": "asr",
        "requires": None,
        "runtime_available": True,
        "model_id": "tiny",
        "display_name": "Tiny",
        "source": "publisher/tiny",
        "revision": "a" * 40,
        "license": "MIT",
        "multilingual": True,
        "capabilities": ["transcription"],
        "profile": "quality",
        "size_bytes": 15,
        "installed": True,
        "disk_bytes": 1000,
        "reclaimable_bytes": 1000,
        "shared_bytes": 0,
        "external": [{"origin": "hf-cache"}],
    }
    assert models[1]["installed"] is False
    assert models[1]["disk_bytes"] is None
    assert models[1]["reclaimable_bytes"] is None
    assert models[1]["shared_bytes"] is None
    assert models[1]["external"] == [{"origin": "buzz"}]
    assert "/" not in json.dumps({**models[1], "source": "", "display_name": ""})


def test_delete_model_frees_bytes() -> None:
    store = Store(TINY)
    status, body = asyncio.run(
        request(
            build(store, Selections()), "DELETE", "/api/models/tiny", "confirm=tiny"
        )
    )

    assert (status, body) == (
        200,
        {"key": "faster-whisper:tiny", "model_id": "tiny", "freed_bytes": 1000},
    )
    assert store.removed == [TINY]


def test_delete_requires_matching_confirmation() -> None:
    for query in ("", "confirm=base"):
        status, body = asyncio.run(
            request(
                build(Store(TINY), Selections()), "DELETE", "/api/models/tiny", query
            )
        )
        assert status == 400
        assert (
            cast(dict[str, str], body["detail"])["code"] == "model_delete_unconfirmed"
        )


def test_delete_missing_model_is_404() -> None:
    status, body = asyncio.run(
        request(
            build(Store(TINY), Selections()),
            "DELETE",
            "/api/models/base",
            "confirm=base",
        )
    )

    assert status == 404
    assert cast(dict[str, str], body["detail"])["code"] == "model_not_installed"


def test_delete_model_in_use_is_409_and_keeps_the_files() -> None:
    selections = Selections()
    store = Store(TINY, BASE)
    status, body = asyncio.run(
        request(
            build(store, selections, running_job(selections, TINY)),
            "DELETE",
            "/api/models/tiny",
            "confirm=tiny",
        )
    )

    assert status == 409
    assert cast(dict[str, str], body["detail"])["code"] == "model_in_use"
    assert store.removed == []
