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
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from voz.application.assign_speakers import AssignProviderSpeakers, AssignSpeakers
from voz.application.chunked_transcription import (
    ChunkProgress,
    merge_transcription_language,
)
from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationProvider,
    DiarizationResult,
)
from voz.application.ports.inference_audio import (
    InferenceAudioError,
    InferenceAudioFailureCode,
    InferenceAudioSource,
)
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationProgress,
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
    TranscriptionWord,
    clamp_words,
)
from voz.application.ports.transcription_checkpoint import (
    TranscriptionCheckpoint,
    TranscriptionCheckpointStore,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.application.progress_throttle import ProgressThrottle
from voz.application.quality_flags import quality_flags
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.word import Word

DEFAULT_CHUNK_DURATION_MS = 30 * 60 * 1_000
DEFAULT_OVERLAP_MS = 5_000

# Global progress by stage: normalization, transcription, speakers, persistence.
# Without speaker diarization the transcription takes the speakers' share too.
PREPROCESS_END = 0.02
TRANSCRIBE_END_WITH_SPEAKERS = 0.8
SPEAKERS_END = 0.98


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
        on_progress: Callable[[MediaNormalizationProgress], None] | None = None,
    ) -> None: ...


ProviderFactory = Callable[[JobSelection], TranscriptionProvider]
DiarizationProviderFactory = Callable[[], DiarizationProvider]
ReleaseAsr = Callable[[JobSelection], None]
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


