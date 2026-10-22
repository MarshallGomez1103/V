"""A worker that outlives ``stop`` is never replaced and its resources stay open.

``stop`` reports whether the worker exited. While it is alive, ``start`` must not
spawn a second worker on the same queue, and the lifespan must not release the
engine, runtimes or database the worker still uses.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Protocol

import pytest
import test_job_runner_diarization as diar
import test_synthesis_runner as tsr
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from voz.application.job_runner import JobRunner
from voz.application.ports.speech_synthesis import SynthesisCancellationToken
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.application.synthesis.runner import SynthesisRunner
from voz.bootstrap import create_app

LONG = 10.0
SHORT = 0.05


class _Runner(Protocol):
    def start(self) -> None: ...
    def stop(self, timeout: float = ...) -> bool: ...


def _workers(name: str) -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == name and t.is_alive()]


class StuckAsr(diar.FakeAsr):
    """Chunk 2 ignores cancellation until ``release`` is set (a hung engine)."""

    def __init__(self, timeline: diar.Timeline) -> None:
        super().__init__(timeline)
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        self.calls += 1
        if self.calls == 2:
            self.started.set()
            assert self.release.wait(LONG)
        return super().transcribe(audio=audio, options=options)


def _assert_stuck_worker_is_kept(runner: _Runner, thread_name: str) -> None:
    (worker,) = _workers(thread_name)

    assert runner.stop(timeout=SHORT) is False  # still alive: not reported as stopped
    assert worker.is_alive()
    runner.start()  # must not launch a second worker on the same queue
    assert _workers(thread_name) == [worker]


def test_transcription_stop_reports_a_stuck_worker_and_start_adds_no_second(
    tmp_path: Path,
) -> None:
    fx = diar.world(tmp_path, diarization=None)
    asr = StuckAsr(fx.timeline)
    fx.asr = asr
    runner = fx.runner(None)
    runner.start()
    runner.enqueue(fx.job.id)
    assert asr.started.wait(5)

    try:
        _assert_stuck_worker_is_kept(runner, "voz-job-runner")
    finally:
        asr.release.set()

    assert runner.stop(timeout=5) is True
    assert _workers("voz-job-runner") == []


def test_transcription_stop_of_an_idle_worker_is_clean_and_restartable(
    tmp_path: Path,
) -> None:
    runner = diar.world(tmp_path, diarization=None).runner(None)
    assert runner.stop() is True  # never started

    runner.start()
    assert runner.stop(timeout=5) is True
    assert _workers("voz-job-runner") == []

    runner.start()  # a clean stop allows a new worker
    assert len(_workers("voz-job-runner")) == 1
    assert runner.stop(timeout=5) is True


def test_synthesis_stop_reports_a_stuck_worker_and_start_adds_no_second(
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def hang(call: int, _token: SynthesisCancellationToken | None) -> None:
        if call == 2:
            started.set()
            assert release.wait(LONG)

    fixture = tsr.harness(tmp_path, tsr.ScriptedTts(hook=hang))
    runner: SynthesisRunner = fixture.runner
    runner.start()
    runner.enqueue(fixture.job.id)
    assert started.wait(5)

    try:
        _assert_stuck_worker_is_kept(runner, "voz-synthesis-runner")
    finally:
        release.set()

    assert runner.stop(timeout=5) is True
    assert _workers("voz-synthesis-runner") == []
    fixture.engine.dispose()


def test_synthesis_stop_of_an_idle_worker_is_clean_and_restartable(
    tmp_path: Path,
) -> None:
    fixture = tsr.harness(tmp_path)
    runner = fixture.runner
    assert runner.stop() is True  # never started

    runner.start()
    assert runner.stop(timeout=5) is True
    runner.start()
    assert len(_workers("voz-synthesis-runner")) == 1
    assert runner.stop(timeout=5) is True
    fixture.engine.dispose()


def _run_lifespan(
    monkeypatch: pytest.MonkeyPatch, join: Callable[[JobRunner, float], bool]
) -> list[Engine]:
    disposed: list[Engine] = []
    real_dispose = Engine.dispose

    def spy(self: Engine, close: bool = True) -> None:
        disposed.append(self)
        real_dispose(self, close)

    monkeypatch.setattr(Engine, "dispose", spy)
    monkeypatch.setattr(JobRunner, "join", join)
    with TestClient(create_app()):
        pass
    return disposed


def test_lifespan_keeps_shared_resources_while_a_worker_is_still_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_join = JobRunner.join

    def join_reports_alive(self: JobRunner, timeout: float) -> bool:
        real_join(self, timeout)  # really stop it, but report it as still alive
        return False

    assert _run_lifespan(monkeypatch, join_reports_alive) == []


def test_lifespan_releases_shared_resources_after_a_clean_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed = _run_lifespan(monkeypatch, JobRunner.join)

    assert len(disposed) == 1


def test_lifespan_signals_both_workers_before_waiting_on_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def spy(cls: type, name: str, label: str) -> None:
        real = getattr(cls, name)

        def wrapper(self: object, *args: float) -> object:
            calls.append(f"{label}.{name}")
            return real(self, *args)

        monkeypatch.setattr(cls, name, wrapper)

    for name in ("request_stop", "join"):
        spy(JobRunner, name, "transcription")
        spy(SynthesisRunner, name, "synthesis")
    with TestClient(create_app()):
        pass

    assert calls == [
        "transcription.request_stop",
        "synthesis.request_stop",
        "transcription.join",
        "synthesis.join",
    ]


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_worker_that_died_leaves_no_sentinel_to_kill_the_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def die(self: object, job_id: object) -> None:
        raise SystemExit  # BaseException: the loop's `except Exception` misses it

    monkeypatch.setattr(SynthesisRunner, "run_job", die)
    fixture = tsr.harness(tmp_path)
    runner = fixture.runner
    runner.start()
    (worker,) = _workers("voz-synthesis-runner")
    runner.enqueue(fixture.job.id)
    worker.join(5)
    assert not worker.is_alive()

    assert runner.stop() is True
    runner.start()
    (restarted,) = _workers("voz-synthesis-runner")
    restarted.join(0.2)  # a leftover sentinel would end it at once

    assert restarted.is_alive()
    assert runner.stop(timeout=5) is True
    fixture.engine.dispose()
