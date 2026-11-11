"""Close VOZ in the middle of a project queue, reopen, and finish it in order.

Real HTTP app, real runner thread, real ffmpeg, slow fake ASR over many chunks.
Three recordings are queued. The first app exits its lifespan while the second
one is mid-way; the second app opens the same XDG directories and must finish
the second recording from its checkpoints and run the third, without repeating
the finished one and without duplicating segments.
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
BLOCKS = 4  # 2 s of audio per recording, one distinct 500 ms block per chunk
FILES = 3
OVERLAP_MS = 100
PARK_AT_CALL = BLOCKS + 2  # closed on the second chunk of the second recording

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


def _wav(target: Path, recording: int) -> Path:
    """16 kHz mono PCM, every 500 ms block of every recording a different level."""
    block = SAMPLE_RATE * BLOCK_MS // 1_000
    with wave.open(str(target), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for index in range(BLOCKS):
            level = 500 * (recording * BLOCKS + index + 1)
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


def _rows(tmp_path: Path, query: str) -> list[tuple[object, ...]]:
    database = _paths(tmp_path).data / DATABASE_FILENAME
    with sqlite3.connect(database) as connection:
        return connection.execute(query).fetchall()


def _upload_all(client: httpx.Client, wavs: list[Path]) -> str:
    project_id = client.post("/api/projects", json={"name": "Curso"}).json()["id"]
    for wav in wavs:
        uploaded = client.post(
            f"/api/projects/{project_id}/media",
            content=wav.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Voz-Filename": wav.name,
            },
        )
        assert uploaded.status_code == 201, uploaded.text
    return project_id


def _start_queue(client: httpx.Client, project_id: str) -> dict[str, Any]:
    (option,) = client.get("/api/transcription-options").json()["options"]
    started = client.post(
        f"/api/projects/{project_id}/transcription-queue",
        json={"option_id": option["option_id"], "language": "es"},
    )
    assert started.status_code == 201, started.text
    return started.json()


def _wait_finished(client: httpx.Client, project_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    queue: dict[str, Any] = {}
    while time.monotonic() < deadline:
        queue = client.get(f"/api/projects/{project_id}/transcription-queue").json()[
            "queue"
        ]
        if queue["state"] == "finished":
            return queue
        time.sleep(0.05)
    raise AssertionError(f"the queue never finished: {queue}")


def _texts(client: httpx.Client, item: dict[str, Any]) -> list[str]:
    segments = client.get(f"/api/transcripts/{item['transcript_id']}/segments").json()
    return [segment["text"] for segment in segments["segments"]]


def test_queue_resumes_after_restart_without_repeating_finished_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wavs = [_wav(tmp_path / f"clase-{i}.wav", i) for i in range(FILES)]
    runner: list[JobRunner] = []

    first = _SlowAsr(runner, park_at=PARK_AT_CALL)
    with _client(tmp_path, monkeypatch, first, runner) as client:
        project_id = _upload_all(client, wavs)
        queue = _start_queue(client, project_id)
        assert [item["filename"] for item in queue["items"]] == [w.name for w in wavs]
        assert queue["counts"]["total"] == FILES
        assert first.parked.wait(30), "the queue never reached the parked chunk"
    # Closing the app left the second recording mid-way and the third untouched.
    assert len(first.clips) == PARK_AT_CALL
    states = _rows(
        tmp_path,
        "select j.state from transcription_queue_items i "
        "join transcription_jobs j on j.id = i.job_id order by i.position",
    )
    assert states == [("COMPLETED",), ("TRANSCRIBING",), ("QUEUED",)]
    assert _rows(tmp_path, "select count(*) from transcription_checkpoints") == [
        (PARK_AT_CALL,)
    ]

    second = _SlowAsr(runner)
    with _client(tmp_path, monkeypatch, second, runner) as client:
        queue = _wait_finished(client, project_id)
        texts = [_texts(client, item) for item in queue["items"]]

    assert [item["status"] for item in queue["items"]] == ["done"] * FILES
    assert queue["progress"] == 1.0
    assert queue["counts"]["done"] == FILES
    # Every chunk of every recording was decoded exactly once across both runs.
    total = FILES * BLOCKS
    assert len(second.clips) == total - PARK_AT_CALL
    assert set(first.clips).isdisjoint(second.clips)
    assert len(set(first.clips) | set(second.clips)) == total
    # Each recording keeps its own chunks, in order, none duplicated.
    clips = [f"clip-{name}" for name in (*first.clips, *second.clips)]
    assert texts == [clips[i : i + BLOCKS] for i in range(0, total, BLOCKS)]
    assert _rows(tmp_path, "select count(*) from transcripts") == [(FILES,)]

    # Reopening a finished queue runs nothing.
    third = _SlowAsr(runner)
    with _client(tmp_path, monkeypatch, third, runner) as client:
        again = client.get(f"/api/projects/{project_id}/transcription-queue").json()
        assert again["queue"]["state"] == "finished"
    assert third.clips == []
