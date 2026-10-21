"""Custom imports with synthetic weights, local HTTP and isolated fake loaders."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import tarfile
import threading
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from subprocess import Popen as ValidationChild
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.import_custom_model import ImportCustomModel
from voz.application.model_manager import ListModels, RemoveModel
from voz.application.model_tasks import ModelTaskRunner
from voz.application.ports.custom_models import (
    CustomModelError,
    CustomModelRequest,
    CustomValidation,
)
from voz.application.ports.model_installation import CancelCheck, ModelInstallationError
from voz.application.ports.transcription_options import RuntimeAvailability
from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.processing_profile import ComputePrecision
from voz.domain.entities.voice import Voice
from voz.infrastructure import custom_model_worker, custom_models
from voz.infrastructure.custom_model_worker import SubprocessModelValidator
from voz.infrastructure.custom_models import CustomModelCatalog, CustomModelStore
from voz.infrastructure.diarization.models import DiarizationModelStore
from voz.infrastructure.model_registry import (
    ENGINE_CAPABILITIES,
    ManagedModelCatalog,
    RoutingModelStore,
)
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.tts.model_store import TtsModelStore
from voz.interfaces.api.model_tasks import create_model_tasks_router
from voz.interfaces.api.models import create_models_router


class Validator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.roles: list[dict[str, str]] = []
        self.error: Exception | None = None

    def validate(
        self,
        directory: Path,
        engine: str,
        family: str,
        *,
        file_roles: dict[str, str],
        cancelled: CancelCheck,
    ) -> CustomValidation:
        self.roles.append(dict(file_roles))
        assert directory.is_dir() and not cancelled()
        self.calls.append((engine, family))
        if self.error:
            raise self.error
        return (
            CustomValidation((Voice("0", "Test voice", ("es",)),), ("es",))
            if engine == "sherpa-onnx-tts"
            else CustomValidation()
        )


def folder(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, data in {
        "model.bin": b"ctranslate2",
        "config.json": b"{}",
        "tokenizer.json": b"{}",
    }.items():
        (root / name).write_bytes(data)
    (root / "untrusted.py").write_text('raise RuntimeError("must never execute")')
    return root


def request(source: Path | str, **changes: object) -> CustomModelRequest:
    values: dict[str, object] = dict(
        source_type="folder",
        source=str(source),
        engine="faster-whisper",
        family="ctranslate2",
        display_name="Custom voice model",
    )
    values.update(changes)
    return CustomModelRequest(**values)  # type: ignore[arg-type]


def stores(
    tmp_path: Path,
) -> tuple[FileSystemModelStore, CustomModelStore, Validator, ImportCustomModel]:
    files = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    store = CustomModelStore(
        files, cache_root=tmp_path / "cache", runtime_available=lambda _: True
    )
    validator = Validator()
    return files, store, validator, ImportCustomModel(store, validator)


def archive(member: str = "voice/model.onnx", *, link: bool = False) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:bz2") as bundle:
        for name, data in [
            (member, b"fake onnx"),
            ("voice/tokens.txt", b"a 0"),
            ("voice/script.py", b"never execute"),
        ]:
            info = tarfile.TarInfo(name)
            if link and name == member:
                info.type, info.linkname = tarfile.SYMTYPE, "../outside"
                bundle.addfile(info)
            else:
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
    return raw.getvalue()


@contextmanager
def server(payloads: dict[str, bytes]) -> Generator[tuple[str, list[tuple[str, str]]]]:
    calls: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_HEAD(self) -> None:
            self.reply(False)

        def do_GET(self) -> None:
            self.reply(True)

        def reply(self, body: bool) -> None:
            calls.append((self.command, self.path))
            data = payloads.get(self.path)
            self.send_response(200 if data is not None else 404)
            self.send_header("Content-Length", str(len(data or b"")))
            self.end_headers()
            if body and data is not None:
                self.wfile.write(data)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def test_folder_preview_is_path_free_unpinned_and_unconfirmed_copies_nothing(
    tmp_path: Path,
) -> None:
    files, store, validator, importer = stores(tmp_path)
    source = folder(tmp_path / "private-folder")
    preview = importer.prepare(request(source))
    assert preview.descriptor.source is None and preview.descriptor.revision is None
    assert preview.size_bytes == 15 and preview.file_count == 3
    assert str(source) not in repr(preview)
    assert store.managed_entries() == ()
    with pytest.raises(CustomModelError) as raised:
        importer.execute(preview.id, confirm=False)
    assert raised.value.code == "model_install_unconfirmed"
    assert validator.calls == [] and files.registered_descriptors() == ()


def test_folder_pins_all_hashes_keeps_original_independent_and_lists_live(
    tmp_path: Path,
) -> None:
    files, store, validator, importer = stores(tmp_path)
    source = folder(tmp_path / "original")
    preview = importer.prepare(request(source, license="MIT (declared)"))
    progress: list[tuple[int, int]] = []
    descriptor = importer.execute(
        preview.id,
        confirm=True,
        progress=lambda done, total: progress.append((done, total)),
    )
    assert descriptor.source and descriptor.source.startswith("sha256:")
    assert descriptor.revision and len(descriptor.revision) == 40
    assert descriptor.profile is not None
    installed = files.resolve_path(descriptor)
    record = json.loads((installed / ".voz-custom.json").read_text())
    assert record["license"] == "User-declared: MIT (declared)"
    for entry in record["files"]:
        assert (
            entry["sha256"]
            == hashlib.sha256((installed / entry["name"]).read_bytes()).hexdigest()
        )
    assert "untrusted.py" not in {entry["name"] for entry in record["files"]}
    assert str(source) not in (installed / ".voz-model.json").read_text()
    assert str(source) not in (installed / ".voz-custom.json").read_text()
    (source / "model.bin").write_bytes(b"changed")
    assert (installed / "model.bin").read_bytes() == b"ctranslate2"
    assert store.managed_entries()[0].descriptor == descriptor
    assert store.list_models(ModelCapability.TRANSCRIPTION)[0].files_available
    assert validator.calls == [("faster-whisper", "ctranslate2")]
    assert progress[-1] == (15, 15)
    assert store.remove(descriptor) > 0
    assert store.managed_entries() == () and (source / "model.bin").exists()


def test_url_preview_only_reads_size_then_tts_install_is_live_and_removable(
    tmp_path: Path,
) -> None:
    files, store, _, importer = stores(tmp_path)
    with server({"/voice.tar.bz2": archive()}) as (base, calls):
        preview = importer.prepare(
            request(
                base + "/voice.tar.bz2",
                source_type="url",
                engine="sherpa-onnx-tts",
                family="vits",
            )
        )
        assert calls == [("HEAD", "/voice.tar.bz2")]
        assert preview.descriptor.provenance is None
        assert preview.size_bytes == len(archive())
        descriptor = importer.execute(preview.id, confirm=True)
        assert calls == [("HEAD", "/voice.tar.bz2"), ("GET", "/voice.tar.bz2")]
    tts = TtsModelStore(data_root=tmp_path / "data", custom_manifest=store.manifest)
    assert descriptor.supports(ModelCapability.SYNTHESIS)
    manifest = tts.manifest(descriptor.model_id)
    assert manifest is not None and manifest.voices[0].name == "Test voice"
    assert set(manifest.files) == {"model", "tokens"}
    assert not (files.resolve_path(descriptor) / "script.py").exists()
    routing = RoutingModelStore(
        files, DiarizationModelStore(data_root=tmp_path / "data"), tts, custom=store
    )
    assert routing.is_installed(descriptor)
    assert routing.remove(descriptor) > 0
    assert tts.manifest(descriptor.model_id) is None
    assert CustomModelCatalog(store, ModelCapability.SYNTHESIS).list_models() == ()


def test_hf_metadata_pins_revision_and_only_allowlisted_files_download(
    tmp_path: Path,
) -> None:
    files, _, validator, _ = stores(tmp_path)
    commit = "a" * 40
    contents = {
        "model.bin": b"ctranslate2",
        "config.json": b"{}",
        "tokenizer.json": b"{}",
    }
    siblings = [
        {
            "rfilename": name,
            "size": len(data),
            "lfs": {"sha256": hashlib.sha256(data).hexdigest()},
        }
        for name, data in contents.items()
    ]
    siblings.extend(
        [
            {"rfilename": "model.py", "size": 999},
            {"rfilename": "weights.pkl", "size": 999},
        ]
    )
    metadata = "/api/models/org/model/revision/main?blobs=true"
    payloads = {
        metadata: json.dumps({"sha": commit, "siblings": siblings}).encode(),
        **{
            f"/org/model/resolve/{commit}/{name}": data
            for name, data in contents.items()
        },
    }
    with server(payloads) as (base, calls):
        store = CustomModelStore(
            files,
            cache_root=tmp_path / "cache",
            hf_base_url=base,
            runtime_available=lambda _: True,
        )
        importer = ImportCustomModel(store, validator)
        preview = importer.prepare(
            request("https://huggingface.co/org/model", source_type="huggingface")
        )
        assert preview.descriptor.provenance == ("org/model", commit)
        assert calls == [("GET", metadata)]
        descriptor = importer.execute(preview.id, confirm=True)
        assert descriptor.revision == commit
        assert len(calls) == 4 and all(
            not path.endswith((".py", ".pkl")) for _, path in calls
        )
    assert files.is_installed(descriptor)


@pytest.mark.parametrize("lfs", [[], "private-metadata-secret"])
def test_hf_invalid_lfs_is_a_safe_preview_error(
    tmp_path: Path,
    lfs: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    files, _, validator, _ = stores(tmp_path)
    metadata = "/api/models/org/model/revision/main?blobs=true"
    document = {
        "sha": "a" * 40,
        "siblings": [
            {"rfilename": "model.bin", "size": 15, "lfs": lfs},
        ],
    }
    with server({metadata: json.dumps(document).encode()}) as (base, calls):
        store = CustomModelStore(
            files,
            cache_root=tmp_path / "cache",
            hf_base_url=base,
            runtime_available=lambda _: True,
        )
        importer = ImportCustomModel(store, validator)
        app = FastAPI()
        app.include_router(create_models_router(Mock(), Mock(), custom=importer))
        response = cast(httpx.Client, TestClient(app)).post(
            "/api/models/custom/preview",
            json={
                "source_type": "huggingface",
                "source": "org/model",
                "engine": "faster-whisper",
                "family": "ctranslate2",
                "display_name": "Own model",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "custom_model_invalid"
        assert calls == [("GET", metadata)]
        assert "private-metadata-secret" not in response.text + caplog.text
        assert str(tmp_path) not in response.text
        assert validator.calls == [] and store.managed_entries() == ()


@pytest.mark.parametrize(
    ("member", "link"),
    [("../escape.onnx", False), ("voice/model.onnx", True), ("/escape.onnx", False)],
)
def test_untrusted_archives_never_escape_or_publish(
    tmp_path: Path, member: str, link: bool
) -> None:
    _, store, validator, importer = stores(tmp_path)
    with server({"/bad.tar.bz2": archive(member, link=link)}) as (base, _):
        preview = importer.prepare(
            request(
                base + "/bad.tar.bz2",
                source_type="url",
                engine="sherpa-onnx-tts",
                family="vits",
            )
        )
        with pytest.raises(Exception) as raised:
            importer.execute(preview.id, confirm=True)
        assert "invalid" in str(getattr(raised.value, "code", ""))
    assert store.managed_entries() == () and validator.calls == []
    assert not (tmp_path / "escape.onnx").exists()


def test_folder_symlinks_are_rejected_and_scan_stops_at_its_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, importer = stores(tmp_path)
    source = folder(tmp_path / "original")
    (source / "link").symlink_to(source / "model.bin")
    with pytest.raises(CustomModelError):
        importer.prepare(request(source))
    scanned: list[int] = []

    def entries(_: Path, pattern: str) -> Generator[Path]:
        del pattern
        for count in range(100):
            scanned.append(count)
            yield source / "model.bin"

    monkeypatch.setattr(custom_models, "_MAX_FILES", 3)
    monkeypatch.setattr(Path, "rglob", entries)
    with pytest.raises(CustomModelError):
        importer.prepare(request(source))
    assert len(scanned) == 4


def test_failed_validation_and_cancelled_validation_wait_never_register(
    tmp_path: Path,
) -> None:
    _, store, validator, importer = stores(tmp_path)
    source = folder(tmp_path / "original")
    preview = importer.prepare(request(source))
    validator.error = CustomModelError(
        "custom_model_validation_failed", "Cannot load weights."
    )
    with pytest.raises(CustomModelError) as raised:
        importer.execute(preview.id, confirm=True)
    assert raised.value.code == "custom_model_validation_failed"
    assert store.managed_entries() == ()
    waiting = threading.Event()
    cancelled = threading.Event()

    @contextmanager
    def guard(check: CancelCheck) -> Generator[None]:
        waiting.set()
        while not check():
            cancelled.wait(0.01)
        raise CustomModelError("model_installation_cancelled", "Cancelled.")
        yield  # pragma: no cover

    validator.calls.clear()
    importer = ImportCustomModel(store, validator, validation_context=guard)
    preview = importer.prepare(request(source))
    errors: list[str] = []

    def execute() -> None:
        try:
            importer.execute(preview.id, confirm=True, cancelled=cancelled.is_set)
        except CustomModelError as error:
            errors.append(error.code)

    thread = threading.Thread(target=execute)
    thread.start()
    assert waiting.wait(3)
    cancelled.set()
    thread.join(3)
    assert not thread.is_alive() and errors == ["model_installation_cancelled"]
    assert validator.calls == [] and store.managed_entries() == ()


def test_whisper_cpp_custom_descriptor_is_startable_with_the_cpu_profile(
    tmp_path: Path,
) -> None:
    _, store, _, importer = stores(tmp_path)
    source = tmp_path / "ggml"
    source.mkdir()
    (source / "ggml-my-model.bin").write_bytes(b"ggml")
    preview = importer.prepare(request(source, engine="whisper-cpp", family="ggml"))
    descriptor = importer.execute(preview.id, confirm=True)

    class Runtime:
        def probe(self, provider_id: str) -> RuntimeAvailability:
            return RuntimeAvailability(
                True,
                hardware=HardwareCapabilities(frozenset(), frozenset(ComputePrecision)),
                capabilities=ENGINE_CAPABILITIES[provider_id],
            )

    options = GetTranscriptionOptions(
        CustomModelCatalog(store, ModelCapability.TRANSCRIPTION), Runtime()
    ).execute()
    assert options.options[0].can_start
    assert descriptor.profile is not None


def test_api_custom_tasks_are_confirmed_path_free_and_can_be_removed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    files, store, validator, importer = stores(tmp_path)
    source = folder(tmp_path / "private-path")
    catalog = ManagedModelCatalog(
        whisper_cpp_available=lambda: False,
        diarization_runtime_available=lambda: False,
        custom_models=store.managed_entries,
    )
    routing = RoutingModelStore(
        files, DiarizationModelStore(data_root=tmp_path / "data"), custom=store
    )
    external = Mock()
    external.find_candidates.return_value = ()
    jobs = Mock()
    jobs.list_recoverable.return_value = ()
    runner = ModelTaskRunner(catalog, routing, Mock(), custom=importer)
    app = FastAPI()
    app.include_router(
        create_models_router(
            ListModels(catalog, routing, external=external),
            RemoveModel(catalog, routing, jobs, Mock()),
            custom=importer,
        )
    )
    app.include_router(create_model_tasks_router(runner))
    try:
        client = cast(httpx.Client, TestClient(app))
        prepared = client.post(
            "/api/models/custom/preview",
            json={
                "source_type": "folder",
                "source": str(source),
                "engine": "faster-whisper",
                "family": "ctranslate2",
                "display_name": "Own model",
            },
        )
        assert prepared.status_code == 200
        preview_id = prepared.json()["id"]
        refused = client.post(
            "/api/models/custom/install", json={"preview_id": preview_id}
        )
        assert refused.status_code == 400 and validator.calls == []
        queued = client.post(
            "/api/models/custom/install",
            json={"preview_id": preview_id, "confirm": True},
        )
        assert queued.status_code == 202
        task_id = queued.json()["id"]
        task = queued
        for _ in range(300):
            task = client.get("/api/model-tasks/" + task_id)
            if task.json()["state"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.01)
        assert task.json()["state"] == "completed"
        listed = client.get("/api/models")
        entry = next(
            item
            for item in listed.json()["models"]
            if item["model_id"].startswith("custom-")
        )
        assert "transcription" in entry["capabilities"] and entry["installed"]
        key = entry["key"]
        deleted = client.delete("/api/models/" + key, params={"confirm": key})
        assert deleted.status_code == 200 and store.managed_entries() == ()
        for response in (prepared, refused, queued, task, listed, deleted):
            assert str(source) not in response.text
        assert str(source) not in caplog.text
    finally:
        runner.stop()


@pytest.mark.parametrize(
    "changes",
    [
        {"source": {"secret": "private-source-secret"}},
        {"source": "private-source-secret" * 200},
        {"display_name": {"secret": "private-source-secret"}},
        {"source_type": "private-source-secret"},
    ],
)
@pytest.mark.parametrize("route", ["preview", "install"])
def test_api_validation_does_not_reflect_source_or_secret(
    tmp_path: Path,
    changes: dict[str, object],
    caplog: pytest.LogCaptureFixture,
    route: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    _, store, _, importer = stores(tmp_path)
    app = FastAPI()
    app.include_router(create_models_router(Mock(), Mock(), custom=importer))
    app.include_router(
        create_model_tasks_router(
            ModelTaskRunner(Mock(), Mock(), Mock(), custom=importer)
        )
    )
    response = cast(httpx.Client, TestClient(app)).post(
        "/api/models/custom/" + route,
        json={
            "source_type": "folder",
            "source": str(tmp_path / "private-folder"),
            "engine": "faster-whisper",
            "family": "ctranslate2",
            "display_name": "Own",
            **changes,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "custom_model_invalid"
    assert "private-source-secret" not in response.text + caplog.text
    assert str(tmp_path) not in response.text + caplog.text
    assert store.managed_entries() == ()


def test_local_import_checks_disk_before_copy_and_keeps_original(
    tmp_path: Path,
) -> None:
    disk = Mock()
    disk.free_bytes.return_value = 0
    files = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache", disk_space=disk
    )
    store = CustomModelStore(
        files, cache_root=tmp_path / "cache", runtime_available=lambda _: True
    )
    validator = Validator()
    importer = ImportCustomModel(store, validator)
    source = folder(tmp_path / "source")
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    preview = importer.prepare(request(source))
    with pytest.raises(ModelInstallationError) as raised:
        importer.execute(preview.id, confirm=True)
    assert raised.value.code == "disk_space_insufficient"
    assert {path.name: path.read_bytes() for path in source.iterdir()} == before
    assert validator.calls == [] and store.managed_entries() == ()
    assert not (tmp_path / "cache" / "custom-models").exists()


@pytest.mark.parametrize(
    ("engine", "family", "filename"),
    [
        ("faster-whisper", "ctranslate2", "model.bin"),
        ("sherpa-onnx-tts", "vits", "model.onnx"),
    ],
)
def test_single_file_urls_missing_companions_are_rejected_before_network(
    tmp_path: Path,
    engine: str,
    family: str,
    filename: str,
) -> None:
    _, _, validator, importer = stores(tmp_path)
    with server({"/" + filename: b"fake weights"}) as (base, calls):
        with pytest.raises(CustomModelError):
            importer.prepare(
                request(
                    base + "/" + filename,
                    source_type="url",
                    engine=engine,
                    family=family,
                )
            )
        assert calls == [] and validator.calls == []


def test_custom_tasks_deduplicate_and_cancel_running_and_queued(tmp_path: Path) -> None:
    _, store, validator, _ = stores(tmp_path)
    source = folder(tmp_path / "source")
    waiting = threading.Event()

    @contextmanager
    def guard(cancelled: CancelCheck) -> Generator[None]:
        waiting.set()
        while not cancelled():
            time.sleep(0.01)
        raise CustomModelError("model_installation_cancelled", "Cancelled.")
        yield  # pragma: no cover

    importer = ImportCustomModel(store, validator, validation_context=guard)
    first = importer.prepare(request(source))
    second = importer.prepare(request(source))
    runner = ModelTaskRunner(Mock(), Mock(), Mock(), custom=importer)
    try:
        running = runner.enqueue_custom(first.id, confirm=True)
        assert waiting.wait(3)
        assert runner.get(running.id).done_bytes == first.size_bytes
        assert runner.enqueue_custom(first.id, confirm=True).id == running.id
        queued = runner.enqueue_custom(second.id, confirm=True)
        assert runner.cancel(queued.id).state == "cancelled"
        runner.cancel(running.id)
        for _ in range(300):
            if runner.get(running.id).state == "cancelled":
                break
            time.sleep(0.01)
        assert runner.get(running.id).state == "cancelled"
        assert runner.get(running.id).error_code is None
        assert validator.calls == [] and store.managed_entries() == ()
    finally:
        runner.stop()


def test_unexpected_validator_error_never_enters_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _, store, validator, importer = stores(tmp_path)
    validator.error = RuntimeError("private-source-secret")
    preview = importer.prepare(request(folder(tmp_path / "source")))
    runner = ModelTaskRunner(Mock(), Mock(), Mock(), custom=importer)
    try:
        task = runner.enqueue_custom(preview.id, confirm=True)
        for _ in range(300):
            if runner.get(task.id).state == "failed":
                break
            time.sleep(0.01)
        assert runner.get(task.id).error_code == "model_task_failed"
        assert "private-source-secret" not in caplog.text
        assert store.managed_entries() == ()
    finally:
        runner.stop()


@pytest.mark.parametrize(("field", "value"), [("license", None), ("file_roles", [])])
@pytest.mark.parametrize(
    ("engine", "family"),
    [
        ("faster-whisper", "ctranslate2"),
        ("sherpa-onnx-tts", "vits"),
    ],
)
def test_corrupt_custom_record_is_skipped_in_live_catalog(
    tmp_path: Path,
    field: str,
    value: object,
    engine: str,
    family: str,
) -> None:
    files, store, _, importer = stores(tmp_path)
    source = folder(tmp_path / "source")
    if engine == "sherpa-onnx-tts":
        (source / "model.onnx").write_bytes(b"synthetic onnx")
        (source / "tokens.txt").write_bytes(b"a 0")
    preview = importer.prepare(request(source, engine=engine, family=family))
    descriptor = importer.execute(preview.id, confirm=True)
    manifest = files.resolve_path(descriptor) / ".voz-custom.json"
    metadata = json.loads(manifest.read_text())
    if value is None:
        del metadata[field]
    else:
        metadata[field] = value
    manifest.write_text(json.dumps(metadata))
    assert store.managed_entries() == ()
    assert store.list_models(ModelCapability.TRANSCRIPTION) == ()
    assert store.list_models(ModelCapability.SYNTHESIS) == ()
    assert store.manifest(descriptor.model_id) is None
    assert (
        GetTranscriptionOptions(
            CustomModelCatalog(store, ModelCapability.TRANSCRIPTION),
            Mock(),
        )
        .execute()
        .options
        == ()
    )


def test_fake_validation_child_success_timeout_cancel_and_crash(tmp_path: Path) -> None:
    okay = 'import json; print(json.dumps({"voices":[],"languages":[]}))'
    validator = SubprocessModelValidator(argv=[sys.executable, "-c", okay])
    assert (
        validator.validate(
            tmp_path,
            "faster-whisper",
            "ctranslate2",
            file_roles={},
            cancelled=lambda: False,
        )
        == CustomValidation()
    )
    for code, script, timeout, check in [
        (
            "custom_model_validation_failed",
            'raise RuntimeError("private-secret")',
            1.0,
            lambda: False,
        ),
        (
            "custom_model_validation_timeout",
            "import time; time.sleep(10)",
            0.05,
            lambda: False,
        ),
        (
            "model_installation_cancelled",
            "import time; time.sleep(10)",
            1.0,
            lambda: True,
        ),
    ]:
        validator = SubprocessModelValidator(
            argv=[sys.executable, "-c", script], timeout_seconds=timeout
        )
        with pytest.raises(CustomModelError) as raised:
            validator.validate(
                tmp_path,
                "faster-whisper",
                "ctranslate2",
                file_roles={},
                cancelled=check,
            )
        assert raised.value.code == code and "private-secret" not in str(raised.value)


def test_validation_cancels_a_running_fake_child_without_leaving_it_alive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = custom_model_worker.subprocess.Popen
    children: list[ValidationChild[bytes]] = []

    def start(argv: Sequence[str], **kwargs: Any) -> ValidationChild[bytes]:
        child = cast(ValidationChild[bytes], original(argv, **kwargs))
        children.append(child)
        return child

    monkeypatch.setattr(custom_model_worker.subprocess, "Popen", start)
    deadline = time.monotonic() + 0.15
    validator = SubprocessModelValidator(
        argv=[sys.executable, "-c", "import time; time.sleep(10)"]
    )
    with pytest.raises(CustomModelError) as raised:
        validator.validate(
            tmp_path,
            "faster-whisper",
            "ctranslate2",
            file_roles={},
            cancelled=lambda: time.monotonic() >= deadline,
        )
    assert raised.value.code == "model_installation_cancelled"
    assert len(children) == 1
    assert children[0].poll() is not None


def test_real_faster_whisper_loader_contract_never_uses_network_or_remote_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = Mock()

    def import_loader(name: str) -> SimpleNamespace:
        assert name == "faster_whisper"
        return SimpleNamespace(WhisperModel=loader)

    monkeypatch.setattr(
        custom_model_worker.importlib,
        "import_module",
        import_loader,
    )
    result = custom_model_worker._load(tmp_path, "faster-whisper", "ctranslate2", {})  # pyright: ignore[reportPrivateUsage]
    assert result == CustomValidation()
    loader.assert_called_once_with(
        str(tmp_path),
        device="cpu",
        compute_type="int8",
        local_files_only=True,
        cpu_threads=1,
        num_workers=1,
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="process-group cleanup (os.killpg) is POSIX-only; Windows uses child.kill()",
)
def test_exited_child_process_group_cleanup_tolerates_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Child:
        pid = 999999
        returncode = 0

        def poll(self) -> int:
            return 0

    def popen(*args: object, **kwargs: object) -> Child:
        del args
        output = cast(io.BufferedIOBase, kwargs["stdout"])
        output.write(b'{"voices":[],"languages":[]}')
        return Child()

    def gone(pid: int, sig: int) -> None:
        del sig
        assert pid == Child.pid
        raise ProcessLookupError

    monkeypatch.setattr(custom_model_worker.subprocess, "Popen", popen)
    monkeypatch.setattr(custom_model_worker.os, "killpg", gone)
    assert (
        SubprocessModelValidator().validate(
            tmp_path,
            "faster-whisper",
            "ctranslate2",
            file_roles={},
            cancelled=lambda: False,
        )
        == CustomValidation()
    )


def test_windows_whisper_cpp_validation_is_explicitly_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(custom_model_worker, "os", SimpleNamespace(name="nt"))
    with pytest.raises(CustomModelError) as raised:
        SubprocessModelValidator().validate(
            tmp_path, "whisper-cpp", "ggml", file_roles={}, cancelled=lambda: False
        )
    assert raised.value.code == "custom_model_runtime_unavailable"


def whisper_folder(root: Path) -> Path:
    root.mkdir()
    for name in ("tiny-encoder.int8.onnx", "tiny-decoder.int8.onnx", "tokens.txt"):
        (root / name).write_bytes(b"synthetic")
    (root / "untrusted.py").write_bytes(b"never execute")
    (root / "voices.bin").write_bytes(b"not ASR")
    return root


def test_sherpa_whisper_custom_import_has_native_cpu_profile(tmp_path: Path) -> None:
    files, store, validator, importer = stores(tmp_path)
    source = whisper_folder(tmp_path / "source")
    preview = importer.prepare(
        request(source, engine="sherpa-onnx-asr", family="whisper")
    )
    assert preview.file_count == 3
    assert preview.descriptor.profile is not None
    assert preview.descriptor.profile.cpu_precision == ComputePrecision.NATIVE
    assert preview.descriptor.supports(ModelCapability.TRANSCRIPTION)
    descriptor = importer.execute(preview.id, confirm=True)
    installed = files.resolve_path(descriptor)
    assert set(custom_models.model_files(installed, "whisper", {})) == {
        "encoder",
        "decoder",
        "tokens",
    }
    assert not (installed / "untrusted.py").exists()
    assert not (installed / "voices.bin").exists()
    assert validator.calls == [("sherpa-onnx-asr", "whisper")]
    assert store.list_models(ModelCapability.TRANSCRIPTION)[0].descriptor == descriptor

    class Runtime:
        def probe(self, provider_id: str) -> RuntimeAvailability:
            assert provider_id == "sherpa-onnx-asr"
            return RuntimeAvailability(
                True,
                hardware=HardwareCapabilities(
                    frozenset(), frozenset({ComputePrecision.NATIVE})
                ),
                capabilities=descriptor.capabilities,
            )

    options = GetTranscriptionOptions(
        CustomModelCatalog(store, ModelCapability.TRANSCRIPTION), Runtime()
    ).execute()
    assert options.options[0].can_start
    assert store.remove(descriptor) > 0
    assert source.exists()


def test_sherpa_whisper_validator_loads_only_installed_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = whisper_folder(tmp_path / "source")
    factory = Mock()

    def installed(name: str) -> SimpleNamespace:
        assert name == "sherpa_onnx"
        return SimpleNamespace(OfflineRecognizer=SimpleNamespace(from_whisper=factory))

    monkeypatch.setattr(custom_model_worker.importlib, "import_module", installed)
    assert (
        custom_model_worker._load(source, "sherpa-onnx-asr", "whisper", {})  # pyright: ignore[reportPrivateUsage]
        == CustomValidation()
    )
    factory.assert_called_once_with(
        encoder=str(source / "tiny-encoder.int8.onnx"),
        decoder=str(source / "tiny-decoder.int8.onnx"),
        tokens=str(source / "tokens.txt"),
        language="",
        task="transcribe",
        provider="cpu",
        num_threads=1,
        debug=False,
        enable_token_timestamps=False,
        enable_segment_timestamps=False,
    )


@pytest.mark.parametrize(
    "name,allowed",
    [
        ("encoder.onnx", True),
        ("nested/decoder.onnx", True),
        ("tokens.txt", True),
        ("voices.bin", False),
        ("run.py", False),
        ("model.onnx.exe", False),
        ("../encoder.onnx", False),
        ("dict/private", False),
    ],
)
def test_sherpa_asr_allowlist(name: str, allowed: bool) -> None:
    assert custom_models.allowed_file("sherpa-onnx-asr", name) is allowed


def test_sherpa_whisper_explicit_roles_are_validated_before_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = whisper_folder(tmp_path / "source")
    factory = Mock()
    monkeypatch.setattr(custom_model_worker, "load_whisper", factory)
    roles = {
        "encoder": "tiny-encoder.int8.onnx",
        "decoder": "tiny-decoder.int8.onnx",
        "tokens": "tokens.txt",
    }
    custom_model_worker._load(source, "sherpa-onnx-asr", "whisper", roles)  # pyright: ignore[reportPrivateUsage]
    assert factory.call_args.args[0] == {
        role: source / name for role, name in roles.items()
    }
    factory.reset_mock()
    for bad in [
        {**roles, "encoder": "../outside.onnx"},
        {**roles, "decoder": roles["encoder"]},
        {**roles, "tokens": "missing.txt"},
        {**roles, "script": "run.py"},
    ]:
        with pytest.raises(CustomModelError):
            custom_model_worker._load(source, "sherpa-onnx-asr", "whisper", bad)  # pyright: ignore[reportPrivateUsage]
    factory.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_sherpa_whisper_validation_child_uses_installed_runtime_factory(
    tmp_path: Path,
    fails: bool,
) -> None:
    pytest.importorskip("sherpa_onnx")
    source = whisper_folder(tmp_path / "source")
    child = """
