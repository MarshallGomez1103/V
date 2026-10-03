"""Restart-safe ASR orchestration with one atomic checkpoint per chunk."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from voz.application.chunked_transcription import (
    AudioChunk,
    ChunkProgress,
    ChunkProgressCallback,
    globalize_chunk_result,
    merge_transcription_language,
    owned_chunk_segments,
    plan_audio_chunks,
)
from voz.application.ports.inference_audio import InferenceAudioSource
from voz.application.ports.repositories import TranscriptionJobRepository
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_checkpoint import (
    TranscriptionCheckpoint,
    TranscriptionCheckpointStore,
)
from voz.application.progress_throttle import MIN_SAVE_INTERVAL_S, ProgressThrottle
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)


@dataclass(frozen=True, slots=True)
class RecoverableTranscriptionOutcome:
    """Current durable result and job snapshot, complete or cancelled."""

    result: TranscriptionResult
    job: TranscriptionJob
    completed_chunks: int
    total_chunks: int

    @property
    def cancelled(self) -> bool:
        return self.job.state is TranscriptionJobState.CANCELLED


@dataclass(slots=True)
class RecoverableTranscription:
    """Skip confirmed chunks and commit each new result before progressing."""

    provider: TranscriptionProvider
    audio_source: InferenceAudioSource
    checkpoints: TranscriptionCheckpointStore
    jobs: TranscriptionJobRepository
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    monotonic: Callable[[], float] = time.monotonic
    min_save_interval_s: float = MIN_SAVE_INTERVAL_S

    def execute(
        self,
        *,
        job: TranscriptionJob,
        duration_ms: int,
        options: TranscriptionOptions,
        chunk_duration_ms: int = 30 * 60 * 1_000,
        overlap_ms: int = 5_000,
        on_progress: ChunkProgressCallback | None = None,
        cancellation: TranscriptionCancellationToken | None = None,
        progress_range: tuple[float, float] = (0.0, 1.0),
    ) -> RecoverableTranscriptionOutcome:
        """Transcribe the missing chunks.

        ``progress_range`` maps the stage onto the job's global progress (the first
        value is where transcription starts, the second where it ends). Besides the
        atomic checkpoint per chunk, ``stage_progress`` (chunks done plus the position
        inside the current one) is saved
        while a chunk is decoded, at most twice per second.
        """
        if job.state is not TranscriptionJobState.TRANSCRIBING:
            raise ValueError("recoverable transcription requires a TRANSCRIBING job")
        chunks = plan_audio_chunks(
            duration_ms,
            chunk_duration_ms=chunk_duration_ms,
            overlap_ms=overlap_ms,
        )
        existing = tuple(self.checkpoints.list_for_job(job.id))
        self._validate_existing(existing, chunks, options)
        # In-chunk saves may leave the job ahead of its last checkpoint, never behind.
        if existing and job.progress < existing[-1].job_progress:
            raise ValueError("job progress does not match its latest checkpoint")
        low, high = progress_range
        throttle = ProgressThrottle(self.min_save_interval_s, self.monotonic)
        output: list[TranscriptionSegment] = []
        language: str | None = None
        for checkpoint in existing:
            output.extend(checkpoint.segments)
            language = merge_transcription_language(language, checkpoint.language)

        current_job = job

        def publish(stage: float) -> None:
            """Throttled in-chunk progress; the checkpoint covers chunk ends."""
            nonlocal current_job
            if self._is_cancelled(cancellation) or not throttle.ready():
                return
            stage = max(stage, current_job.stage_progress or 0.0)
            current_job = current_job.with_stage_progress(
                stage,
                progress=low + (high - low) * stage,
                at=self._timestamp_not_before(current_job.updated_at),
            )
            self.jobs.save(current_job)

        def position_callback(chunk: AudioChunk, done: int) -> Callable[[int], None]:
            span = chunk.process_end_ms - chunk.process_start_ms

            def on_position(local_ms: int) -> None:
                publish((done + min(0.99, local_ms / span)) / len(chunks))

            return on_position

        for chunk in chunks[len(existing) :]:
            if self._is_cancelled(cancellation):
                return self._cancelled_outcome(
                    current_job,
                    output,
                    language,
                    len(existing),
                    len(chunks),
                )
            try:
                with self.audio_source.open(chunk.clip) as audio:
                    local_result = self.provider.transcribe(
                        audio=audio,
                        options=replace(
                            options,
                            clip=None,
                            on_position=position_callback(chunk, len(existing)),
                        ),
                        cancellation=cancellation,
                    )
            except TranscriptionError as error:
                if error.code is not TranscriptionFailureCode.CANCELLED:
                    raise
                return self._cancelled_outcome(
                    current_job,
                    output,
                    language,
                    len(existing),
                    len(chunks),
                )
            result = globalize_chunk_result(chunk, local_result)
            if self._is_cancelled(cancellation):
                return self._cancelled_outcome(
                    current_job,
                    output,
                    language,
                    len(existing),
                    len(chunks),
                )

            owned = owned_chunk_segments(chunk, result.segments)
            language = merge_transcription_language(language, result.language)
            completed_count = len(existing) + 1
            progress = completed_count / len(chunks)
            stage = max(progress, current_job.stage_progress or 0.0)
            current_job = current_job.with_stage_progress(
                stage,
                progress=low + (high - low) * stage,
                at=self._timestamp_not_before(current_job.updated_at),
            )
            checkpoint = TranscriptionCheckpoint(
                job_id=job.id,
                chunk_index=chunk.index,
                process_start_ms=chunk.process_start_ms,
                process_end_ms=chunk.process_end_ms,
                owned_start_ms=chunk.owned_start_ms,
                owned_end_ms=chunk.owned_end_ms,
                provider_id=options.model.provider_id,
                model_id=options.model.model_id,
                model_source=options.model.source,
                model_revision=options.model.revision,
                requested_language=options.language,
                segments=owned,
                language=result.language,
                progress=progress,
                job_progress=current_job.progress,
                completed_at=current_job.updated_at,
            )
            self.checkpoints.commit(checkpoint, current_job)
            existing = (*existing, checkpoint)
            output.extend(owned)
            if on_progress is not None:
                on_progress(ChunkProgress(completed_count, len(chunks)))

        return RecoverableTranscriptionOutcome(
            result=TranscriptionResult(tuple(output), language),
            job=current_job,
            completed_chunks=len(existing),
            total_chunks=len(chunks),
        )

    def _cancelled_outcome(
        self,
        job: TranscriptionJob,
        segments: list[TranscriptionSegment],
        language: str | None,
        completed_chunks: int,
        total_chunks: int,
    ) -> RecoverableTranscriptionOutcome:
        timestamp = self._timestamp_not_before(job.updated_at)
        cancelling = job.transition_to(
            TranscriptionJobState.CANCELLING,
            at=timestamp,
        )
        cancelled = cancelling.transition_to(
            TranscriptionJobState.CANCELLED,
            at=timestamp,
        )
        self.jobs.save(cancelled)
        return RecoverableTranscriptionOutcome(
            result=TranscriptionResult(tuple(segments), language),
            job=cancelled,
            completed_chunks=completed_chunks,
            total_chunks=total_chunks,
        )

    def _timestamp_not_before(self, minimum: datetime) -> datetime:
        timestamp = self.clock()
        return minimum if timestamp < minimum else timestamp

    @staticmethod
    def _is_cancelled(
        cancellation: TranscriptionCancellationToken | None,
    ) -> bool:
        return cancellation is not None and cancellation.is_cancelled()

    @staticmethod
    def _validate_existing(
        checkpoints: tuple[TranscriptionCheckpoint, ...],
        chunks: tuple[AudioChunk, ...],
        options: TranscriptionOptions,
    ) -> None:
        if len(checkpoints) > len(chunks):
            raise ValueError("checkpoint count exceeds the chunk plan")
        for expected_index, checkpoint in enumerate(checkpoints):
            chunk = chunks[expected_index]
            if checkpoint.chunk_index != expected_index:
                raise ValueError("checkpoints must form a contiguous prefix")
            if checkpoint.progress != (expected_index + 1) / len(chunks):
                raise ValueError("checkpoint progress does not match the chunk plan")
            if (
                checkpoint.process_start_ms != chunk.process_start_ms
                or checkpoint.process_end_ms != chunk.process_end_ms
                or checkpoint.owned_start_ms != chunk.owned_start_ms
                or checkpoint.owned_end_ms != chunk.owned_end_ms
                or checkpoint.provider_id != options.model.provider_id
                or checkpoint.model_id != options.model.model_id
                or checkpoint.model_source != options.model.source
                or checkpoint.model_revision != options.model.revision
                or checkpoint.requested_language != options.language
            ):
                raise ValueError(
                    "checkpoint does not match the requested plan, model, "
                    "or requested language"
                )


__all__ = ["RecoverableTranscription", "RecoverableTranscriptionOutcome"]
