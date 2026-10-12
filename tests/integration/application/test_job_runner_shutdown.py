"""Shutdown reaches the ASR engine and the preprocessing (V0-09e, real SQLite).

Ctrl+C / ``POST /api/shutdown`` call ``JobRunner.stop``; the in-flight chunk or
normalization must see it through its cancellation token, so the worker exits
in seconds. Shutdown is not a user cancel: the job stays in its processable
state and ``recover`` resumes it on the next start without redoing confirmed
chunks.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import BinaryIO

import test_job_runner_diarization as diar

from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.domain.entities.transcription_job import TranscriptionJobState as S
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)

LONG = 10.0  # a real chunk may last minutes; the test fails long before


def _wait_for_cancel(token: object) -> bool:
    deadline = time.monotonic() + LONG
    while time.monotonic() < deadline:
        if token is not None and token.is_cancelled():  # type: ignore[attr-defined]
            return True
        time.sleep(0.005)
    return False


class BlockingAsr(diar.FakeAsr):
    """Chunk ``block_at`` runs until its token is cancelled, like a long decode."""

    def __init__(self, timeline: diar.Timeline, *, block_at: int | None) -> None:
        super().__init__(timeline)
        self.block_at = block_at
        self.calls = 0
        self.started = threading.Event()

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        self.calls += 1
        if self.calls == self.block_at:
            self.started.set()
            if _wait_for_cancel(cancellation):
                raise TranscriptionError(TranscriptionFailureCode.CANCELLED, "stop")
        return super().transcribe(audio=audio, options=options)


def _stop_while(started: threading.Event, runner: object) -> float:
    assert started.wait(5)
    worker = runner._thread  # type: ignore[attr-defined]
    t0 = time.monotonic()
    runner.stop(timeout=5)  # type: ignore[attr-defined]
    elapsed = time.monotonic() - t0
    assert worker is not None and not worker.is_alive()
    return elapsed


def test_shutdown_stops_the_asr_chunk_and_recover_resumes(tmp_path: Path) -> None:
    fx = diar.world(tmp_path, diarization=None)
    asr = BlockingAsr(fx.timeline, block_at=2)
    fx.asr = asr
    runner = fx.runner(None)
    runner.start()
    runner.enqueue(fx.job.id)

    assert _stop_while(asr.started, runner) < 2.0  # not the whole chunk

    stopped = fx.persisted()
    assert stopped.state is S.TRANSCRIBING  # resumable, never CANCELLED
    store = SqliteTranscriptionCheckpointStore(fx.engine)
    assert [c.chunk_index for c in store.list_for_job(fx.job.id)] == [0]

    asr.block_at = None
    asr.calls = 0
    restarted = fx.runner(None)
    assert restarted.recover() == (fx.job.id,)
    restarted.start()
    assert restarted.wait_idle(10)
    restarted.stop()

    assert fx.persisted().state is S.COMPLETED
    total = len(store.list_for_job(fx.job.id))
    assert total > 1
    assert asr.calls == total - 1  # confirmed chunk 0 was not transcribed again


def test_user_cancel_during_a_chunk_still_ends_cancelled(tmp_path: Path) -> None:
    fx = diar.world(tmp_path, diarization=None)
    asr = BlockingAsr(fx.timeline, block_at=2)
    fx.asr = asr
    runner = fx.runner(None)
    runner.start()
    runner.enqueue(fx.job.id)
    assert asr.started.wait(5)

    runner.cancel(fx.job.id)
    assert runner.wait_idle(5)
    runner.stop()

    assert fx.persisted().state is S.CANCELLED


class BlockingPreparer:
    """Normalization that runs until its token is cancelled, then restores it."""

    def __init__(self, source: Path, target: Path) -> None:
        self.source = source
        self.target = target
        self.block = True
        self.started = threading.Event()

    def prepare(
        self,
        *,
        project_id: object,
        media_asset_id: object,
        cancellation: MediaNormalizationCancellationToken | None = None,
        on_progress: object = None,
    ) -> None:
        if self.block:
            self.started.set()
            if _wait_for_cancel(cancellation):
                raise MediaNormalizationError(
                    MediaNormalizationFailureCode.CANCELLED, "stop"
                )
        shutil.copyfile(self.source, self.target)


def test_shutdown_stops_preprocessing_and_recover_resumes(tmp_path: Path) -> None:
    fx = diar.world(tmp_path, diarization=None)
    derivative = next((fx.root / "projects").rglob("*.inference.wav"))
    kept = tmp_path / "original.wav"
    shutil.move(derivative, kept)
    preparer = BlockingPreparer(kept, derivative)
    runner = fx.runner(None)
    runner.audio_preparer = preparer
    runner.start()
    runner.enqueue(fx.job.id)

    assert _stop_while(preparer.started, runner) < 2.0

    assert fx.persisted().state is S.PREPROCESSING  # resumable, never CANCELLED

    preparer.block = False
    restarted = fx.runner(None)
    restarted.audio_preparer = preparer
    assert restarted.recover() == (fx.job.id,)
    restarted.start()
    assert restarted.wait_idle(10)
    restarted.stop()
    assert fx.persisted().state is S.COMPLETED
