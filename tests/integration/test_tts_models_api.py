"""Speech synthesis models through the Model Manager API (V4-03).

The real ``ManagedModelCatalog`` and ``RoutingModelStore`` over a local HTTP
server and a tar.bz2 built here: listing, install task, delete.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import time
from collections.abc import Callable, Iterator, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.application.import_external_model import ImportExternalModel
from voz.application.model_manager import ListModels, RemoveModel
from voz.application.model_tasks import ModelTaskRunner
from voz.application.ports.external_models import ExternalModelCandidate
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.domain.entities.voice import Voice
from voz.infrastructure.diarization.models import DiarizationModelStore
from voz.infrastructure.model_registry import ManagedModelCatalog, RoutingModelStore
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.tts.catalog import TTS_CATALOG, TTS_PROVIDER_ID, TtsModelEntry
from voz.infrastructure.tts.model_store import TtsModelStore
from voz.interfaces.api.model_tasks import create_model_tasks_router
from voz.interfaces.api.models import create_models_router

_ROOT = "vits-test"
_MEMBERS = {
    f"{_ROOT}/test.onnx": b"onnx" * 300,
    f"{_ROOT}/tokens.txt": b"a 1\n",
    f"{_ROOT}/espeak-ng-data/phontab": b"p" * 20,
}
KEY = f"{TTS_PROVIDER_ID}:test-voice"


def _archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for name, data in _MEMBERS.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


ARCHIVE = _archive()


@pytest.fixture
def origin() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def do_GET(self) -> None:
            if self.path != "/test.tar.bz2":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(ARCHIVE)))
            self.end_headers()
            self.wfile.write(ARCHIVE)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _entry(url: str, sha256: str) -> TtsModelEntry:
    return TtsModelEntry(
        descriptor=ModelDescriptor(
            provider_id=TTS_PROVIDER_ID,
            model_id="test-voice",
            display_name="Test voice",
            capabilities=frozenset({ModelCapability.SYNTHESIS, ModelCapability.CPU}),
        ),
        family="vits",
        archive_name="test.tar.bz2",
        url=url,
        size_bytes=len(ARCHIVE),
        sha256=sha256,
        root=_ROOT,
        files=(("model", "test.onnx"), ("tokens", "tokens.txt")),
        directories=(("data_dir", "espeak-ng-data"),),
        languages=("es",),
        voices=(Voice("0", "Test", ("es",)),),
        sample_rate=22_050,
        license="MIT; espeak-ng-data GPL-3.0",
        ram_bytes=1,
    )


class _NoJobs:
    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        return ()


class _NoSelections:
    def get(self, job_id: UUID) -> JobSelection | None:
        return None


class _NoExternal:
    def find_candidates(self) -> tuple[ExternalModelCandidate, ...]:
        return ()


def _api(
    tmp_path: Path, entries: Sequence[TtsModelEntry]
) -> tuple[httpx.Client, ModelTaskRunner]:
    catalog = ManagedModelCatalog(
        whisper_cpp_available=lambda: False,
        diarization_runtime_available=lambda: True,
        tts_runtime_available=lambda: True,
        tts_models=entries,
    )
    files = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    store = RoutingModelStore(
        files,
        DiarizationModelStore(data_root=tmp_path / "data"),
        TtsModelStore(data_root=tmp_path / "data", catalog=entries),
    )
    runner = ModelTaskRunner(
        catalog, store, ImportExternalModel(_NoExternal(), files, ())
    )
    app = FastAPI()
    app.include_router(
        create_models_router(
            ListModels(catalog, store),
            RemoveModel(catalog, store, _NoJobs(), _NoSelections()),
        )
    )
    app.include_router(create_model_tasks_router(runner))
    return cast(httpx.Client, TestClient(app)), runner  # pyright: ignore[reportUnknownArgumentType]


def _models(api: httpx.Client) -> dict[str, dict[str, Any]]:
    body = api.get("/api/models").json()
    return {item["key"]: item for item in body["models"]}


def _wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def test_the_pinned_catalog_lists_every_tts_model_as_synthesis(tmp_path: Path) -> None:
    api, runner = _api(tmp_path, TTS_CATALOG)
    try:
        listed = {
            key: model
            for key, model in _models(api).items()
            if model["provider_id"] == TTS_PROVIDER_ID
        }

        assert set(listed) == {
            "sherpa-onnx-tts:piper-es_MX-ald-medium",
            "sherpa-onnx-tts:piper-es_MX-claude-high-int8",
            "sherpa-onnx-tts:piper-es_ES-davefx-medium",
            "sherpa-onnx-tts:piper-en_US-lessac-medium",
            "sherpa-onnx-tts:kitten-nano-en-v0_8-int8",
            "sherpa-onnx-tts:kitten-mini-en-v0_8",
            "sherpa-onnx-tts:kokoro-int8-multi-lang-v1_0",
        }
        for model in listed.values():
            assert model["capabilities"] == ["cpu", "synthesis"]
            assert (model["kind"], model["installed"]) == ("tts", False)
            assert model["runtime_available"] is True and model["profile"] is None
            assert model["source"] is None and model["revision"] is None
            assert model["license"] and "GPL-3.0" in model["license"]
        kokoro = listed["sherpa-onnx-tts:kokoro-int8-multi-lang-v1_0"]
        assert kokoro["size_bytes"] == 132_303_094 and kokoro["multilingual"] is True
        assert "slow" in kokoro["display_name"]
        assert str(tmp_path) not in api.get("/api/models").text
    finally:
        runner.stop()


def test_install_task_lists_and_deletes_a_tts_model(
    tmp_path: Path, origin: str
) -> None:
    entry = _entry(f"{origin}/test.tar.bz2", hashlib.sha256(ARCHIVE).hexdigest())
    api, runner = _api(tmp_path, (entry,))
    try:
        assert _models(api)[KEY]["installed"] is False

        task = api.post(
            f"/api/models/{KEY}/install", json={"method": "download", "confirm": True}
        )
        assert task.status_code == 202 and task.json()["key"] == KEY
        _wait_for(
            lambda: (
                api.get(f"/api/model-tasks/{task.json()['id']}").json()["state"]
                == "completed"
            )
        )
        done = api.get(f"/api/model-tasks/{task.json()['id']}").json()
        assert (done["done_bytes"], done["total_bytes"]) == (len(ARCHIVE), len(ARCHIVE))

        model = _models(api)[KEY]
        assert model["installed"] is True and (model["disk_bytes"] or 0) > 1000
        assert model["reclaimable_bytes"] == model["disk_bytes"]
        assert str(tmp_path) not in api.get("/api/models").text
        again = api.post(
            f"/api/models/{KEY}/install", json={"method": "download", "confirm": True}
        )
        assert again.status_code == 409

        deleted = api.delete(f"/api/models/{KEY}", params={"confirm": KEY})
        assert deleted.status_code == 200
        assert deleted.json()["freed_bytes"] == model["disk_bytes"]
        assert _models(api)[KEY]["installed"] is False
        assert not (tmp_path / "data/models/tts/test-voice").exists()
    finally:
        runner.stop()


def test_install_with_a_wrong_digest_fails_with_a_stable_code(
    tmp_path: Path, origin: str
) -> None:
    api, runner = _api(tmp_path, (_entry(f"{origin}/test.tar.bz2", "0" * 64),))
    try:
        task_id = api.post(
            f"/api/models/{KEY}/install", json={"method": "download", "confirm": True}
        ).json()["id"]
        _wait_for(
            lambda: api.get(f"/api/model-tasks/{task_id}").json()["state"] == "failed"
        )

        assert (
            api.get(f"/api/model-tasks/{task_id}").json()["error_code"]
            == "model_installation_checksum_mismatch"
        )
        assert _models(api)[KEY]["installed"] is False
        assert not (tmp_path / "data/models/tts/test-voice").exists()
    finally:
        runner.stop()
