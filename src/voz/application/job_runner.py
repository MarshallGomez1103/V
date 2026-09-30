"""Single-worker transcription pipeline with typed failure and cooperative cancel.

The runner owns the explicit job state machine: it advances a job through the
pipeline states, delegates the only heavy stage to ``RecoverableTranscription``
(which keeps atomic chunk checkpoints), and persists a stable ``error_code`` on
failure. Cancellation is requested from any thread through ``cancel``; the
worker honours it between recoverable units. Shutdown leaves a running job in
its processable state so that ``recover`` can resume it on the next start.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from voz.application.chunked_transcription import (
    ChunkProgress,
    merge_transcription_language,
)
from voz.application.ports.inference_audio import (
    InferenceAudioError,
    InferenceAudioFailureCode,
    InferenceAudioSource,
)
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.repositories import (
    MediaAssetRepository,
    SegmentRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
)
from voz.application.ports.transcription import (
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_checkpoint import (
    TranscriptionCheckpoint,
    TranscriptionCheckpointStore,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)

DEFAULT_CHUNK_DURATION_MS = 30 * 60 * 1_000
DEFAULT_OVERLAP_MS = 5_000


class JobRunnerFailureCode(StrEnum):
    """Runner-level failures; provider/media adapters carry their own codes."""

    SELECTION_MISSING = "job_selection_missing"
    MEDIA_ASSET_MISSING = "job_media_asset_missing"
    DURATION_UNKNOWN = "job_media_duration_unknown"
    INTERNAL = "job_internal_error"


class JobNotFound(LookupError):
    """The referenced job does not exist."""


class JobTerminal(RuntimeError):
    """The job already finished and cannot be cancelled."""


class InferenceAudioPreparer(Protocol):
    """Create the normalized derivative for one media asset when it is missing."""

    def prepare(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> None: ...


ProviderFactory = Callable[[JobSelection], TranscriptionProvider]
AudioSourceFactory = Callable[[UUID, UUID], InferenceAudioSource]


def transcript_id_for(job_id: UUID) -> UUID:
    """Deterministic transcript identity: reproducible and idempotent on resume."""
    return uuid5(job_id, "transcript")


class _Stopping(Exception):
    """Raised inside the worker to leave the current job recoverable on shutdown."""


@dataclass(frozen=True, slots=True)
class _EventToken:
    event: threading.Event

    def is_cancelled(self) -> bool:
        return self.event.is_set()


@dataclass(slots=True)
class _LockedJobs:
    """Serialize job writes with ``JobRunner.cancel`` so progress never regresses."""

    inner: TranscriptionJobRepository
    lock: threading.Lock

    def add(self, job: TranscriptionJob) -> None:
        with self.lock:
            self.inner.add(job)

    def save(self, job: TranscriptionJob) -> None:
        with self.lock:
            self.inner.save(job)

    def get(self, job_id: UUID) -> TranscriptionJob | None:
        return self.inner.get(job_id)

    def list_by_project(self, project_id: UUID) -> Sequence[TranscriptionJob]:
        return self.inner.list_by_project(project_id)

    def list_by_media_asset(self, media_asset_id: UUID) -> Sequence[TranscriptionJob]:
        return self.inner.list_by_media_asset(media_asset_id)

    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        return self.inner.list_recoverable()


@dataclass(slots=True)
class _LockedCheckpoints:
    inner: TranscriptionCheckpointStore
    lock: threading.Lock

    def commit(
        self, checkpoint: TranscriptionCheckpoint, job: TranscriptionJob
    ) -> None:
        with self.lock:
            self.inner.commit(checkpoint, job)

    def list_for_job(self, job_id: UUID) -> Sequence[TranscriptionCheckpoint]:
        return self.inner.list_for_job(job_id)


@dataclass(slots=True)
class JobRunner:
    """One daemon worker draining a FIFO of job identities.

    # ponytail: un worker global; N workers cuando importe.
    """

    jobs: TranscriptionJobRepository
    selections: TranscriptionJobSelectionRepository
    media_assets: MediaAssetRepository
    transcripts: TranscriptRepository
    segments: SegmentRepository
    checkpoints: TranscriptionCheckpointStore
    provider_for: ProviderFactory
    audio_source_for: AudioSourceFactory
    audio_preparer: InferenceAudioPreparer
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    chunk_duration_ms: int = DEFAULT_CHUNK_DURATION_MS
    overlap_ms: int = DEFAULT_OVERLAP_MS
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
            target=self._loop, name="voz-job-runner", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the worker to leave its job recoverable and wait for it to exit."""
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
        """Re-enqueue every non-terminal job; checkpoints make resume idempotent."""
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

    def cancel(self, job_id: UUID) -> TranscriptionJob:
        """Mark CANCELLING now; the worker finishes to CANCELLED between units."""
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise JobNotFound(str(job_id))
            if job.state.is_terminal:
                raise JobTerminal(job.state.value)
            running = self._current == job_id
            if running:
                self._cancel.set()
            if job.state is TranscriptionJobState.CANCELLING:
                return job
            at = self._not_before(job)
            cancelling = job.transition_to(TranscriptionJobState.CANCELLING, at=at)
            if not running:
                cancelling = cancelling.transition_to(
                    TranscriptionJobState.CANCELLED, at=at
                )
            self.jobs.save(cancelling)
            return cancelling

    # -- execution -----------------------------------------------------------

    def run_job(self, job_id: UUID) -> TranscriptionJob | None:
        """Process one job synchronously; the worker thread calls this per item."""
        with self._lock:
            self._queued.discard(job_id)
            job = self.jobs.get(job_id)
            if job is None or job.state.is_terminal:
                return job
            self._current = job_id
            self._cancel.clear()
        try:
            return self._execute(job)
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
                # ponytail: run_job already persisted FAILED when it could; a
                # persistence outage must not kill the only worker.
                pass
            finally:
                self._queue.task_done()

    def _execute(self, job: TranscriptionJob) -> TranscriptionJob:
        token = _EventToken(self._cancel)
        try:
            if job.state is TranscriptionJobState.CANCELLING:
                return self._save(
                    job.transition_to(
                        TranscriptionJobState.CANCELLED, at=self._not_before(job)
                    )
                )
            selection = self.selections.get(job.id)
            if selection is None:
                return self._fail(job, JobRunnerFailureCode.SELECTION_MISSING.value)
            media_asset = self.media_assets.get(job.media_asset_id)
            if media_asset is None:
                return self._fail(job, JobRunnerFailureCode.MEDIA_ASSET_MISSING.value)
            if media_asset.duration_ms is None:
                return self._fail(job, JobRunnerFailureCode.DURATION_UNKNOWN.value)
            audio_source = self.audio_source_for(job.project_id, job.media_asset_id)
            result: TranscriptionResult | None = None

            while job.state is not TranscriptionJobState.COMPLETED:
                if token.is_cancelled():
                    return self._finish_cancelled(job)
                if self._stopping.is_set():
                    raise _Stopping
                # Work belongs to the *current* state so a recovered job resumes
                # exactly where it stopped; the transition follows the work.
                if job.state is TranscriptionJobState.PREPROCESSING:
                    if not self._derivative_exists(audio_source):
                        self.audio_preparer.prepare(
                            project_id=job.project_id,
                            media_asset_id=job.media_asset_id,
                            cancellation=token,
                        )
                elif job.state is TranscriptionJobState.TRANSCRIBING:
                    outcome = RecoverableTranscription(
                        provider=self.provider_for(selection),
                        audio_source=audio_source,
                        checkpoints=_LockedCheckpoints(self.checkpoints, self._lock),
                        jobs=_LockedJobs(self.jobs, self._lock),
                        clock=self.clock,
                    ).execute(
                        job=job,
                        duration_ms=media_asset.duration_ms,
                        options=TranscriptionOptions(
                            model=selection.model, language=selection.language
                        ),
                        chunk_duration_ms=self.chunk_duration_ms,
                        overlap_ms=self.overlap_ms,
                        on_progress=self._on_progress,
                        cancellation=token,
                    )
                    job = outcome.job
                    if outcome.cancelled:
                        return job
                    result = outcome.result
                elif job.state is TranscriptionJobState.PERSISTING:
                    if result is None:
                        result = self._result_from_checkpoints(job.id)
                    self._persist_transcript(job, selection, result)
                # QUEUED / PROBING / ALIGNING / DIARIZING / MERGING: no work yet.
                # ponytail: the original was probed at import; PROBING exists for
                # the state contract and future re-validation.
                job = self._advance(job)
            return job
        except _Stopping:
            return job
        except Exception as error:
            job = self._latest(job)
            if token.is_cancelled() or job.state is TranscriptionJobState.CANCELLING:
                return self._finish_cancelled(job)
            return self._fail(job, _error_code(error))

    def _on_progress(self, progress: ChunkProgress) -> None:
        # Progress was persisted atomically with the checkpoint; this hook only
        # gives shutdown a safe point between recoverable units.
        del progress
        if self._stopping.is_set():
            raise _Stopping

    def _advance(self, job: TranscriptionJob) -> TranscriptionJob:
        successor = {
            TranscriptionJobState.QUEUED: TranscriptionJobState.PROBING,
            TranscriptionJobState.PROBING: TranscriptionJobState.PREPROCESSING,
            TranscriptionJobState.PREPROCESSING: TranscriptionJobState.TRANSCRIBING,
            TranscriptionJobState.TRANSCRIBING: TranscriptionJobState.ALIGNING,
            TranscriptionJobState.ALIGNING: TranscriptionJobState.DIARIZING,
            TranscriptionJobState.DIARIZING: TranscriptionJobState.MERGING,
            TranscriptionJobState.MERGING: TranscriptionJobState.PERSISTING,
            TranscriptionJobState.PERSISTING: TranscriptionJobState.COMPLETED,
        }[job.state]
        return self._save(job.transition_to(successor, at=self._not_before(job)))

    def _derivative_exists(self, audio_source: InferenceAudioSource) -> bool:
        try:
            with audio_source.open():
                return True
        except InferenceAudioError as error:
            if error.code is InferenceAudioFailureCode.NOT_FOUND:
                return False
            raise

    def _result_from_checkpoints(self, job_id: UUID) -> TranscriptionResult:
        segments: list[TranscriptionSegment] = []
        language: str | None = None
        for checkpoint in self.checkpoints.list_for_job(job_id):
            segments.extend(checkpoint.segments)
            language = merge_transcription_language(language, checkpoint.language)
        return TranscriptionResult(tuple(segments), language)

    def _persist_transcript(
        self,
        job: TranscriptionJob,
        selection: JobSelection,
        result: TranscriptionResult,
    ) -> None:
        transcript_id = transcript_id_for(job.id)
        # Identities are deterministic, so a crash between the transcript insert
        # and the last segment (or before COMPLETED) resumes by adding only the
        # missing segments instead of duplicating or skipping them.
        if self.transcripts.get(transcript_id) is None:
            self.transcripts.add(
                Transcript(
                    job.project_id,
                    job.media_asset_id,
                    id=transcript_id,
                    language=result.language or selection.language,
                    created_at=self._not_before(job),
                )
            )
        stored = {s.id for s in self.segments.list_by_transcript(transcript_id)}
        for index, item in enumerate(result.segments):
            segment_id = uuid5(transcript_id, f"segment:{index}")
            if segment_id not in stored:
                self.segments.add(
                    Segment(
                        transcript_id,
                        item.start_ms,
                        item.end_ms,
                        item.text,
                        id=segment_id,
                    )
                )

    def _latest(self, job: TranscriptionJob) -> TranscriptionJob:
        """Re-read after a failure so persisted checkpoint progress is kept."""
        persisted = self.jobs.get(job.id)
        return job if persisted is None or persisted.state.is_terminal else persisted

    def _finish_cancelled(self, job: TranscriptionJob) -> TranscriptionJob:
        at = self._not_before(job)
        if job.state is not TranscriptionJobState.CANCELLING:
            job = job.transition_to(TranscriptionJobState.CANCELLING, at=at)
        return self._save(job.transition_to(TranscriptionJobState.CANCELLED, at=at))

    def _fail(self, job: TranscriptionJob, code: str) -> TranscriptionJob:
        failed = job.transition_to(
            TranscriptionJobState.FAILED,
            at=self._not_before(job),
            error_code=code,
        )
        return self._save(failed)

    def _save(self, job: TranscriptionJob) -> TranscriptionJob:
        with self._lock:
            self.jobs.save(job)
        return job

    def _not_before(self, job: TranscriptionJob) -> datetime:
        now = self.clock()
        return job.updated_at if now < job.updated_at else now


def _error_code(error: BaseException) -> str:
    """Adapters raise typed errors whose ``code`` is already a stable identifier."""
    code: object = getattr(error, "code", None)
    if isinstance(code, StrEnum):
        return code.value
    return JobRunnerFailureCode.INTERNAL.value


__all__ = [
    "AudioSourceFactory",
    "InferenceAudioPreparer",
    "JobNotFound",
    "JobRunner",
    "JobRunnerFailureCode",
    "JobTerminal",
    "ProviderFactory",
    "transcript_id_for",
]