@dataclass(frozen=True, slots=True)
class _AnyEventToken:
    """Cancelled when the user cancels *or* the server is shutting down."""

    events: tuple[threading.Event, ...]

    def is_cancelled(self) -> bool:
        return any(event.is_set() for event in self.events)


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
    diarization_provider_for: DiarizationProviderFactory | None = None
    assign_speakers: AssignSpeakers | None = None
    assign_provider_speakers: AssignProviderSpeakers | None = None
    """Speakers from cloud ASR labels; only used when no local diarization is asked."""
    release_asr: ReleaseAsr = lambda selection: None
    """Free the ASR engine before diarizing (S6.15/S14.07); must be idempotent."""
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
            persisted = False
            wants_speakers = _wants_diarization(selection)
            transcribe_end = (
                TRANSCRIBE_END_WITH_SPEAKERS if wants_speakers else SPEAKERS_END
            )

            def report(
                stage: float, low: float, high: float, throttle: ProgressThrottle
            ) -> None:
                """Throttled stage progress; cancellation wins over a late write."""
                nonlocal job
                if token.is_cancelled() or not throttle.ready():
                    return
                job = self._save_stage_progress(job, stage, low + (high - low) * stage)

            def ensure_transcript(current: JobSelection) -> TranscriptionResult:
                """Persist the text as soon as it exists (idempotent on resume)."""
                nonlocal result, persisted
                if result is None:
                    result = self._result_from_checkpoints(job.id)
                if not persisted:
                    self._persist_transcript(
                        job, current, result, media_asset.duration_ms
                    )
                    persisted = True
                return result

            while job.state is not TranscriptionJobState.COMPLETED:
                if token.is_cancelled():
                    return self._finish_cancelled(job)
                if self._stopping.is_set():
                    raise _Stopping
                # Work belongs to the *current* state so a recovered job resumes
                # exactly where it stopped; the transition follows the work.
                if job.state is TranscriptionJobState.PREPROCESSING:
                    if not self._derivative_exists(audio_source):
                        job = self._restart_stage(job)
                        throttle = ProgressThrottle()
                        self.audio_preparer.prepare(
                            project_id=job.project_id,
                            media_asset_id=job.media_asset_id,
                            cancellation=token,
                            on_progress=lambda sample, throttle=throttle: report(
                                sample.processed_ms / sample.total_ms,
                                0.0,
                                PREPROCESS_END,
                                throttle,
                            ),
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
                            model=selection.model,
                            language=selection.language,
                            glossary=selection.glossary,
                            quality_profile=selection.quality_profile,
                            prompt=selection.prompt,
                        ),
                        chunk_duration_ms=self.chunk_duration_ms,
                        overlap_ms=self.overlap_ms,
                        on_progress=self._on_progress,
                        cancellation=token,
                        progress_range=(PREPROCESS_END, transcribe_end),
                    )
                    job = outcome.job
                    if outcome.cancelled:
                        return job
                    result = outcome.result
                elif job.state is TranscriptionJobState.ALIGNING:
                    # The text is final here: show it before the speakers exist.
                    ensure_transcript(selection)
                elif job.state is TranscriptionJobState.DIARIZING:
                    ensure_transcript(
                        selection
                    )  # also for jobs recovered from older runs
                    if wants_speakers:
                        if job.stage_progress is not None:
                            job = self._restart_stage(job)  # the work starts over
                        throttle = ProgressThrottle()
                        diarized, selection = self._diarize(
                            job,
                            selection,
                            audio_source,
                            token,
                            lambda stage, throttle=throttle: report(
                                stage,
                                TRANSCRIBE_END_WITH_SPEAKERS,
                                SPEAKERS_END,
                                throttle,
                            ),
                        )
                        selection = self._assign_speakers(job, selection, diarized)
                elif job.state is TranscriptionJobState.PERSISTING:
                    # ponytail: a job that an older version left here keeps its
                    # text but no speakers; newer runs assign them in DIARIZING.
                    final = ensure_transcript(selection)
                    if selection.diarization is None:
                        selection = self._assign_provider_speakers(
                            job, selection, final
                        )
                # QUEUED / PROBING / MERGING: no work yet.
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

    def _diarize(
        self,
        job: TranscriptionJob,
        selection: JobSelection,
        audio_source: InferenceAudioSource,
        token: _EventToken,
        on_progress: Callable[[float], None] | None = None,
    ) -> tuple[DiarizationResult | None, JobSelection]:
        """Run diarization; a failure is recorded and never loses the transcript."""
        options = selection.diarization
        assert options is not None
        stop = _AnyEventToken((self._cancel, self._stopping))
        try:
            # The ASR engine and the diarization models must not share memory.
            self.release_asr(selection)
            if self.diarization_provider_for is None:
                raise DiarizationError(
                    DiarizationFailureCode.RUNTIME_UNAVAILABLE,
                    "Speaker diarization is not wired.",
                )
            provider = self.diarization_provider_for()
            with audio_source.open() as audio:
                result = provider.diarize(
                    audio=audio,
                    options=options,
                    cancellation=stop,
                    on_progress=on_progress,
                )
            return result, selection
        except Exception as error:
            if token.is_cancelled():
                raise
            if self._stopping.is_set():
                raise _Stopping from error
            return None, self._record_diarization_error(job, selection, error)

    def _assign_speakers(
        self,
        job: TranscriptionJob,
        selection: JobSelection,
        diarized: DiarizationResult | None,
    ) -> JobSelection:
        if diarized is None:
            return selection  # the failure was already recorded
        try:
            if self.assign_speakers is None:
                raise DiarizationError(
                    DiarizationFailureCode.RUNTIME_UNAVAILABLE,
                    "Speaker assignment is not wired.",
                )
            self.assign_speakers.execute(transcript_id_for(job.id), diarized)
        except Exception as error:
            return self._record_diarization_error(job, selection, error)
        return selection

    def _assign_provider_speakers(
        self,
        job: TranscriptionJob,
        selection: JobSelection,
        result: TranscriptionResult,
    ) -> JobSelection:
        """Entities for the labels a cloud ASR already gave; idempotent on resume."""
        if self.assign_provider_speakers is None:
            return selection
        transcript_id = transcript_id_for(job.id)
        labels = {
            uuid5(transcript_id, f"segment:{index}"): item.speaker
            for index, item in enumerate(result.segments)
            if item.speaker and item.text.strip()
        }
        if not labels:
            return selection
        try:
            self.assign_provider_speakers.execute(transcript_id, job.project_id, labels)
        except Exception as error:
            return self._record_diarization_error(job, selection, error)
        return selection

    def _record_diarization_error(
        self, job: TranscriptionJob, selection: JobSelection, error: Exception
    ) -> JobSelection:
        code = _error_code(error, DiarizationFailureCode.PROVIDER_FAILED.value)
        self.selections.record_diarization_error(job.id, code)
        return replace(selection, diarization_error_code=code)

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

    def _save_stage_progress(
        self, job: TranscriptionJob, stage: float, progress: float
    ) -> TranscriptionJob:
        """Persist progress inside the current stage (callers throttle)."""
        updated = job.with_stage_progress(
            max(stage, job.stage_progress or 0.0),
            progress=progress,
            at=self._not_before(job),
        )
        return self._save(updated)

    def _restart_stage(self, job: TranscriptionJob) -> TranscriptionJob:
        return job.restart_stage(at=self._not_before(job))

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
        audio_duration_ms: int | None = None,
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
            # Whisper prefixes a word-boundary space; it is not content. A
            # whitespace-only span has no literal text to keep.
            text = item.text.strip()
            if text and segment_id not in stored:
                self.segments.add(
                    Segment(
                        transcript_id,
                        item.start_ms,
                        item.end_ms,
                        text,
                        id=segment_id,
                        words=_domain_words(segment_id, item),
                        # S13.04: hints only; ``text`` stays the literal ASR output.
                        quality_flags=quality_flags(
                            item, audio_duration_ms=audio_duration_ms
                        ),
                        avg_logprob=item.avg_logprob,
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


def _domain_words(segment_id: UUID, item: TranscriptionSegment) -> tuple[Word, ...]:
    """Words for one segment: trimmed, non-empty, inside it, ids stable on resume."""
    stripped: list[TranscriptionWord] = []
    for word in item.words:
        text = word.text.strip()  # same boundary-space rule as the segment text
        if text:
            stripped.append(replace(word, text=text))
    return tuple(
        Word(
            segment_id,
            word.start_ms,
            word.end_ms,
            word.text,
            id=uuid5(segment_id, f"word:{index}"),
        )
        for index, word in enumerate(
            clamp_words(tuple(stripped), item.start_ms, item.end_ms)
        )
    )


def _wants_diarization(selection: JobSelection) -> bool:
    """Requested, and not already given up on (a recorded failure is final)."""
    return (
        selection.diarization is not None and selection.diarization_error_code is None
    )


def _error_code(
    error: BaseException, default: str = JobRunnerFailureCode.INTERNAL.value
) -> str:
    """Adapters raise typed errors whose ``code`` is already a stable identifier."""
    code: object = getattr(error, "code", None)
    if isinstance(code, StrEnum):
        return code.value
    return default


__all__ = [
    "AudioSourceFactory",
    "DiarizationProviderFactory",
    "InferenceAudioPreparer",
    "JobNotFound",
    "JobRunner",
    "JobRunnerFailureCode",
    "JobTerminal",
    "ProviderFactory",
    "ReleaseAsr",
    "transcript_id_for",
]
