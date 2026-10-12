"""SynthesisRunner over real SQLite, real WAV storage and the fake TTS (V3-03)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest
import test_job_runner as tjr
from sqlalchemy import Engine

from voz.application.compute_slot import ComputeKind, ComputeSlot, SlotUser
from voz.application.ports.speech_synthesis import (
    PcmAudio,
    SynthesisCancellationToken,
    SynthesisError,
    SynthesisFailureCode,
    SynthesisProgressCallback,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.application.synthesis import CancelSynthesisJob
from voz.application.synthesis.runner import SynthesisRunner
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.application.text_chunking import (
    CHUNK_SILENCE_MS,
    PARAGRAPH_SILENCE_MS,
    plan_text_chunks,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import SynthesisRequest
from voz.domain.entities.transcription_job import TranscriptionJobState
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.schema import metadata
from voz.infrastructure.persistence.synthesis import (
    SqliteSynthesisJobRepository,
    SqliteSynthesizedAudioRepository,
)
from voz.infrastructure.synthesis_storage import FileSystemSynthesisStorage
from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
    fake_tts_descriptor,
)

BASE = datetime(2026, 10, 12, 9, tzinfo=UTC)
MAX_CHARS = 40
TEXT = (
    "Hola mundo. Esta es una prueba corta del motor.\n\n"
    "Segundo párrafo con algo más de texto. Y una frase final."
)
LONG = 10.0
Hook = Callable[[int, SynthesisCancellationToken | None], None]


class ScriptedTts(FakeSpeechSynthesisProvider):
    """Fake engine with a hook before each chunk and an optional typed failure."""

    def __init__(self, *, hook: Hook | None = None, fail_on: int | None = None):
        super().__init__(max_chunk_chars=MAX_CHARS)
        self.hook = hook
        self.fail_on = fail_on
        self.calls = 0
        self.frames: list[int] = []

    def synthesize(
        self,
        chunk_text: str,
        *,
        model: ModelDescriptor,
        voice_id: str,
        speed: float = 1.0,
        cancellation: SynthesisCancellationToken | None = None,
        on_progress: SynthesisProgressCallback | None = None,
    ) -> PcmAudio:
        self.calls += 1
        if self.hook is not None:
            self.hook(self.calls, cancellation)
        if self.fail_on == self.calls:
            raise SynthesisError(
                SynthesisFailureCode.SYNTHESIS_FAILED, "/private/engine crashed"
            )
        audio = super().synthesize(
            chunk_text,
            model=model,
            voice_id=voice_id,
            speed=speed,
            cancellation=cancellation,
            on_progress=on_progress,
        )
        self.frames.append(audio.frame_count)
        return audio


class Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                fake_tts_descriptor(), InstallationStatus.REGISTERED, True
            ),
        )


class EmptyCatalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return ()


@dataclass(slots=True)
class Harness:
    engine: Engine
    storage: FileSystemSynthesisStorage
    job: SynthesisJob
    provider: ScriptedTts
    runner: SynthesisRunner

    @property
    def jobs(self) -> SqliteSynthesisJobRepository:
        return SqliteSynthesisJobRepository(self.engine)

    def persisted(self) -> SynthesisJob:
        job = self.jobs.get(self.job.id)
        assert job is not None
        return job

    def new_runner(
        self, provider: ScriptedTts, slot: ComputeSlot | None = None
    ) -> SynthesisRunner:
        ticks = iter(range(1, 10_000))
        return SynthesisRunner(
            jobs=self.jobs,
            audio=SqliteSynthesizedAudioRepository(self.engine),
            storage=self.storage,
            providers=SynthesisProviderRegistry([provider]),
            catalog=Catalog(),
            compute_slot=slot or ComputeSlot(),
            clock=lambda: BASE + timedelta(seconds=next(ticks)),
        )


CHUNKS = plan_text_chunks(TEXT, max_chars=MAX_CHARS)


def harness(
    tmp_path: Path, provider: ScriptedTts | None = None, slot: ComputeSlot | None = None
) -> Harness:
    engine = create_sqlite_engine((tmp_path / "tts.db").absolute())
    metadata.create_all(engine)
    job = SynthesisJob.create(
        job_id=uuid4(),
        request=SynthesisRequest(
            text=TEXT,
            provider_id=FAKE_TTS_PROVIDER_ID,
            model_id="tone",
            voice_id="tone-low",
        ),
        chunks_total=len(CHUNKS),
        now=BASE,
    )
    SqliteSynthesisJobRepository(engine).add(job)
    tts = provider or ScriptedTts()
    fixture = Harness(
        engine,
        FileSystemSynthesisStorage(tmp_path / "data"),
        job,
        tts,
        None,  # type: ignore[arg-type]
    )
    fixture.runner = fixture.new_runner(tts, slot)
    return fixture


def _wait_for(condition: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + LONG
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


def _assert_completed_wav(fixture: Harness, provider: ScriptedTts) -> None:
    stored = SqliteSynthesizedAudioRepository(fixture.engine).get_by_job(fixture.job.id)
    assert stored is not None
    assert stored.chunk_count == len(CHUNKS)
    gaps = [
        PARAGRAPH_SILENCE_MS if "\n\n" in TEXT[a.end : b.start] else CHUNK_SILENCE_MS
        for a, b in pairwise(CHUNKS)
    ]
    assert PARAGRAPH_SILENCE_MS in gaps  # the text crosses a paragraph
    with fixture.storage.open_for_reading(stored.relative_path) as raw:
        source: BinaryIO = raw
        with wave.open(source, "rb") as audio:
            assert (audio.getnchannels(), audio.getsampwidth()) == (1, 2)
            assert audio.getframerate() == 16_000 == stored.sample_rate
            silence = sum(gap * 16 for gap in gaps)  # 16 frames per ms
            assert audio.getnframes() == sum(provider.frames[-len(CHUNKS) :]) + silence


def test_job_renders_every_chunk_and_completes_with_a_valid_wav(
    tmp_path: Path,
) -> None:
    seen: list[int] = []
    fixture: Harness

    def record(call: int, _token: SynthesisCancellationToken | None) -> None:
        seen.append(fixture.persisted().chunks_done)

    fixture = harness(tmp_path, ScriptedTts(hook=record))
    assert len(CHUNKS) >= 3

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is SynthesisJobState.COMPLETED
    assert fixture.persisted() == finished
    assert finished.chunks_done == finished.chunks_total == len(CHUNKS)
    assert seen == list(range(len(CHUNKS)))  # progress persisted chunk by chunk
    _assert_completed_wav(fixture, fixture.provider)
    fixture.engine.dispose()


@pytest.mark.parametrize("via_use_case", [False, True])
def test_cancel_during_rendering_ends_cancelled_without_audio(
    tmp_path: Path, via_use_case: bool
) -> None:
    fixture: Harness

    def cancel_on_second(call: int, _token: SynthesisCancellationToken | None) -> None:
        if call != 2:
            return
        if via_use_case:  # V2-05 wiring: the use case signals the runner
            CancelSynthesisJob(
                fixture.jobs, interrupt=fixture.runner.interrupt
            ).execute(fixture.job.id)
        else:
            fixture.runner.cancel(fixture.job.id)

    fixture = harness(tmp_path, ScriptedTts(hook=cancel_on_second))
    fixture.runner.start()
    fixture.runner.enqueue(fixture.job.id)
    assert fixture.runner.wait_idle(LONG)
    fixture.runner.stop()

    persisted = fixture.persisted()
    assert persisted.state is SynthesisJobState.CANCELLED
    assert persisted.chunks_done == 1
    assert fixture.provider.calls == 2
    assert (
        SqliteSynthesizedAudioRepository(fixture.engine).get_by_job(fixture.job.id)
        is None
    )
    fixture.engine.dispose()


def test_shutdown_leaves_job_resumable_and_recover_renders_it_again(
    tmp_path: Path,
) -> None:
    started = threading.Event()
    reached: list[bool] = []

    def block_second(call: int, token: SynthesisCancellationToken | None) -> None:
        if call == 2:
            started.set()
            reached.append(
                _wait_for(lambda: token is not None and token.is_cancelled())
            )

    fixture = harness(tmp_path, ScriptedTts(hook=block_second))
    fixture.runner.start()
    fixture.runner.enqueue(fixture.job.id)
    assert started.wait(LONG)
    fixture.runner.stop(LONG)

    assert reached == [True]  # shutdown reached the in-flight chunk
    stopped = fixture.persisted()
    assert stopped.state is SynthesisJobState.RUNNING
    assert stopped.chunks_done == 1
    assert (
        SqliteSynthesizedAudioRepository(fixture.engine).get_by_job(fixture.job.id)
        is None
    )

    fresh = ScriptedTts()
    runner = fixture.new_runner(fresh)
    assert runner.recover() == (fixture.job.id,)
    runner.start()
    assert runner.wait_idle(LONG)
    runner.stop()

    finished = fixture.persisted()
    assert finished.state is SynthesisJobState.COMPLETED
    assert fresh.calls == len(CHUNKS)  # no per-chunk checkpoints: from zero
    _assert_completed_wav(fixture, fresh)
    fixture.engine.dispose()


def test_provider_failure_persists_its_stable_code(tmp_path: Path) -> None:
    fixture = harness(tmp_path, ScriptedTts(fail_on=2))

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is SynthesisJobState.FAILED
    assert finished.error_code == "synthesis_failed"
    assert fixture.persisted() == finished
    assert finished.chunks_done == 1
    fixture.engine.dispose()


def test_unknown_model_fails_with_typed_code(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    fixture.runner.catalog = EmptyCatalog()

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is SynthesisJobState.FAILED
    assert finished.error_code == "synthesis_model_unknown"
    assert fixture.provider.calls == 0
    fixture.engine.dispose()


def test_job_waiting_for_the_slot_can_be_cancelled_or_stopped(
    tmp_path: Path,
) -> None:
    slot = ComputeSlot()
    release = threading.Event()
    held = threading.Event()

    def busy() -> None:
        with slot.hold(ComputeKind.TRANSCRIPTION, uuid4()):
            held.set()
            release.wait(LONG)

    blocker = threading.Thread(target=busy)
    blocker.start()
    assert held.wait(LONG)
    fixture = harness(tmp_path, slot=slot)
    second = SynthesisJob.create(
        job_id=uuid4(), request=fixture.job.request, chunks_total=len(CHUNKS), now=BASE
    )
    fixture.jobs.add(second)
    fixture.runner.start()
    fixture.runner.enqueue(fixture.job.id)
    fixture.runner.enqueue(second.id)
    assert _wait_for(
        lambda: slot.waiting() == (SlotUser(ComputeKind.SYNTHESIS, fixture.job.id),)
    )

    cancelled = fixture.runner.cancel(fixture.job.id)
    assert cancelled.state is SynthesisJobState.CANCELLED  # still QUEUED: at once
    assert _wait_for(
        lambda: slot.waiting() == (SlotUser(ComputeKind.SYNTHESIS, second.id),)
    )
    fixture.runner.stop(LONG)
    release.set()
    blocker.join(LONG)

    assert fixture.persisted().state is SynthesisJobState.CANCELLED
    stored = fixture.jobs.get(second.id)
    assert stored is not None and stored.state is SynthesisJobState.QUEUED
    assert fixture.provider.calls == 0
    assert slot.holder() is None and slot.waiting() == ()
    fixture.engine.dispose()


def test_transcription_and_synthesis_never_run_at_the_same_time(
    tmp_path: Path,
) -> None:
    slot = ComputeSlot()
    active: list[str] = []
    overlaps: list[tuple[str, ...]] = []
    holders: list[SlotUser | None] = []
    guard = threading.Lock()

    def enter(kind: str) -> None:
        with guard:
            active.append(kind)
            if len(active) > 1:
                overlaps.append(tuple(active))
        holders.append(slot.holder())
        time.sleep(0.03)
        with guard:
            active.remove(kind)

    class SlowAsr(tjr.Provider):
        def transcribe(
            self,
            *,
            audio: BinaryIO,
            options: TranscriptionOptions,
            cancellation: TranscriptionCancellationToken | None = None,
        ) -> TranscriptionResult:
            enter("asr")
            return super().transcribe(
                audio=audio, options=options, cancellation=cancellation
            )

    asr = tjr.harness(tmp_path / "asr", provider=SlowAsr())
    asr.runner.compute_slot = slot
    tts = harness(
        tmp_path, ScriptedTts(hook=lambda call, token: enter("tts")), slot=slot
    )
    asr.runner.start()
    tts.runner.start()
    asr.runner.enqueue(asr.job.id)
    assert _wait_for(lambda: slot.holder() is not None)
    tts.runner.enqueue(tts.job.id)
    assert asr.runner.wait_idle(LONG) and tts.runner.wait_idle(LONG)
    asr.runner.stop()
    tts.runner.stop()

    assert asr.persisted().state is TranscriptionJobState.COMPLETED
    assert tts.persisted().state is SynthesisJobState.COMPLETED
    assert overlaps == []
    assert {h.kind for h in holders if h is not None} == {
        ComputeKind.TRANSCRIPTION,
        ComputeKind.SYNTHESIS,
    }
    assert None not in holders
    asr.engine.dispose()
    tts.engine.dispose()


def test_transcription_waiting_for_the_slot_is_cancelled_without_running(
    tmp_path: Path,
) -> None:
    slot = ComputeSlot()
    release = threading.Event()
    held = threading.Event()

    def busy() -> None:
        with slot.hold(ComputeKind.SYNTHESIS, uuid4()):
            held.set()
            release.wait(LONG)

    blocker = threading.Thread(target=busy)
    blocker.start()
    assert held.wait(LONG)
    asr = tjr.harness(tmp_path)
    asr.runner.compute_slot = slot
    asr.runner.start()
    asr.runner.enqueue(asr.job.id)
    assert _wait_for(
        lambda: slot.waiting() == (SlotUser(ComputeKind.TRANSCRIPTION, asr.job.id),)
    )

    asr.runner.cancel(asr.job.id)
    assert _wait_for(lambda: slot.waiting() == ())
    assert asr.runner.wait_idle(LONG)
    asr.runner.stop()
    release.set()
    blocker.join(LONG)

    assert asr.persisted().state is TranscriptionJobState.CANCELLED
    assert asr.provider.calls == 0
    asr.engine.dispose()


def test_transcription_waiting_for_the_slot_stays_queued_on_shutdown(
    tmp_path: Path,
) -> None:
    slot = ComputeSlot()
    release = threading.Event()
    held = threading.Event()

    def busy() -> None:
        with slot.hold(ComputeKind.SYNTHESIS, uuid4()):
            held.set()
            release.wait(LONG)

    blocker = threading.Thread(target=busy)
    blocker.start()
    assert held.wait(LONG)
    asr = tjr.harness(tmp_path)
    asr.runner.compute_slot = slot
    asr.runner.start()
    asr.runner.enqueue(asr.job.id)
    assert _wait_for(lambda: len(slot.waiting()) == 1)

    asr.runner.stop(LONG)
    release.set()
    blocker.join(LONG)

    assert asr.persisted().state is TranscriptionJobState.QUEUED
    assert asr.provider.calls == 0
    assert slot.waiting() == ()
    asr.engine.dispose()
