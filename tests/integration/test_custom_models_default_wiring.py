"""Custom model imports through the default app, with isolated fake loaders."""

from __future__ import annotations

import json
import sys
import time
from functools import partial
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

import voz.bootstrap as bootstrap
from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.compute_slot import ComputeKind, ComputeSlot
from voz.application.ports.custom_models import CustomValidation
from voz.application.ports.model_installation import CancelCheck
from voz.application.ports.transcription_options import RuntimeAvailability
from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.processing_profile import ComputePrecision
from voz.domain.entities.voice import Voice
from voz.infrastructure.custom_models import CustomModelStore
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.tts.sherpa_provider import sherpa_tts_info
from voz.infrastructure.tts.subprocess_provider import (
    ManifestSource,
    SubprocessSynthesisProvider,
)

WORKER = Path(__file__).parents[1] / "fixtures/tts/fake_tts_worker.py"


class FakeValidator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def validate(
        self,
        directory: Path,
        engine: str,
        family: str,
        *,
        file_roles: dict[str, str],
        cancelled: CancelCheck,
    ) -> CustomValidation:
        assert directory.is_dir() and not cancelled()
        self.calls.append(engine)
        return (
            CustomValidation((Voice("0", "Test voice", ("es",)),), ("es",))
            if engine == "sherpa-onnx-tts"
            else CustomValidation()
        )


class FakeRuntime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            True,
            hardware=HardwareCapabilities(
                frozenset(), frozenset({ComputePrecision.INT8})
            ),
            capabilities=frozenset(
                {ModelCapability.TRANSCRIPTION, ModelCapability.CPU}
            ),
        )


def _client(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    validator: FakeValidator,
    slot: ComputeSlot | None = None,
    *,
    runtime_available: bool = True,
) -> httpx.Client:
    monkeypatch.setattr(bootstrap, "SubprocessModelValidator", lambda: validator)
    monkeypatch.setattr(
        bootstrap,
        "CustomModelStore",
        partial(CustomModelStore, runtime_available=lambda _: runtime_available),
    )
    monkeypatch.setattr(bootstrap, "FasterWhisperRuntimeProbe", FakeRuntime)
    real_find_spec = bootstrap.find_spec

    def fake_find_spec(name: str) -> object:
        return object() if name == "sherpa_onnx" else real_find_spec(name)

    monkeypatch.setattr(bootstrap, "find_spec", fake_find_spec)
    if slot is not None:
        monkeypatch.setattr(bootstrap, "ComputeSlot", lambda: slot)

    def fake_sherpa(manifests: ManifestSource) -> SubprocessSynthesisProvider:
        return SubprocessSynthesisProvider(
            info=sherpa_tts_info(),
            argv=[sys.executable, str(WORKER)],
            manifests=manifests,
        )

    monkeypatch.setattr(bootstrap, "sherpa_tts_provider", fake_sherpa)
    app = bootstrap.create_app(
        paths=VozPaths(root / "config", root / "data", root / "cache", root / "state")
    )
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def _folder(root: Path, *, tts: bool = False) -> Path:
    root.mkdir()
    files = (
        {"voice.onnx": b"fake weights", "tokens.txt": b"a 0\n"}
        if tts
        else {
            "model.bin": b"fake weights",
            "config.json": b"{}",
            "tokenizer.json": b"{}",
        }
    )
    for name, body in files.items():
        (root / name).write_bytes(body)
    return root


def _preview(
    client: httpx.Client, folder: Path, *, tts: bool = False
) -> dict[str, Any]:
    response = client.post(
        "/api/models/custom/preview",
        json={
            "source_type": "folder",
            "source": str(folder),
            "engine": "sherpa-onnx-tts" if tts else "faster-whisper",
            "family": "vits" if tts else "ctranslate2",
            "display_name": "Custom test model",
        },
    )
    assert response.status_code == 200, response.text
    assert str(folder) not in response.text
    assert response.json()["descriptor"]["revision"] is None
    return response.json()


def _wait(
    client: httpx.Client, url: str, *, field: str, terminal: set[str]
) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(url)
        assert response.status_code == 200
        body = response.json()
        if body[field] in terminal:
            return body
        time.sleep(0.01)
    raise AssertionError("Background work did not finish")