import sys, os
from pathlib import Path
import sherpa_onnx
from voz.infrastructure.custom_model_worker import main
folder=Path(sys.argv[3])
def factory(**kwargs):
    assert kwargs['provider']=='cpu' and kwargs['num_threads']==1
    assert kwargs['task']=='transcribe' and kwargs['language']==''
    for role in ('encoder','decoder','tokens'):
        assert Path(kwargs[role]).is_file()
    (folder/'.factory-pid').write_text(str(os.getpid()))
    return object()
sherpa_onnx.OfflineRecognizer.from_whisper=staticmethod(factory)
sys.exit(main())
"""
    if fails:
        child = child.replace("return object()", "raise RuntimeError('private-secret')")
    validator = SubprocessModelValidator(
        argv=[sys.executable, "-c", child], timeout_seconds=10
    )
    if fails:
        with pytest.raises(CustomModelError) as error:
            validator.validate(
                source,
                "sherpa-onnx-asr",
                "whisper",
                file_roles={},
                cancelled=lambda: False,
            )
        assert error.value.code == "custom_model_validation_failed"
        assert "private-secret" not in str(error.value)
    else:
        assert (
            validator.validate(
                source,
                "sherpa-onnx-asr",
                "whisper",
                file_roles={},
                cancelled=lambda: False,
            )
            == CustomValidation()
        )
    import os

    assert int((source / ".factory-pid").read_text()) != os.getpid()


@pytest.mark.parametrize("name", ["LICENSE", "MODEL_CARD"])
def test_sherpa_asr_preserves_license_metadata(name: str) -> None:
    assert custom_models.allowed_file("sherpa-onnx-asr", name)
    assert not custom_models.allowed_file("sherpa-onnx-asr", "nested/" + name)


@pytest.mark.parametrize(
    ("repo", "weights", "engine", "family", "roles"),
    [
        (
            "ct2-model",
            {"model.bin", "config.json", "tokenizer.json"},
            "faster-whisper",
            "ctranslate2",
            {},
        ),
        ("ggml-model", {"ggml-tiny.bin"}, "whisper-cpp", "ggml", {}),
        (
            "whisper-onnx",
            {"tiny-encoder.int8.onnx", "tiny-decoder.int8.onnx", "tokens.txt"},
            "sherpa-onnx-asr",
            "whisper",
            {
                "encoder": "tiny-encoder.int8.onnx",
                "decoder": "tiny-decoder.int8.onnx",
                "tokens": "tokens.txt",
            },
        ),
        (
            "sherpa-onnx-nemo-parakeet-tdt",
            {
                "encoder.int8.onnx",
                "decoder.int8.onnx",
                "joiner.int8.onnx",
                "tokens.txt",
            },
            "sherpa-onnx-asr",
            "nemo_transducer",
            {
                "encoder": "encoder.int8.onnx",
                "decoder": "decoder.int8.onnx",
                "joiner": "joiner.int8.onnx",
                "tokens": "tokens.txt",
            },
        ),
        (
            "kitten-model",
            {"model.onnx", "tokens.txt", "voices.bin", "espeak-ng-data/phontab"},
            "sherpa-onnx-tts",
            "kitten",
            {},
        ),
        (
            "kokoro-model",
            {"model.onnx", "tokens.txt", "voices.bin", "espeak-ng-data/phontab"},
            "sherpa-onnx-tts",
            "kokoro",
            {},
        ),
        ("piper-vits", {"model.onnx", "tokens.txt"}, "sherpa-onnx-tts", "vits", {}),
    ],
)
def test_auto_hf_previews_metadata_only_then_validates_and_pins_on_confirmation(
    tmp_path: Path,
    repo: str,
    weights: set[str],
    engine: str,
    family: str,
    roles: dict[str, str],
) -> None:
    files, _, validator, _ = stores(tmp_path)
    revision = "b" * 40
    metadata = f"/api/models/org/{repo}/revision/main?blobs=true"
    prefix = f"/org/{repo}/resolve/{revision}/"
    bodies = {name: b"synthetic weights" for name in weights}
    document = {
        "sha": revision,
        "siblings": [
            {
                "rfilename": name,
                "size": len(body),
                "lfs": {"sha256": hashlib.sha256(body).hexdigest()},
            }
            for name, body in bodies.items()
        ]
        + [{"rfilename": "untrusted.py"}, {"rfilename": "unsafe.pkl"}],
    }
    payloads = {metadata: json.dumps(document).encode()}
    payloads.update({prefix + name: body for name, body in bodies.items()})
    with server(payloads) as (base, calls):
        store = CustomModelStore(
            files,
            cache_root=tmp_path / "cache",
            hf_base_url=base,
            runtime_available=lambda _: True,
        )
        importer = ImportCustomModel(store, validator)
        preview = importer.prepare(
            request(
                "org/" + repo,
                source_type="huggingface",
                engine="auto",
                family="",
                display_name="",
            )
        )
        assert preview.descriptor.provider_id == engine and preview.family == family
        assert preview.descriptor.display_name == repo
        assert preview.descriptor.revision == revision and preview.license == "unknown"
        assert preview.file_count == len(weights)
        assert calls == [("GET", metadata)] and validator.calls == []
        assert not (tmp_path / "cache/custom-models").exists()
        with pytest.raises(CustomModelError, match="confirmed explicitly"):
            importer.execute(preview.id, confirm=False)
        assert calls == [("GET", metadata)]
        descriptor = importer.execute(preview.id, confirm=True)
        assert validator.calls == [(engine, family)] and validator.roles == [roles]
        assert len(calls) == len(weights) + 1
        assert not any(path.endswith((".py", ".pkl")) for _, path in calls)
    record = json.loads(
        (files.resolve_path(descriptor) / ".voz-custom.json").read_text()
    )
    assert record["file_roles"] == roles and record["license"] == "unknown"
    assert all(len(item["sha256"]) == 64 for item in record["files"])
    assert descriptor.source == "org/" + repo and descriptor.revision == revision


@pytest.mark.parametrize(
    ("names", "code"),
    [
        (
            {"model.safetensors", "config.json", "tokenizer.json"},
            "custom_model_engine_unsupported",
        ),
        ({"pytorch_model.bin", "config.json"}, "custom_model_engine_unsupported"),
        ({"model.gguf"}, "custom_model_engine_unsupported"),
        ({"random.onnx", "tokens.txt"}, "custom_model_engine_unsupported"),
        ({"ggml-a.bin", "ggml-b.bin"}, "custom_model_detection_ambiguous"),
        (
            {"encoder.onnx", "encoder.int8.onnx", "decoder.onnx", "tokens.txt"},
            "custom_model_detection_ambiguous",
        ),
        (
            {"model.bin", "config.json", "tokenizer.json", "ggml-a.bin"},
            "custom_model_detection_ambiguous",
        ),
    ],
)
def test_auto_hf_rejects_unsupported_or_ambiguous_without_weight_gets(
    tmp_path: Path,
    names: set[str],
    code: str,
) -> None:
    files, _, validator, _ = stores(tmp_path)
    metadata = "/api/models/org/Qwen-model/revision/main?blobs=true"
    doc = {
        "sha": "c" * 40,
        "siblings": [{"rfilename": name, "size": 10} for name in names],
    }
    with server({metadata: json.dumps(doc).encode()}) as (base, calls):
        store = CustomModelStore(
            files,
            cache_root=tmp_path / "cache",
            hf_base_url=base,
            runtime_available=lambda _: True,
        )
        with pytest.raises(CustomModelError) as raised:
            store.prepare(
                request(
                    "org/Qwen-model",
                    source_type="huggingface",
                    engine="auto",
                    family="",
                    display_name="",
                )
            )
        assert raised.value.code == code
        assert calls == [("GET", metadata)] and validator.calls == []
        assert not (tmp_path / "cache/custom-models").exists()


@pytest.mark.parametrize(
    ("name", "engine", "family"),
    [
        ("ggml-custom.bin", "whisper-cpp", "ggml"),
        ("sherpa-onnx-whisper-tiny.tar.bz2", "sherpa-onnx-asr", "whisper"),
        ("sherpa-onnx-nemo-parakeet-tdt.tar.bz2", "sherpa-onnx-asr", "nemo_transducer"),
        ("kokoro-v1.tar.bz2", "sherpa-onnx-tts", "kokoro"),
        ("kitten-nano.tar.bz2", "sherpa-onnx-tts", "kitten"),
        ("piper-voice.tar.bz2", "sherpa-onnx-tts", "vits"),
    ],
)
def test_auto_direct_url_only_heads_explicit_supported_format(
    tmp_path: Path,
    name: str,
    engine: str,
    family: str,
) -> None:
    _, store, validator, _ = stores(tmp_path)
    with server({"/" + name: b"not validated weights"}) as (base, calls):
        plan = store.prepare(
            request(
                base + "/" + name,
                source_type="url",
                engine="auto",
                family="",
                display_name="",
            )
        )
        assert plan.preview.descriptor.provider_id == engine
        assert plan.preview.family == family and plan.preview.license == "unknown"
        assert calls == [("HEAD", "/" + name)] and validator.calls == []
        assert not (tmp_path / "cache/custom-models").exists()


@pytest.mark.parametrize(
    "name", ["arbitrary.onnx", "model.safetensors", "voice.tar.bz2"]
)
def test_auto_unknown_url_is_rejected_without_network(
    tmp_path: Path, name: str
) -> None:
    _, store, _, _ = stores(tmp_path)
    with server({"/" + name: b"unknown"}) as (base, calls):
        with pytest.raises(CustomModelError) as raised:
            store.prepare(
                request(
                    base + "/" + name,
                    source_type="url",
                    engine="auto",
                    family="",
                    display_name="",
                )
            )
        assert raised.value.code == "custom_model_engine_unsupported"
        assert not calls


def test_auto_runtime_unavailable_checks_metadata_but_never_fetches_weights(
    tmp_path: Path,
) -> None:
    files, _, _, _ = stores(tmp_path)
    metadata = "/api/models/org/ct2/revision/main?blobs=true"
    doc = {
        "sha": "c" * 40,
        "siblings": [
            {"rfilename": name, "size": 10}
            for name in ("model.bin", "config.json", "tokenizer.json")
        ],
    }
    with server({metadata: json.dumps(doc).encode()}) as (base, calls):
        store = CustomModelStore(
            files,
            cache_root=tmp_path / "cache",
            hf_base_url=base,
            runtime_available=lambda _: False,
        )
        with pytest.raises(CustomModelError) as raised:
            store.prepare(
                request(
                    "org/ct2",
                    source_type="huggingface",
                    engine="auto",
                    family="",
                    display_name="",
                )
            )
        assert raised.value.code == "custom_model_runtime_unavailable"
        assert calls == [("GET", metadata)]


def test_link_only_api_request_defaults_to_auto_and_safe_derived_name(
    tmp_path: Path,
) -> None:
    _, _, validator, importer = stores(tmp_path)
    app = FastAPI()
    app.include_router(create_models_router(Mock(), Mock(), custom=importer))
    with server({"/ggml-custom.bin": b"synthetic ggml"}) as (base, calls):
        response = cast(httpx.Client, TestClient(app)).post(
            "/api/models/custom/preview",
            json={"source_type": "url", "source": base + "/ggml-custom.bin"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["descriptor"]["provider_id"] == "whisper-cpp"
        assert response.json()["descriptor"]["display_name"] == "ggml-custom"
        assert calls == [("HEAD", "/ggml-custom.bin")] and validator.calls == []
        assert str(tmp_path) not in response.text


def test_auto_archive_hint_still_requires_successful_load_validation(
    tmp_path: Path,
) -> None:
    files, store, validator, importer = stores(tmp_path)
    validator.error = CustomModelError(
        "custom_model_validation_failed", "Cannot load weights."
    )
    with server({"/piper-voice.tar.bz2": archive()}) as (base, calls):
        preview = importer.prepare(
            request(
                base + "/piper-voice.tar.bz2",
                source_type="url",
                engine="auto",
                family="",
                display_name="",
            )
        )
        assert calls == [("HEAD", "/piper-voice.tar.bz2")] and not validator.calls
        with pytest.raises(CustomModelError) as raised:
            importer.execute(preview.id, confirm=True)
        assert raised.value.code == "custom_model_validation_failed"
        assert calls == [
            ("HEAD", "/piper-voice.tar.bz2"),
            ("GET", "/piper-voice.tar.bz2"),
        ]
    assert validator.calls == [("sherpa-onnx-tts", "vits")]
    assert files.registered_descriptors() == () and store.managed_entries() == ()


@pytest.mark.parametrize("cancelled", [False, True])
def test_auto_hf_checksum_and_cancellation_fail_before_validation(
    tmp_path: Path,
    cancelled: bool,
) -> None:
    files, _, validator, _ = stores(tmp_path)
    metadata = "/api/models/org/model/revision/main?blobs=true"
    prefix = "/org/model/resolve/" + "d" * 40 + "/ggml-model.bin"
    body = b"fake weights"
    doc = {
        "sha": "d" * 40,
        "siblings": [
            {
                "rfilename": "ggml-model.bin",
                "size": len(body),
                "lfs": {"sha256": "0" * 64},
            }
        ],
    }
    with server({metadata: json.dumps(doc).encode(), prefix: body}) as (base, calls):
        store = CustomModelStore(
            files,
            cache_root=tmp_path / "cache",
            hf_base_url=base,
            runtime_available=lambda _: True,
        )
        importer = ImportCustomModel(store, validator)
        preview = importer.prepare(
            request(
                "org/model",
                source_type="huggingface",
                engine="auto",
                family="",
                display_name="",
            )
        )
        with pytest.raises((CustomModelError, ModelInstallationError)):
            importer.execute(preview.id, confirm=True, cancelled=lambda: cancelled)
        assert calls == [("GET", metadata)] + ([] if cancelled else [("GET", prefix)])
    assert not validator.calls and not files.registered_descriptors()


def test_auto_folder_remains_manual_without_scanning(tmp_path: Path) -> None:
    _, store, _, _ = stores(tmp_path)
    with pytest.raises(CustomModelError) as raised:
        store.prepare(request(tmp_path / "not-scanned", engine="auto", family=""))
    assert raised.value.code == "custom_model_engine_unsupported"


def test_nemo_transducer_import_is_cpu_only_and_persists_after_restart(
    tmp_path: Path,
) -> None:
    files, _store, validator, importer = stores(tmp_path)
    source = whisper_folder(tmp_path / "source")
    (source / "joiner.int8.onnx").write_bytes(b"synthetic")
    preview = importer.prepare(
        request(source, engine="sherpa-onnx-asr", family="nemo_transducer")
    )
    assert preview.file_count == 4
    assert preview.descriptor.profile is not None
    assert preview.descriptor.profile.cpu_precision is ComputePrecision.NATIVE
    assert preview.descriptor.capabilities == frozenset(
        {ModelCapability.CPU, ModelCapability.TRANSCRIPTION}
    )
    descriptor = importer.execute(preview.id, confirm=True)
    installed = files.resolve_path(descriptor)
    assert set(custom_models.model_files(installed, "nemo_transducer", {})) == {
        "encoder",
        "decoder",
        "joiner",
        "tokens",
    }
    assert not (installed / "untrusted.py").exists()
    assert validator.calls == [("sherpa-onnx-asr", "nemo_transducer")]
    reopened = CustomModelStore(
        files, cache_root=tmp_path / "cache", runtime_available=lambda _: True
    )
    assert (
        reopened.list_models(ModelCapability.TRANSCRIPTION)[0].descriptor == descriptor
    )


@pytest.mark.parametrize("missing_joiner", [False, True])
def test_auto_nemo_archive_validates_four_weights_before_registration(
    tmp_path: Path, missing_joiner: bool
) -> None:
    files, store, validator, importer = stores(tmp_path)
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:bz2") as bundle:
        for name in (
            "encoder.int8.onnx",
            "decoder.int8.onnx",
            "joiner.int8.onnx",
            "tokens.txt",
            "run.py",
        ):
            if missing_joiner and name == "joiner.int8.onnx":
                continue
            item = tarfile.TarInfo("nemo/" + name)
            item.size = 7
            bundle.addfile(item, io.BytesIO(b"weights"))
    path = "/sherpa-onnx-nemo-parakeet-tdt-v3-int8.tar.bz2"
    with server({path: data.getvalue()}) as (base, calls):
        preview = importer.prepare(
            request(
                base + path,
                source_type="url",
                engine="auto",
                family="",
                display_name="",
            )
        )
        assert preview.family == "nemo_transducer"
        if missing_joiner:
            with pytest.raises(CustomModelError):
                importer.execute(preview.id, confirm=True)
            assert validator.calls == [] and store.managed_entries() == ()
        else:
            descriptor = importer.execute(preview.id, confirm=True)
            assert validator.calls == [("sherpa-onnx-asr", "nemo_transducer")]
            installed = files.resolve_path(descriptor)
            assert len(custom_models.model_files(installed, "nemo_transducer", {})) == 4
            assert not (installed / "run.py").exists()
        assert calls == [("HEAD", path), ("GET", path)]
