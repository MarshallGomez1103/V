"""Installed runtime discovery does not require downloading a first ASR model."""

import sys
import time
from functools import partial
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient

import voz.bootstrap as bootstrap
from voz.application.ports.custom_models import CustomValidation
from voz.application.ports.model_installation import CancelCheck
from voz.bootstrap import create_app
from voz.infrastructure.asr.sherpa_onnx import SherpaOnnxProvider
from voz.infrastructure.custom_models import CustomModelStore

WORKER = Path(__file__).parents[1] / "fixtures/asr/fake_sherpa_onnx_worker.py"
WAV = Path(__file__).parents[1] / "fixtures/media/synthetic-tone.wav"


class Validator:
    def validate(
        self,
        directory: Path,
        engine: str,
        family: str,
        *,
        file_roles: dict[str, str],
        cancelled: CancelCheck,
    ) -> CustomValidation:
        assert (
            directory.is_dir() and engine == "sherpa-onnx-asr" and family == "whisper"
        )
        assert not cancelled()
        return CustomValidation()


def test_custom_engine_is_available_before_first_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "voz.bootstrap.sherpa_asr_available", lambda: True, raising=False
    )
    with TestClient(create_app()) as raw:
        client = cast(httpx.Client, raw)
        result = client.get("/api/models")
        assert result.status_code == 200
        assert "sherpa-onnx-asr" in result.json().get("custom_engines", [])


def test_imported_whisper_runs_existing_jobs_and_compatible_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for name in ("encoder.onnx", "decoder.onnx", "tokens.txt"):
        (source / name).write_bytes(b"synthetic weights")
    monkeypatch.setattr(
        bootstrap,
        "CustomModelStore",
        partial(CustomModelStore, runtime_available=lambda _: True),
    )
    monkeypatch.setattr(bootstrap, "SubprocessModelValidator", Validator)
    monkeypatch.setattr(
        bootstrap,
        "SherpaOnnxProvider",
        partial(SherpaOnnxProvider, worker_argv=(sys.executable, str(WORKER))),
    )
    with TestClient(create_app()) as raw:
        client = cast(httpx.Client, raw)
        preview = client.post(
            "/api/models/custom/preview",
            json={
                "source_type": "folder",
                "source": str(source),
                "engine": "sherpa-onnx-asr",
                "family": "whisper",
                "display_name": "Synthetic Whisper ONNX",
                "license": "MIT",
            },
        )
        assert preview.status_code == 200, preview.text
        installed = client.post(
            "/api/models/custom/install",
            json={
                "preview_id": preview.json()["id"],
                "confirm": True,
            },
        )
        assert installed.status_code == 202, installed.text
        deadline = time.monotonic() + 5
        while True:
            task = client.get("/api/model-tasks/" + installed.json()["id"]).json()
            if task["state"] in {"completed", "failed", "cancelled"}:
                break
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert task["state"] == "completed", task
        option = next(
            item
            for item in client.get("/api/transcription-options").json()["options"]
            if item["provider_id"] == "sherpa-onnx-asr"
        )
        assert option["can_start"] and option["execution"]["precision"] == "native"
        assert set(option["capabilities"]) == {"transcription", "cpu"}
        result = client.post(
            "/v1/audio/transcriptions",
            data={"model": task["key"], "language": "es"},
            files={"file": ("test.wav", WAV.read_bytes(), "audio/wav")},
        )
        assert result.status_code == 200, result.text
        assert result.json() == {"text": "hola mundo"}
        assert (source / "encoder.onnx").read_bytes() == b"synthetic weights"
        removed = client.delete(
            "/api/models/" + task["key"], params={"confirm": task["key"]}
        )
        assert removed.status_code == 200, removed.text
