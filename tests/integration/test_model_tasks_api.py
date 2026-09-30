"""HTTP contract of /api/models/{id}/install and /api/model-tasks.

Fake ports first; then the real ``FileSystemModelStore`` against a local
``http.server`` (no real network).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.application.import_external_model import ImportExternalModel
from voz.application.model_tasks import ModelTaskRunner
from voz.application.ports.external_models import ExternalModelCandidate
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ModelInstallation,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure import model_storage
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.interfaces.api.model_tasks import create_model_tasks_router

NOW = datetime(2026, 9, 30, 10, tzinfo=UTC)
REVISION = "0123456789abcdef0123456789abcdef01234567"
BIN = bytes(range(256)) * 32  # 8 KiB
CFG = b'{"fixture": true}'
VIEW_KEYS = {
    "id",
    "model_id",
    "method",
    "origin",
    "state",
    "done_bytes",
    "total_bytes",
    "error_code",
    "created_at",
    "updated_at",
}


def make(model_id: str) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id=model_id,
        display_name=model_id.title(),
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        source=f"example/{model_id}",
        revision=REVISION,
    )


@dataclass(frozen=True)
class Entry:
    descriptor: ModelDescriptor
    files: tuple[ModelFile, ...]


class Catalog:
    def __init__(self, *entries: Entry) -> None:
        self._entries = entries

    def entries(self) -> tuple[Entry, ...]:
        return self._entries


def client(runner: ModelTaskRunner) -> httpx.Client:
    app = FastAPI()
    app.include_router(create_model_tasks_router(runner))
    # TestClient is an httpx.Client; its own stubs resolve to Unknown under pyright.
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def code_of(response: httpx.Response) -> str:
    return cast(str, response.json()["detail"]["code"])


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


# --- fake ports -------------------------------------------------------------


class FakeStore:
    def __init__(self) -> None:
        self.installed: set[str] = set()
        self.gate = Event()
        self.started = Event()

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return descriptor.model_id in self.installed

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        if progress:
            progress(30, sum(f.size_bytes for f in files))
        self.started.set()
        while not self.gate.wait(0.005):
            if cancelled is not None and cancelled():
                raise ModelInstallationError(
                    ModelInstallationFailureCode.CANCELLED, "cancelled"
                )
        self.installed.add(descriptor.model_id)
        return ModelInstallation(descriptor, NOW)


class FakeExternal:
    def available(
        self, origin: str = "buzz"
    ) -> tuple[tuple[ModelDescriptor, str], ...]:
        return ((make("base"), origin),)

    def execute(
        self,
        model_id: str,
        origin: str = "buzz",
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        del origin, progress, cancelled
        return ModelInstallation(make(model_id), NOW)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def api(store: FakeStore) -> Iterator[httpx.Client]:
    catalog = Catalog(
        Entry(make("tiny"), (ModelFile("model.bin", 100, None),)),
        Entry(make("base"), (ModelFile("model.bin", 200, None),)),
    )
    runner = ModelTaskRunner(catalog, store, FakeExternal())
    yield client(runner)
    store.gate.set()
    runner.stop()


def install(api: httpx.Client, model_id: str, **body: Any) -> httpx.Response:
    payload: dict[str, Any] = {"method": "download", "confirm": True} | body
    return api.post(f"/api/models/{model_id}/install", json=payload)


def test_install_returns_202_task_view_without_paths(
    api: httpx.Client, store: FakeStore
) -> None:
    response = install(api, "tiny")

    assert response.status_code == 202
    body = response.json()
    assert set(body) == VIEW_KEYS
    assert (body["model_id"], body["method"], body["origin"]) == (
        "tiny",
        "download",
        None,
    )
    assert body["state"] in {"queued", "running"} and body["total_bytes"] == 100
    assert "/" not in response.text  # no paths or URLs
    assert store.started.wait(5)
    wait_for(
        lambda: api.get(f"/api/model-tasks/{body['id']}").json()["done_bytes"] == 30
    )
    store.gate.set()
    wait_for(
        lambda: api.get(f"/api/model-tasks/{body['id']}").json()["state"] == "completed"
    )
    listing = api.get("/api/model-tasks")
    assert listing.status_code == 200
    assert [t["id"] for t in listing.json()["tasks"]] == [body["id"]]


def test_install_requires_explicit_confirmation(api: httpx.Client) -> None:
    for body in ({"method": "download"}, {"method": "download", "confirm": False}):
        response = api.post("/api/models/tiny/install", json=body)
        assert response.status_code == 400
        assert code_of(response) == "model_install_unconfirmed"
    assert api.get("/api/model-tasks").json() == {"tasks": []}


def test_install_error_statuses(api: httpx.Client, store: FakeStore) -> None:
    unknown = install(api, "nope")
    assert (unknown.status_code, code_of(unknown)) == (404, "model_unknown")

    store.installed.add("tiny")
    installed = install(api, "tiny")
    assert (installed.status_code, code_of(installed)) == (
        409,
        "model_already_installed",
    )

    # the installed check comes before the import-candidate check
    assert install(api, "tiny", method="import", origin="buzz").status_code == 409

    imported = install(api, "base", method="import", origin="buzz")
    assert imported.status_code == 202 and imported.json()["origin"] == "buzz"


def test_import_without_candidate_is_404(api: httpx.Client) -> None:
    response = install(api, "tiny", method="import", origin="buzz")
    assert (response.status_code, code_of(response)) == (
        404,
        "external_model_not_found",
    )


def test_duplicate_install_returns_the_same_task(api: httpx.Client) -> None:
    first = install(api, "tiny").json()
    again = install(api, "tiny")
    assert again.status_code == 202 and again.json()["id"] == first["id"]
    assert len(api.get("/api/model-tasks").json()["tasks"]) == 1


def test_get_unknown_task_is_404(api: httpx.Client) -> None:
    response = api.get("/api/model-tasks/missing")
    assert (response.status_code, code_of(response)) == (404, "model_task_not_found")
    assert api.post("/api/model-tasks/missing/cancel").status_code == 404


def test_cancel_running_then_terminal_conflict(
    api: httpx.Client, store: FakeStore
) -> None:
    task = install(api, "tiny").json()
    assert store.started.wait(5)

    response = api.post(f"/api/model-tasks/{task['id']}/cancel")
    assert response.status_code == 202 and set(response.json()) == VIEW_KEYS
    wait_for(
        lambda: api.get(f"/api/model-tasks/{task['id']}").json()["state"] == "cancelled"
    )

    again = api.post(f"/api/model-tasks/{task['id']}/cancel")
    assert (again.status_code, code_of(again)) == (409, "model_task_terminal")


def test_invalid_method_is_rejected(api: httpx.Client) -> None:
    response = api.post(
        "/api/models/tiny/install", json={"method": "torrent", "confirm": True}
    )
    assert response.status_code == 422


# --- real store + local HTTP server ----------------------------------------


@pytest.fixture
def origin() -> Iterator[str]:
    prefix = f"/example/real/resolve/{REVISION}/"
    routes = {prefix + "model.bin": BIN, prefix + "config.json": CFG}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def do_GET(self) -> None:
            body = routes.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(
        target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class LocalOriginStore:
    """Real store, but ``download`` targets the local test server."""

    def __init__(self, store: FileSystemModelStore, base_url: str) -> None:
        self._store, self._base_url = store, base_url

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return self._store.is_installed(descriptor)

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        return self._store.download(
            descriptor,
            files,
            base_url=self._base_url,
            progress=progress,
            cancelled=cancelled,
        )


class NoExternal:
    def find_candidates(self) -> tuple[ExternalModelCandidate, ...]:
        return ()


def test_real_store_downloads_from_local_server_through_http(
    tmp_path: Path, origin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_storage, "_BLOCK_BYTES", 1024)
    real = make("real")
    files = (
        ModelFile("model.bin", len(BIN), hashlib.sha256(BIN).hexdigest()),
        ModelFile("config.json", len(CFG), None),
    )
    catalog = Catalog(Entry(real, files))
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache", clock=lambda: NOW
    )
    runner = ModelTaskRunner(
        catalog,
        LocalOriginStore(store, origin),
        ImportExternalModel(NoExternal(), store, catalog.entries()),
    )
    api = client(runner)
    try:
        response = install(api, "real")
        assert response.status_code == 202
        task_id = response.json()["id"]

        wait_for(
            lambda: (
                api.get(f"/api/model-tasks/{task_id}").json()["state"] == "completed"
            )
        )
        done = api.get(f"/api/model-tasks/{task_id}").json()
        total = len(BIN) + len(CFG)
        assert (done["done_bytes"], done["total_bytes"], done["error_code"]) == (
            total,
            total,
            None,
        )
        assert store.is_installed(real)
        assert (store.resolve_path(real) / "model.bin").read_bytes() == BIN
        assert str(tmp_path) not in api.get("/api/model-tasks").text

        again = install(api, "real")
        assert (again.status_code, code_of(again)) == (409, "model_already_installed")
        missing = install(api, "real", method="import", origin="buzz")
        assert missing.status_code == 409
    finally:
        runner.stop()


def test_real_store_failure_surfaces_a_stable_code(tmp_path: Path, origin: str) -> None:
    real = make("real")
    wrong = (
        ModelFile("model.bin", len(BIN), "0" * 64),
        ModelFile("config.json", len(CFG), None),
    )
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    runner = ModelTaskRunner(
        Catalog(Entry(real, wrong)),
        LocalOriginStore(store, origin),
        ImportExternalModel(NoExternal(), store, ()),
    )
    api = client(runner)
    try:
        task_id = install(api, "real").json()["id"]
        wait_for(
            lambda: api.get(f"/api/model-tasks/{task_id}").json()["state"] == "failed"
        )
        assert (
            api.get(f"/api/model-tasks/{task_id}").json()["error_code"]
            == "model_installation_checksum_mismatch"
        )
        assert not store.is_installed(real)
    finally:
        runner.stop()
