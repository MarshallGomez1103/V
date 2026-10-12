"""Single-worker speech synthesis pipeline sharing the compute slot (V3-03).

Mirrors ``JobRunner``: one daemon thread drains a FIFO of job identities. Per
job it takes the process-wide ``ComputeSlot``, re-plans the text chunks, renders
them one by one with the registered engine (progress per chunk is persisted),
stores one WAV and completes the job. Cancel wins (V0-09a): once CANCELLING is
persisted only CANCELLED may follow it. Shutdown leaves the job resumable and
``recover`` renders it again on the next start.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from itertools import pairwise
from uuid import UUID

from voz.application.compute_slot import ComputeKind, ComputeSlot, SlotWaitCancelled
from voz.application.ports.speech_synthesis import PcmAudio
from voz.application.ports.synthesis_audio_storage import SynthesisAudioStorage
from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.application.synthesis.cancel_synthesis_job import CancelSynthesisJob
from voz.application.synthesis.create_synthesis_job import SynthesisModelCatalog
from voz.application.synthesis.errors import SynthesisJobFailureCode
from voz.application.synthesis_provider_registry import (
    SynthesisProviderNotFoundError,
    SynthesisProviderRegistry,
)
from voz.application.text_chunking import plan_text_chunks, silence_gap_ms
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState

_LOG = logging.getLogger(__name__)

_CANCEL_PATH = frozenset({SynthesisJobState.CANCELLING, SynthesisJobState.CANCELLED})


class SynthesisRunnerFailureCode(StrEnum):
    """Runner-level failures; engines and storage carry their own codes."""

    INTERNAL = "synthesis_internal_error"
    CRASHED = "synthesis_runner_crashed"


class _Stopping(Exception):
    """Leave the current job resumable: the server is shutting down."""


class _CodedFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _AnyEventToken:
    events: tuple[threading.Event, ...]

    def is_cancelled(self) -> bool:
        return any(event.is_set() for event in self.events)


@dataclass(slots=True)
class SynthesisRunner:
    """One daemon worker rendering synthesis jobs in FIFO order.

    # ponytail: un worker; el slot de cómputo ya serializa todo el trabajo pesado.
    """

    jobs: SynthesisJobRepository
    audio: SynthesizedAudioRepository
    storage: SynthesisAudioStorage
    providers: SynthesisProviderRegistry
    catalog: SynthesisModelCatalog
    compute_slot: ComputeSlot = field(default_factory=ComputeSlot)
    """Share the transcription runner's slot so only one heavy job runs."""
    release_other_runtimes: Callable[[], None] = lambda: None
    """Free a resident ASR runtime before rendering (ADR-0010 point 4)."""
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _queue: queue.Queue[UUID | None] = field(
        default_factory=queue.Queue[UUID | None], repr=False
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _stopping: threading.Event = field(default_factory=threading.Event, repr=False)
    _current: UUID | None = field(default=None, repr=False)
    _queued: set[UUID] = field(default_factory=set[UUID], repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._loop, name="voz-synthesis-runner", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the worker to leave its job resumable and wait for it to exit."""
        self._stopping.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def enqueue(self, job_id: UUID) -> None:
        """Queue a job once; a job already waiting or running is not duplicated."""
        with self._lock:
            if job_id in self._queued or job_id == self._current:
                return
            self._queued.add(job_id)
        self._queue.put(job_id)

    def recover(self) -> tuple[UUID, ...]:
        """Re-enqueue every non-terminal job, oldest first."""
        recovered = tuple(job.id for job in self.jobs.list_recoverable())
        for job_id in recovered:
            self.enqueue(job_id)
        return recovered

    def wait_idle(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                idle = self._queue.empty() and self._current is None
            if idle:
                return True
            time.sleep(0.01)
        return False

    # -- cancellation --------------------------------------------------------

    def cancel(self, job_id: UUID) -> SynthesisJob:
        """``CancelSynthesisJob`` under the runner lock: no worker write between
        its read and its save. Raises ``SynthesisJobError`` like the use case."""
        with self._lock:
            job = CancelSynthesisJob(self.jobs, clock=self.clock).execute(job_id)
            # Also a QUEUED one: it may be ours, waiting for the compute slot.
            self._interrupt_locked(job_id)
            return job

    def interrupt(self, job_id: UUID) -> None:
        """Make the worker stop ``job_id`` if it is the one running (or waiting)."""
        with self._lock:
            self._interrupt_locked(job_id)

    def _interrupt_locked(self, job_id: UUID) -> None:
        if self._current == job_id:
            self._cancel.set()

    # -- execution -----------------------------------------------------------

    def run_job(self, job_id: UUID) -> SynthesisJob | None:
        """Process one job synchronously; the worker thread calls this per item."""
        with self._lock:
            self._queued.discard(job_id)
            job = self.jobs.get(job_id)
            if job is None or job.state.is_terminal:
                return job
            self._current = job_id
            self._cancel.clear()
        stop = _AnyEventToken((self._cancel, self._stopping))
        try:
            try:
                with self.compute_slot.hold(
                    ComputeKind.SYNTHESIS, job_id, cancellation=stop
                ):
                    return self._execute(job_id, stop)
            except SlotWaitCancelled:
                return self._execute(job_id, stop)  # finishes without heavy work
        finally:
            with self._lock:
                self._current = None

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self.run_job(item)
            except Exception:
                # Same policy as JobRunner: a persistence outage must not kill
                # the only worker; try once to leave the job FAILED.
                _LOG.exception("Synthesis runner crashed on job %s", item)
                if item is not None:
                    self._mark_crashed(item)
            finally:
                self._queue.task_done()

    def _mark_crashed(self, job_id: UUID) -> None:
        try:
            job = self.jobs.get(job_id)
            if job is not None and not job.state.is_terminal:
                self._fail(job, SynthesisRunnerFailureCode.CRASHED.value)
        except Exception:
            _LOG.exception("Could not mark synthesis job %s as failed", job_id)

    def _execute(self, job_id: UUID, stop: _AnyEventToken) -> SynthesisJob | None:
        # Re-read: the job may have been cancelled while it waited for the slot.
        job = self.jobs.get(job_id)
        if job is None or job.state.is_terminal:
            return job
        try:
            self._check(stop)
            if job.state is SynthesisJobState.CANCELLING:
                return self._settle(job)
            if (
                job.state is not SynthesisJobState.PERSISTING
                or self.audio.get_by_job(job.id) is None
            ):
                # Also a PERSISTING job whose run died before storing its row.
                job = self._render(job, stop)
            job = self._save(self._step(job, SynthesisJobState.COMPLETED))
        except _Stopping:
            pass
        except Exception as error:
            latest = self._latest(job)
            interrupted = self._cancel.is_set() or self._stopping.is_set()
            if not interrupted and latest.state is not SynthesisJobState.CANCELLING:
                code = _error_code(error)
                _LOG.error("Synthesis job %s failed (%s)", job.id, code, exc_info=error)
                return self._fail(latest, code)
        return self._settle(job)

    def _settle(self, job: SynthesisJob) -> SynthesisJob:
        """Final word after a stop: cancel wins, else the job stays resumable."""
        persisted = self.jobs.get(job.id) or job
        if persisted.state.is_terminal:
            return persisted
        if self._cancel.is_set() or persisted.state is SynthesisJobState.CANCELLING:
            return self._finish_cancelled(persisted)
        _LOG.info("Synthesis job %s left resumable on shutdown", job.id)
        return persisted

    def _render(self, job: SynthesisJob, stop: _AnyEventToken) -> SynthesisJob:
        """Render every chunk and store the WAV; returns the job in PERSISTING."""
        request = job.request
        try:
            provider = self.providers.get(request.provider_id)
        except SynthesisProviderNotFoundError:
            raise _CodedFailure(
                SynthesisJobFailureCode.PROVIDER_NOT_FOUND.value
            ) from None
        model = self._model(request.provider_id, request.model_id)
        if job.state is SynthesisJobState.QUEUED:
            job = self._save(self._step(job, SynthesisJobState.RUNNING))
        self.release_other_runtimes()
        chunks = plan_text_chunks(
            request.text, max_chars=provider.describe().max_chunk_chars
        )
        # ponytail: a resumed job renders again from its first chunk (no
        # per-chunk audio checkpoints); progress keeps its high-water mark.
        # Ceiling: long texts lose the work done before a restart.
        rendered: list[PcmAudio] = []
        for index, chunk in enumerate(chunks):
            self._check(stop)
            rendered.append(
                provider.synthesize(
                    chunk.text,
                    model=model,
                    voice_id=request.voice_id,
                    speed=request.speed,
                    cancellation=stop,
                )
            )
            # Engine and job may disagree on the count if the engine's chunk
            # cap changed since creation: scale onto the job's total.
            done = (index + 1) * job.chunks_total // len(chunks)
            if done > job.chunks_done:
                job = self._save(job.with_chunks_done(done, at=self._not_before(job)))
            if job.state in _CANCEL_PATH:
                raise _Stopping  # a cancel won the write; ``_settle`` finishes it
        self._check(stop)
        gaps = [
            silence_gap_ms(request.text[before.end : after.start])
            for before, after in pairwise(chunks)
        ]
        if job.state is not SynthesisJobState.PERSISTING:
            job = self._save(self._step(job, SynthesisJobState.PERSISTING))
        if job.state is not SynthesisJobState.PERSISTING:
            raise _Stopping
        # No row yet, so any audio.wav here is left over from a run that died
        # between publishing it and recording it: it has no owner, drop it.
        # ponytail: delete_job removes the whole job directory, not just the
        # WAV. Ceiling: fine while a job directory holds only its audio.
        self.storage.delete_job(job.id)
        self.audio.add(self.storage.write(job.id, rendered, gaps))
        return job

    def _check(self, stop: _AnyEventToken) -> None:
        if stop.is_cancelled():
            raise _Stopping

    def _model(self, provider_id: str, model_id: str) -> ModelDescriptor:
        for item in self.catalog.list_models():
            descriptor = item.descriptor
            if descriptor.identity == (provider_id, model_id) and descriptor.supports(
                ModelCapability.SYNTHESIS
            ):
                return descriptor
        raise _CodedFailure(SynthesisJobFailureCode.MODEL_UNKNOWN.value)

    def _step(self, job: SynthesisJob, target: SynthesisJobState) -> SynthesisJob:
        return job.transition_to(target, at=self._not_before(job))

    def _latest(self, job: SynthesisJob) -> SynthesisJob:
        persisted = self.jobs.get(job.id)
        return job if persisted is None or persisted.state.is_terminal else persisted

    def _finish_cancelled(self, job: SynthesisJob) -> SynthesisJob:
        at = self._not_before(job)
        if job.state is not SynthesisJobState.CANCELLING:
            job = job.transition_to(SynthesisJobState.CANCELLING, at=at)
        return self._save(job.transition_to(SynthesisJobState.CANCELLED, at=at))

    def _fail(self, job: SynthesisJob, code: str) -> SynthesisJob:
        failed = job.transition_to(
            SynthesisJobState.FAILED, at=self._not_before(job), error_code=code
        )
        saved = self._save(failed)
        return saved if saved is failed else self._finish_cancelled(saved)

    def _save(self, job: SynthesisJob) -> SynthesisJob:
        """Persist ``job``, or return the persisted cancel it must not replace."""
        with self._lock:
            if job.state not in _CANCEL_PATH:
                persisted = self.jobs.get(job.id)
                if persisted is not None and persisted.state in _CANCEL_PATH:
                    return persisted
            self.jobs.save(job)
        return job

    def _not_before(self, job: SynthesisJob) -> datetime:
        now = self.clock()
        return job.updated_at if now < job.updated_at else now


def _error_code(error: BaseException) -> str:
    """Typed engine/storage errors carry a stable ``code``; keep only that."""
    if isinstance(error, _CodedFailure):
        return error.code
    code: object = getattr(error, "code", None)
    if isinstance(code, StrEnum):
        return code.value
    return SynthesisRunnerFailureCode.INTERNAL.value


__all__ = ["SynthesisRunner", "SynthesisRunnerFailureCode"]
