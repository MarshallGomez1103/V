"""S14.13: close VOZ in the middle of a long job, reopen, and finish it.

Real HTTP app, real runner thread, real ffmpeg, slow fake ASR over many chunks.
The first app exits its lifespan while the job is mid-way; the second one opens
the same XDG directories and must finish the job without repeating a confirmed
chunk and without duplicating segments.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import functools
import hashlib
import shutil
import sqlite3
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any, BinaryIO, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.chunked_transcription import plan_audio_chunks
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.job_runner import JobRunner
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
from voz.bootstrap import DATABASE_FILENAME, create_app
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.infrastructure.paths import VozPaths

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

SAMPLE_RATE = 16_000
BLOCK_MS = 500
BLOCKS = 8  # 4 s of audio, one distinct 500 ms block per chunk
OVERLAP_MS = 100
PARK_AT_CALL = 3  # the first app is closed while this call is in flight

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required for the real import and normalization path",
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


class _SlowAsr:
    """One segment per clip, named after the clip's audio, a little slow.

    ``park_at`` makes that call wait until the runner is asked to stop, so the
    test can close the app deterministically while the job is mid-way.
    """

    provider_id = "fake-asr"

    def __init__(self, runner: list[JobRunner], park_at: int | None = None) -> None:
        self._runner = runner
        self._park_at = park_at
        self.parked = threading.Event()
        self.clips: list[str] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del options, cancellation
        with wave.open(audio, "rb") as source:
            duration_ms = source.getnframes() * 1_000 // source.getframerate()
            digest = hashlib.sha256(source.readframes(source.getnframes()))
        name = digest.hexdigest()[:12]
        self.clips.append(name)
        time.sleep(0.02)
        if self._park_at == len(self.clips):
            self.parked.set()
            assert self._runner[0]._stopping.wait(15), "the app was never closed"  # pyright: ignore[reportPrivateUsage]
        return TranscriptionResult(
            (TranscriptionSegment(0, duration_ms, f"clip-{name}"),), "es"
        )


def _paths(root: Path) -> VozPaths:
    return VozPaths(
        config=root / "config",
        data=root / "data",
        cache=root / "cache",
        state=root / "state",
    )


def _long_wav(target: Path) -> Path:
    """16 kHz mono PCM, every 500 ms block a different level: clips are unique."""
    block = SAMPLE_RATE * BLOCK_MS // 1_000
    with wave.open(str(target), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for index in range(BLOCKS):
            level = 2_000 * (index + 1)
            output.writeframes(level.to_bytes(2, "little", signed=True) * block)
    return target


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asr: _SlowAsr,
    runner: list[JobRunner],
) -> httpx.Client:
    # ponytail: no injection hook for the runtime or the chunk size in
    # create_app; patch the composition names instead of adding parameters.
    def fake_runtime(descriptor: ModelDescriptor, **_: object) -> SimpleNamespace:
        del descriptor
        return SimpleNamespace(
            providers=TranscriptionProviderRegistry((asr,)), close=lambda: None
        )

    def small_chunks(**wiring: Any) -> JobRunner:
        created = functools.partial(
            JobRunner, chunk_duration_ms=BLOCK_MS, overlap_ms=OVERLAP_MS
        )(**wiring)
        runner[:] = [created]
        return created

    monkeypatch.setattr("voz.bootstrap.create_local_asr_runtime", fake_runtime)
    monkeypatch.setattr("voz.bootstrap.JobRunner", small_chunks)
    app = create_app(
        transcription_options=GetTranscriptionOptions(_Catalog(), _Runtime()),
        paths=_paths(tmp_path),
    )
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def _upload_and_start(client: httpx.Client, wav: Path) -> tuple[str, int]:
    project_id = client.post("/api/projects", json={"name": "Clase larga"}).json()["id"]
    uploaded = client.post(
        f"/api/projects/{project_id}/media",
        content=wav.read_bytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Voz-Filename": "clase.wav",
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    media = uploaded.json()
    (option,) = client.get("/api/transcription-options").json()["options"]
    started = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "media_asset_id": media["media_asset_id"],
            "option_id": option["option_id"],
            "language": "es",
        },
    )
    assert started.status_code == 201, started.text
    return started.json()["id"], media["duration_ms"]


def _wait_state(client: httpx.Client, job_id: str, state: str) -> dict[str, object]:
    deadline = time.monotonic() + 30
    job: dict[str, object] = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] == state:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job never reached {state}: {job}")


def _rows(tmp_path: Path, query: str) -> list[tuple[object, ...]]:
    database = _paths(tmp_path).data / DATABASE_FILENAME
    with sqlite3.connect(database) as connection:
        return connection.execute(query).fetchall()


def test_closing_the_app_mid_job_resumes_without_repeating_or_duplicating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = _long_wav(tmp_path / "clase.wav")
    runner: list[JobRunner] = []

    first = _SlowAsr(runner, park_at=PARK_AT_CALL)
    with _client(tmp_path, monkeypatch, first, runner) as client:
        job_id, duration_ms = _upload_and_start(client, wav)
        total = len(
            plan_audio_chunks(
                duration_ms, chunk_duration_ms=BLOCK_MS, overlap_ms=OVERLAP_MS
            )
        )
        assert total == BLOCKS
        assert first.parked.wait(30), "the job never reached the parked chunk"
    # Leaving the lifespan asked the runner to stop; the in-flight chunk was
    # committed and the job was left recoverable, not failed or completed.
    assert len(first.clips) == PARK_AT_CALL
    ((state, progress),) = _rows(
        tmp_path, f"select state, progress from transcription_jobs where id='{job_id}'"
    )
    assert state == "TRANSCRIBING"
    assert progress == pytest.approx(0.02 + 0.96 * PARK_AT_CALL / total)
    assert _rows(tmp_path, "select count(*) from transcription_checkpoints") == [
        (PARK_AT_CALL,)
    ]
    assert _rows(tmp_path, "select count(*) from segments") == [(0,)]

    second = _SlowAsr(runner)
    with _client(tmp_path, monkeypatch, second, runner) as client:
        done = _wait_state(client, job_id, "COMPLETED")
        assert done["progress"] == 1.0
        transcript_id = done["transcript_id"]
        segments = client.get(f"/api/transcripts/{transcript_id}/segments").json()[
            "segments"
        ]

    # Every chunk was transcribed exactly once across both runs.
    assert len(second.clips) == total - PARK_AT_CALL
    assert set(first.clips).isdisjoint(second.clips)
    assert len(set(first.clips) | set(second.clips)) == total
    # One segment per chunk, in timeline order, none repeated.
    texts = [item["text"] for item in segments]
    assert texts == [f"clip-{name}" for name in (*first.clips, *second.clips)]
    starts = [item["start_ms"] for item in segments]
    assert starts == sorted(set(starts))
    assert _rows(tmp_path, "select count(*) from transcription_checkpoints") == [
        (total,)
    ]
    assert _rows(tmp_path, "select count(*) from transcripts") == [(1,)]

    # A third opening of a finished job neither re-runs ASR nor adds segments.
    third = _SlowAsr(runner)
    with _client(tmp_path, monkeypatch, third, runner) as client:
        assert client.get(f"/api/jobs/{job_id}").json()["state"] == "COMPLETED"
        again = client.get(f"/api/transcripts/{transcript_id}/segments").json()
        assert [item["id"] for item in again["segments"]] == [
            item["id"] for item in segments
        ]
    assert third.clips == []
