"""The default TTS wiring of ``create_app`` (V4-06), without network.

The real ``TtsModelStore``, ``InstalledTtsModels``, ``RoutingModelStore`` and
``RemoveModel``; a catalog model "installed" on disk by hand (as the store
publishes it) and the sherpa engine's child replaced by the fake pipe worker,
since the model files are not real ONNX.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import io
import json
import shutil
import sys
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import voz.bootstrap
from voz.bootstrap import create_app
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.tts.catalog import TTS_CATALOG, TTS_PROVIDER_ID
from voz.infrastructure.tts.sherpa_provider import sherpa_tts_info
from voz.infrastructure.tts.subprocess_provider import (
    ManifestSource,
    SubprocessSynthesisProvider,
)

WORKER = Path(__file__).parents[1] / "fixtures" / "tts" / "fake_tts_worker.py"
ENTRY = next(e for e in TTS_CATALOG if e.model_id == "piper-es_MX-ald-medium")
KEY = f"{TTS_PROVIDER_ID}:{ENTRY.model_id}"


def _install_by_hand(data: Path) -> Path:
    """What ``TtsModelStore._publish`` leaves on disk, with fake contents."""
    directory = data / "models" / "tts" / ENTRY.model_id
    sizes: dict[str, int] = {}
    for _, rel in ENTRY.files:
        (directory / rel).parent.mkdir(parents=True, exist_ok=True)
        (directory / rel).write_bytes(b"not an onnx model")
        sizes[rel] = len(b"not an onnx model")
    (directory / "espeak-ng-data").mkdir()
    (directory / "espeak-ng-data" / "phontab").write_bytes(b"p")
    manifest = {"model_id": ENTRY.model_id, "sha256": ENTRY.sha256, "files": sizes}
    (directory / ".voz-tts.json").write_text(json.dumps(manifest))
    return directory


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    def fake_engine(
        manifests: ManifestSource, **_: object
    ) -> SubprocessSynthesisProvider:
        return SubprocessSynthesisProvider(
            info=sherpa_tts_info(),
            argv=[sys.executable, str(WORKER)],
            manifests=manifests,
        )

    real_find_spec = voz.bootstrap.find_spec

    def find_spec(name: str) -> object:  # the engine is there, whatever the venv
        return object() if name == "sherpa_onnx" else real_find_spec(name)

    monkeypatch.setattr(voz.bootstrap, "find_spec", find_spec)
    monkeypatch.setattr(voz.bootstrap, "sherpa_tts_provider", fake_engine)
    for name in ("data", "state"):
        (tmp_path / name).mkdir()
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    with TestClient(create_app(paths=paths)) as test_client:
        yield test_client


def _wait_state(client: TestClient, job_id: str, states: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        view = client.get(f"/api/synthesis/{job_id}").json()
        if view["state"] in states:
            return view
        time.sleep(0.02)
    raise AssertionError(f"the synthesis job never reached {states}")


def _synthesize(client: TestClient, text: str) -> Any:
    return client.post(
        "/api/synthesis",
        json={
            "text": text,
            "provider_id": TTS_PROVIDER_ID,
            "model_id": ENTRY.model_id,
            "voice_id": "0",
        },
    )


def test_install_synthesize_block_and_delete_through_the_default_wiring(
    client: TestClient, tmp_path: Path
) -> None:
    options = client.get("/api/synthesis/options").json()
    assert [p["provider_id"] for p in options["providers"]] == [
        "openai-compatible",
        "openai-compatible-cloud",
        TTS_PROVIDER_ID,
    ]
    assert options["models"] == []
    listed = {m["key"]: m for m in client.get("/api/models").json()["models"]}
    assert listed[KEY]["installed"] is False
    assert listed[KEY]["runtime_available"] is True

    directory = _install_by_hand(tmp_path / "data")  # after the app was built

    assert {m["key"]: m for m in client.get("/api/models").json()["models"]}[KEY][
        "installed"
    ]
    (model,) = client.get("/api/synthesis/options").json()["models"]
    assert (model["model_id"], model["runtime_ready"]) == (ENTRY.model_id, True)
    assert model["voices"] == [{"id": "0", "name": "ald", "languages": ["es"]}]
    assert str(tmp_path) not in json.dumps(model)

    created = _synthesize(client, "Hola, soy V.")
    assert created.status_code == 201, created.text
    done = _wait_state(client, created.json()["id"], {"COMPLETED", "FAILED"})
    assert done["state"] == "COMPLETED"
    audio = client.get(f"/api/synthesis/{done['id']}/audio")
    with wave.open(io.BytesIO(audio.content)) as reader:
        assert reader.getnchannels() == 1 and reader.getnframes() > 0

    slow = _synthesize(client, "Una frase lenta @slow").json()
    _wait_state(client, slow["id"], {"RUNNING"})
    blocked = client.delete(f"/api/models/{KEY}", params={"confirm": KEY})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "model_in_use"
    assert directory.is_dir()

    client.post(f"/api/synthesis/{slow['id']}/cancel")
    _wait_state(client, slow["id"], {"CANCELLED"})
    deleted = client.delete(f"/api/models/{KEY}", params={"confirm": KEY})
    assert deleted.status_code == 200, deleted.text
    assert not directory.exists()

    assert client.get("/api/synthesis/options").json()["models"] == []
    gone = _synthesize(client, "Otra frase distinta.")
    assert gone.status_code == 404
    assert gone.json()["detail"]["code"] == "synthesis_model_unknown"


def test_a_deleted_model_disappears_from_the_engine_without_a_restart(
    client: TestClient, tmp_path: Path
) -> None:
    directory = _install_by_hand(tmp_path / "data")
    assert client.get("/api/synthesis/options").json()["models"]

    shutil.rmtree(directory)  # removed behind the Model Manager's back

    assert client.get("/api/synthesis/options").json()["models"] == []
