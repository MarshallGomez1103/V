"""Pure chunk planning and provider-neutral transcription coordination."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from voz.application.ports.inference_audio import InferenceAudioSource
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
    clamp_words,
)


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """Processing bounds plus the non-overlapping timeline owned by one chunk."""

    index: int
    process_start_ms: int
    process_end_ms: int
    owned_start_ms: int
    owned_end_ms: int

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise ValueError("chunk index must be a non-negative integer")
        values = (
            self.process_start_ms,
            self.process_end_ms,
            self.owned_start_ms,
            self.owned_end_ms,
        )
        if any(type(value) is not int for value in values):
            raise TypeError("chunk offsets must be integer milliseconds")
        if not (
            0
            <= self.process_start_ms
            <= self.owned_start_ms
            < self.owned_end_ms
            <= self.process_end_ms
        ):
            raise ValueError("chunk processing and ownership bounds are invalid")

    @property
    def clip(self) -> TranscriptionClip:
        return TranscriptionClip(self.process_start_ms, self.process_end_ms)


@dataclass(frozen=True, slots=True)
class ChunkProgress:
    completed_chunks: int
    total_chunks: int

    def __post_init__(self) -> None:
        if type(self.total_chunks) is not int or self.total_chunks <= 0:
            raise ValueError("total_chunks must be positive")
        if (
            type(self.completed_chunks) is not int
            or self.completed_chunks < 0
            or self.completed_chunks > self.total_chunks
        ):
            raise ValueError("completed_chunks must be within the plan")

    @property
    def fraction(self) -> float:
        return self.completed_chunks / self.total_chunks


ChunkProgressCallback = Callable[[ChunkProgress], None]


def plan_audio_chunks(
    duration_ms: int,
    *,
    chunk_duration_ms: int = 30 * 60 * 1_000,
    overlap_ms: int = 5_000,
) -> tuple[AudioChunk, ...]:
    """Build deterministic chunks whose ownership spans the timeline once."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("duration_ms must be a positive integer")
    if type(chunk_duration_ms) is not int or chunk_duration_ms <= 0:
        raise ValueError("chunk_duration_ms must be a positive integer")
    if type(overlap_ms) is not int or not 0 <= overlap_ms < chunk_duration_ms:
        raise ValueError("overlap_ms must be non-negative and smaller than a chunk")

    chunks: list[AudioChunk] = []
    owned_start = 0
    while owned_start < duration_ms:
        owned_end = min(owned_start + chunk_duration_ms, duration_ms)
        chunks.append(
            AudioChunk(
                index=len(chunks),
                process_start_ms=max(0, owned_start - overlap_ms),
                process_end_ms=min(duration_ms, owned_end + overlap_ms),
                owned_start_ms=owned_start,
                owned_end_ms=owned_end,
            )
        )
        owned_start = owned_end
    return tuple(chunks)


def owned_chunk_segments(
    chunk: AudioChunk,
    segments: tuple[TranscriptionSegment, ...],
) -> tuple[TranscriptionSegment, ...]:
    """Keep only segments owned by a chunk and clamp them to that region."""
    owned: list[TranscriptionSegment] = []
    for segment in segments:
        midpoint = segment.start_ms + (segment.end_ms - segment.start_ms) / 2
        if not chunk.owned_start_ms <= midpoint < chunk.owned_end_ms:
            continue
        start_ms = max(segment.start_ms, chunk.owned_start_ms)
        end_ms = min(segment.end_ms, chunk.owned_end_ms)
        if start_ms < end_ms:
            owned.append(
                TranscriptionSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=segment.text,
                    words=clamp_words(segment.words, start_ms, end_ms),
                )
            )
    return tuple(owned)


def globalize_chunk_result(
    chunk: AudioChunk,
    result: TranscriptionResult,
) -> TranscriptionResult:
    """Translate provider-local offsets onto the normalized global timeline."""
    return TranscriptionResult(
        segments=tuple(
            TranscriptionSegment(
                start_ms=segment.start_ms + chunk.process_start_ms,
                end_ms=segment.end_ms + chunk.process_start_ms,
                text=segment.text,
                words=tuple(
                    replace(
                        word,
                        start_ms=word.start_ms + chunk.process_start_ms,
                        end_ms=word.end_ms + chunk.process_start_ms,
                    )
                    for word in segment.words
                ),
            )
            for segment in result.segments
        ),
        language=result.language,
    )


def merge_transcription_language(
    current: str | None,
    incoming: str | None,
) -> str | None:
    """Merge language metadata or reject contradictory provider output."""
    if current is None:
        return incoming
    if incoming is None or incoming == current:
        return current
    raise TranscriptionError(
        TranscriptionFailureCode.PROVIDER_FAILED,
        "The provider returned inconsistent language metadata between chunks.",
    )


@dataclass(slots=True)
class ChunkedTranscription:
    """Run chunks in order and merge their owned global timeline regions."""

    provider: TranscriptionProvider
    audio_source: InferenceAudioSource

    def execute(
        self,
        *,
        duration_ms: int,
        options: TranscriptionOptions,
        chunk_duration_ms: int = 30 * 60 * 1_000,
        overlap_ms: int = 5_000,
        on_progress: ChunkProgressCallback | None = None,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        chunks = plan_audio_chunks(
            duration_ms,
            chunk_duration_ms=chunk_duration_ms,
            overlap_ms=overlap_ms,
        )
        output: list[TranscriptionSegment] = []
        language: str | None = None
        for completed, chunk in enumerate(chunks, start=1):
            with self.audio_source.open(chunk.clip) as audio:
                local_result = self.provider.transcribe(
                    audio=audio,
                    options=replace(options, clip=None),
                    cancellation=cancellation,
                )
            result = globalize_chunk_result(chunk, local_result)
            language = merge_transcription_language(language, result.language)
            output.extend(owned_chunk_segments(chunk, result.segments))
            if on_progress is not None:
                on_progress(ChunkProgress(completed, len(chunks)))
        return TranscriptionResult(segments=tuple(output), language=language)


__all__ = [
    "AudioChunk",
    "ChunkProgress",
    "ChunkProgressCallback",
    "ChunkedTranscription",
    "globalize_chunk_result",
    "merge_transcription_language",
    "owned_chunk_segments",
    "plan_audio_chunks",
]
