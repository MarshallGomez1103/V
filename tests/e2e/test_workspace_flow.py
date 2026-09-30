"""S5.17 backend E2E: real HTTP app, real runner thread, real ffmpeg, fake ASR."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.bootstrap import create_app
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.infrastructure.paths import VozPaths

REPOSITORY_ROOT = Path(__file__).parents[2]
WAV = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"
MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    source="example/fake-asr",
    revision="e" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16,),
        ComputePrecision.INT8,
    ),
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required for the real import and waveform path",
)


class _Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (ModelRegistration(MODEL, InstallationStatus.REGISTERED, True),)


class _Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        del provider_id
        return RuntimeAvailability(
            True,
            HardwareCapabilities(frozenset(), frozenset({ComputePrecision.INT8})),
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


class _FakeAsr:
    """Deterministic ASR; optionally parks inside ``transcribe`` until released."""

    provider_id = "fake-asr"

    def __init__(self, gate: threading.Event | None = None) -> None:
        self.gate = gate
        self.started = threading.Event()

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del options, cancellation
        assert audio.read(4) == b"RIFF"
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(15), "test never released the fake ASR"
        return TranscriptionResult(
            (
                TranscriptionSegment(0, 120, "hola mundo"),
                TranscriptionSegment(120, 250, "segundo tramo"),
            ),
            "es",
        )


def _paths(root: Path) -> VozPaths:
    return VozPaths(
        config=root / "config",
        data=root / "data",
        cache=root / "cache",
        state=root / "state",
    )


def _client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asr: _FakeAsr
) -> httpx.Client:
    # ponytail: no injection hook for the runtime in create_app; patch the
    # composition function instead of adding a parameter for one test.
    def fake_runtime(descriptor: ModelDescriptor, **_: object) -> SimpleNamespace:
        del descriptor
        return SimpleNamespace(
            providers=TranscriptionProviderRegistry((asr,)), close=lambda: None
        )

    monkeypatch.setattr("voz.bootstrap.create_local_asr_runtime", fake_runtime)
    app = create_app(
        transcription_options=GetTranscriptionOptions(_Catalog(), _Runtime()),
        paths=_paths(tmp_path),
    )
    # TestClient is an httpx.Client; its own stubs resolve to Unknown under pyright.
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def _within[T](seconds: float, call: Callable[[], T]) -> T:
    """Fail instead of hanging when a streaming call never ends."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(call).result(timeout=seconds)


def _sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.split("\n\n"):
        name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        if name:
            events.append((name, cast(dict[str, object], json.loads(data))))
    return events


def _import(client: httpx.Client, name: str = "Curso E2E") -> tuple[str, str]:
    created = client.post("/api/projects", json={"name": name})
    assert created.status_code == 201
    project_id = created.json()["id"]
    uploaded = client.post(
        f"/api/projects/{project_id}/media",
        content=WAV.read_bytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Voz-Filename": "synthetic-tone.wav",
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["filename"] == "synthetic-tone.wav"
    assert body["duration_ms"] > 0
    return project_id, body["media_asset_id"]


def _start_job(
    client: httpx.Client, project_id: str, media_id: str
) -> dict[str, object]:
    options = client.get("/api/transcription-options")
    assert options.status_code == 200
    (option,) = options.json()["options"]
    assert option["can_start"] is True
    started = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "media_asset_id": media_id,
            "option_id": option["option_id"],
            "language": "es",
        },
    )
    assert started.status_code == 201, started.text
    return cast(dict[str, object], started.json())


def _wait_state(client: httpx.Client, job_id: str, state: str) -> dict[str, object]:
    deadline = time.monotonic() + 15
    job: dict[str, object] = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] == state:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job never reached {state}: {job}")


def _texts(segments: list[dict[str, object]]) -> list[object]:
    return [item["text"] for item in segments]