def _install(client: httpx.Client, preview: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/models/custom/install",
        json={"preview_id": preview["id"], "confirm": True},
    )
    assert response.status_code == 202
    task = _wait(
        client,
        "/api/model-tasks/" + response.json()["id"],
        field="state",
        terminal={"completed", "failed", "cancelled"},
    )
    assert task["state"] == "completed", task
    return task


def test_custom_asr_is_pinned_listed_startable_and_removable_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _folder(tmp_path / "original")
    validator = FakeValidator()
    with _client(tmp_path / "app", monkeypatch, validator) as client:
        preview = _preview(client, folder)
        refused = client.post(
            "/api/models/custom/install", json={"preview_id": preview["id"]}
        )
        assert refused.status_code == 400 and not validator.calls
        task = _install(client, preview)
        model = next(
            model
            for model in client.get("/api/models").json()["models"]
            if model["key"] == task["key"]
        )
        assert model["installed"] and "transcription" in model["capabilities"]
        assert model["revision"] and model["revision"] != "0" * 40
        assert model["license"] == "unknown"
        option = next(
            option
            for option in client.get("/api/transcription-options").json()["options"]
            if option["model_id"] == task["model_id"]
        )
        assert option["can_start"] is True
        metadata = list((tmp_path / "app/data").rglob(".voz-custom.json"))
        assert len(metadata) == 1
        assert all(
            len(item["sha256"]) == 64
            for item in json.loads(metadata[0].read_text())["files"]
        )
    with _client(tmp_path / "app", monkeypatch, validator) as client:
        assert any(
            model["key"] == task["key"]
            for model in client.get("/api/models").json()["models"]
        )
        removed = client.delete(
            "/api/models/" + task["key"], params={"confirm": task["key"]}
        )
        assert removed.status_code == 200
        assert all(
            model["key"] != task["key"]
            for model in client.get("/api/models").json()["models"]
        )
    assert (folder / "model.bin").read_bytes() == b"fake weights"


def test_custom_tts_is_available_live_and_synthesizes_through_the_wired_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = FakeValidator()
    folder = _folder(tmp_path / "original", tts=True)
    with _client(tmp_path / "app", monkeypatch, validator) as client:
        task = _install(client, _preview(client, folder, tts=True))
        model = next(
            model
            for model in client.get("/api/synthesis/options").json()["models"]
            if model["model_id"] == task["model_id"]
        )
        assert model["voices"][0]["name"] == "Test voice"
        created = client.post(
            "/api/synthesis",
            json={
                "text": "Prueba",
                "provider_id": "sherpa-onnx-tts",
                "model_id": task["model_id"],
                "voice_id": "0",
            },
        )
        assert created.status_code == 201
        job = _wait(
            client,
            "/api/synthesis/" + created.json()["id"],
            field="state",
            terminal={"COMPLETED", "FAILED"},
        )
        assert job["state"] == "COMPLETED", job
        assert client.get(job["audio"]["url"]).content.startswith(b"RIFF")
        assert (
            client.delete(
                "/api/models/" + task["key"], params={"confirm": task["key"]}
            ).status_code
            == 200
        )
        assert all(
            model["model_id"] != task["model_id"]
            for model in client.get("/api/synthesis/options").json()["models"]
        )
    assert validator.calls == ["sherpa-onnx-tts"]


def test_cancelled_import_waiting_for_compute_never_loads_or_registers_weights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = ComputeSlot()
    validator = FakeValidator()
    folder = _folder(tmp_path / "original")
    with _client(tmp_path / "app", monkeypatch, validator, slot) as client:
        preview = _preview(client, folder)
        with slot.hold(ComputeKind.TRANSCRIPTION, uuid4()):
            response = client.post(
                "/api/models/custom/install",
                json={"preview_id": preview["id"], "confirm": True},
            )
            task_id = response.json()["id"]
            deadline = time.monotonic() + 3
            while not slot.waiting() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert slot.waiting()[0].kind is ComputeKind.MODEL_VALIDATION
            assert not validator.calls
            assert (
                client.post("/api/model-tasks/" + task_id + "/cancel").status_code
                == 202
            )
            task = _wait(
                client,
                "/api/model-tasks/" + task_id,
                field="state",
                terminal={"completed", "failed", "cancelled"},
            )
            assert task["state"] == "cancelled"
        assert not slot.waiting() and slot.holder() is None
        assert not validator.calls
        assert all(
            not model["model_id"].startswith("custom-")
            for model in client.get("/api/models").json()["models"]
        )