def test_import_transcribe_play_edit_export_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asr = _FakeAsr()
    with _client(tmp_path, monkeypatch, asr) as client:
        project_id, media_id = _import(client)
        job = _start_job(client, project_id, media_id)
        job_id = str(job["id"])

        response = _within(30, lambda: client.get(f"/api/jobs/{job_id}/events"))
        events = _sse(response.text)
        assert events[0][0] == "job"
        assert events[-2][0] == "job" and events[-2][1]["state"] == "COMPLETED"
        assert events[-1][0] == "end"
        states = [cast(str, data["state"]) for name, data in events if name == "job"]
        assert states[-1] == "COMPLETED"
        progress = [cast(float, data["progress"]) for _, data in events[:-1]]
        assert progress == sorted(progress)

        done = client.get(f"/api/jobs/{job_id}").json()
        assert done["state"] == "COMPLETED" and done["progress"] == 1.0
        transcript_id = done["transcript_id"]
        assert str(tmp_path) not in json.dumps(done)

        listed = client.get(f"/api/transcripts/{transcript_id}/segments").json()
        segments = listed["segments"]
        assert _texts(segments) == ["hola mundo", "segundo tramo"]
        assert [(s["start_ms"], s["end_ms"]) for s in segments] == [
            (0, 120),
            (120, 250),
        ]
        assert all(s["revision"] == 0 and not s["edited"] for s in segments)

        ranged = client.get(
            f"/api/media/{media_id}/original", headers={"Range": "bytes=0-99"}
        )
        assert ranged.status_code == 206
        assert ranged.headers["content-range"].startswith("bytes 0-99/")
        assert ranged.content == WAV.read_bytes()[:100]

        peaks = client.get(f"/api/media/{media_id}/peaks", params={"buckets": 100})
        assert peaks.status_code == 200
        assert len(peaks.json()["peaks"]) == 100
        assert peaks.json()["media_asset_id"] == media_id

        first = segments[0]
        edited = client.put(
            f"/api/segments/{first['id']}",
            json={"text": "  Hola, mundo editado.  ", "revision": first["revision"]},
        )
        assert edited.status_code == 200
        assert edited.json()["text"] == "Hola, mundo editado."
        assert edited.json()["edited"] is True and edited.json()["revision"] == 1

        stale = client.put(
            f"/api/segments/{first['id']}",
            json={"text": "otra pestaña", "revision": 0},
        )
        assert stale.status_code == 409
        detail = stale.json()["detail"]
        assert detail["code"] == "segment_revision_conflict"
        assert detail["current"]["text"] == "Hola, mundo editado."

        txt = client.get(
            f"/api/transcripts/{transcript_id}/export", params={"format": "txt"}
        )
        assert txt.status_code == 200
        assert "Hola, mundo editado." in txt.text and "segundo tramo" in txt.text
        assert "hola mundo" not in txt.text
        srt = client.get(
            f"/api/transcripts/{transcript_id}/export", params={"format": "srt"}
        )
        assert srt.status_code == 200
        assert srt.text.startswith(
            "1\n00:00:00,000 --> 00:00:00,120\nHola, mundo editado.\n\n2\n"
        )
        assert "00:00:00,120 --> 00:00:00,250\nsegundo tramo" in srt.text
        assert "Curso E2E" in srt.headers["content-disposition"]

    # Restart with the same XDG directories: everything comes from disk.
    with _client(tmp_path, monkeypatch, _FakeAsr()) as client:
        projects = client.get("/api/projects").json()["projects"]
        assert [p["id"] for p in projects] == [project_id]
        jobs = client.get("/api/jobs", params={"project_id": project_id}).json()
        assert [(j["id"], j["state"]) for j in jobs["jobs"]] == [(job_id, "COMPLETED")]
        reloaded = client.get(f"/api/transcripts/{transcript_id}/segments").json()
        assert _texts(reloaded["segments"]) == ["Hola, mundo editado.", "segundo tramo"]
        assert reloaded["segments"][0]["revision"] == 1
        txt = client.get(
            f"/api/transcripts/{transcript_id}/export", params={"format": "txt"}
        )
        assert "Hola, mundo editado." in txt.text
        assert (
            client.get(
                f"/api/media/{media_id}/original", headers={"Range": "bytes=0-9"}
            ).status_code
            == 206
        )


def test_cancelling_a_running_job_ends_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = threading.Event()
    asr = _FakeAsr(gate)
    try:
        with _client(tmp_path, monkeypatch, asr) as client:
            project_id, media_id = _import(client)
            job_id = str(_start_job(client, project_id, media_id)["id"])
            assert asr.started.wait(15), "the runner never reached the ASR"

            cancelled = client.post(f"/api/jobs/{job_id}/cancel")
            assert cancelled.status_code == 202
            assert cancelled.json()["state"] == "CANCELLING"
            gate.set()

            final = _wait_state(client, job_id, "CANCELLED")
            assert final["transcript_id"] is None
            again = client.post(f"/api/jobs/{job_id}/cancel")
            assert (again.status_code, again.json()["detail"]["code"]) == (
                409,
                "job_terminal",
            )
            events = _sse(
                _within(30, lambda: client.get(f"/api/jobs/{job_id}/events")).text
            )
            assert events[-1][0] == "end"
            assert events[-2][1]["state"] == "CANCELLED"
    finally:
        gate.set()