def test_browser_folder_upload_previews_and_installs_without_host_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "model.bin": b"fake weights",
        "config.json": b"{}",
        "tokenizer.json": b"{}",
    }
    validator = FakeValidator()
    with _client(tmp_path / "app", monkeypatch, validator) as client:
        created = client.post(
            "/api/models/custom/uploads",
            json={
                "engine": "faster-whisper",
                "family": "ctranslate2",
                "display_name": "Browser folder",
                "files": [
                    {"name": name, "size_bytes": len(body)}
                    for name, body in files.items()
                ],
            },
        )
        assert created.status_code == 201, created.text
        upload_id = created.json()["id"]
        base = "/api/models/custom/uploads/" + upload_id
        assert created.json()["file_count"] == 3
        incomplete = client.post(base + "/preview")
        assert incomplete.status_code == 422 and not validator.calls
        for index, body in enumerate(files.values()):
            sent = client.put(base + "/files/" + str(index), content=body)
            assert sent.status_code == 204, sent.text
        preview = client.post(base + "/preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["size_bytes"] == sum(map(len, files.values()))
        task = _install(client, preview.json())
        assert client.delete(base).status_code == 204
        assert client.delete(base).status_code == 204
        listed = client.get("/api/models")
        assert any(
            model["key"] == task["key"] and model["installed"]
            for model in listed.json()["models"]
        )
        assert (
            client.delete(
                "/api/models/" + task["key"], params={"confirm": task["key"]}
            ).status_code
            == 200
        )
        for response in (created, incomplete, preview, listed):
            assert str(tmp_path) not in response.text


@pytest.mark.parametrize(
    "filename", ["../private-source-secret.bin", "/private-source-secret.bin"]
)
def test_browser_folder_upload_rejects_unsafe_names_without_reflecting_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    with _client(tmp_path / "app", monkeypatch, FakeValidator()) as client:
        response = client.post(
            "/api/models/custom/uploads",
            json={
                "engine": "faster-whisper",
                "family": "ctranslate2",
                "display_name": "Test",
                "files": [{"name": filename, "size_bytes": 1}],
            },
        )
        assert response.status_code == 422
        assert "private-source-secret" not in response.text


def test_browser_folder_upload_checks_runtime_before_accepting_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "app"
    with _client(root, monkeypatch, FakeValidator(), runtime_available=False) as client:
        response = client.post(
            "/api/models/custom/uploads",
            json={
                "engine": "faster-whisper",
                "family": "ctranslate2",
                "display_name": "Test",
                "files": [{"name": "model.bin", "size_bytes": 1}],
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "custom_model_runtime_unavailable"
    assert not (root / "cache/custom-model-uploads").exists()


def test_nemo_browser_import_is_listed_with_cpu_native_execution_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        name: b"fake weights"
        for name in (
            "encoder.int8.onnx",
            "decoder.int8.onnx",
            "joiner.int8.onnx",
            "tokens.txt",
        )
    }
    validator = FakeValidator()
    with _client(tmp_path / "app", monkeypatch, validator) as client:
        created = client.post(
            "/api/models/custom/uploads",
            json={
                "engine": "sherpa-onnx-asr",
                "family": "nemo_transducer",
                "display_name": "NeMo test",
                "files": [
                    {"name": name, "size_bytes": len(body)}
                    for name, body in files.items()
                ],
                "file_roles": {
                    "encoder": "encoder.int8.onnx",
                    "decoder": "decoder.int8.onnx",
                    "joiner": "joiner.int8.onnx",
                    "tokens": "tokens.txt",
                },
            },
        )
        assert created.status_code == 201, created.text
        base = "/api/models/custom/uploads/" + created.json()["id"]
        for index, body in enumerate(files.values()):
            assert (
                client.put(base + "/files/" + str(index), content=body).status_code
                == 204
            )
        preview = client.post(base + "/preview")
        assert preview.status_code == 200, preview.text
        task = _install(client, preview.json())
        assert client.delete(base).status_code == 204
    with _client(tmp_path / "app", monkeypatch, validator) as client:
        option = next(
            option
            for option in client.get("/api/transcription-options").json()["options"]
            if option["model_id"] == task["model_id"]
        )
        assert option["can_start"]
        assert option["execution"]["device"] == "cpu"
        assert option["execution"]["precision"] == "native"
        assert set(option["capabilities"]) == {"transcription", "cpu"}
        assert str(tmp_path) not in json.dumps(option)
    assert validator.calls == ["sherpa-onnx-asr"]
