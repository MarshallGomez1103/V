"""Provider-neutral application contract for speech transcription."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import BinaryIO, Protocol, cast, runtime_checkable

from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor

_SAFE_LANGUAGE_TAG = re.compile(
    r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*",
    re.ASCII,
)


class TranscriptionFailureCode(StrEnum):
    """Stable provider failures suitable for job and API translation."""

    MODEL_NOT_INSTALLED = "transcription_model_not_installed"
    GPU_UNAVAILABLE = "transcription_gpu_unavailable"
    INVALID_AUDIO = "transcription_invalid_audio"
    PROVIDER_FAILED = "transcription_provider_failed"
    CANCELLED = "transcription_cancelled"


class TranscriptionError(RuntimeError):
    """Typed transcription failure with a path-safe user message."""

    def __init__(
        self,
        code: TranscriptionFailureCode,
        user_message: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        super().__init__(user_message)


@runtime_checkable
class TranscriptionCancellationToken(Protocol):
    """Minimal cooperative cancellation contract shared by all providers."""

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        ...


def _validate_language(language: object) -> None:
    if language is None:
        return
    if not isinstance(language, str):
        raise TypeError("language must be a string or None")
    if _SAFE_LANGUAGE_TAG.fullmatch(language) is None:
        raise ValueError("language must be a trimmed language tag")


@dataclass(frozen=True, slots=True)
class TranscriptionWord:
    """One provider word inside a segment, before domain identities exist.

    Text is literal (providers usually prefix a word-boundary space). Zero
    duration is allowed here because engines emit it; ``clamp_words`` drops such
    words before persistence since the domain requires ``start_ms < end_ms``.
    """

    start_ms: int
    end_ms: int
    text: str
    probability: float | None = None

    def __post_init__(self) -> None:
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("word offsets must be integer milliseconds")
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError("word offsets must be non-negative and not reversed")
        raw_text = cast(object, self.text)
        if not isinstance(raw_text, str):
            raise TypeError("word text must be a string")
        if raw_text == "":
            raise ValueError("word text cannot be empty")
        raw_probability = cast(object, self.probability)
        if raw_probability is not None and (
            isinstance(raw_probability, bool)
            or not isinstance(raw_probability, float)
            or not math.isfinite(raw_probability)
            or not 0.0 <= raw_probability <= 1.0
        ):
            raise ValueError("word probability must be a float in [0, 1] or None")


def clamp_words(
    words: tuple[TranscriptionWord, ...],
    start_ms: int,
    end_ms: int,
) -> tuple[TranscriptionWord, ...]:
    """Clip words to ``[start_ms, end_ms]`` keeping them ordered and disjoint.

    Words that end up without duration (outside the bounds, fully overlapped by
    the previous word, or zero-length) are dropped: the segment text stays whole,
    only the timing hint is lost.
    """
    kept: list[TranscriptionWord] = []
    cursor = start_ms
    for word in words:
        word_start = max(word.start_ms, cursor)
        word_end = min(word.end_ms, end_ms)
        if word_end <= word_start:
            continue
        kept.append(replace(word, start_ms=word_start, end_ms=word_end))
        cursor = word_end
    return tuple(kept)


@dataclass(frozen=True, slots=True)
class TranscriptionSegment:
    """Provider output span before domain identities are assigned."""

    start_ms: int
    end_ms: int
    text: str
    words: tuple[TranscriptionWord, ...] = ()
    speaker: str | None = None  # opaque provider label when it diarizes
    # Engine confidence metrics (S13.04/S13.05); None when the engine has none.
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None
    # Set when the engine reported a span beyond the audio it was given, before
    # the span is clipped to the chunk (S13.04 ``out_of_bounds``).
    exceeds_audio: bool = False

    def __post_init__(self) -> None:
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("transcription offsets must be integer milliseconds")
        if self.start_ms < 0 or self.end_ms < 0:
            raise ValueError("transcription offsets must be non-negative")
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        raw_text = cast(object, self.text)
        if not isinstance(raw_text, str):
            raise TypeError("transcription text must be a string")
        if raw_text == "":
            raise ValueError("transcription text cannot be empty")
        raw_words = cast(object, self.words)
        if not isinstance(raw_words, tuple):
            raise TypeError("segment words must be a tuple")
        raw_speaker = cast(object, self.speaker)
        if raw_speaker is not None and not isinstance(raw_speaker, str):
            raise TypeError("segment speaker must be a string or None")
        previous_end_ms = self.start_ms
        for word in cast(tuple[object, ...], raw_words):
            if not isinstance(word, TranscriptionWord):
                raise TypeError("words must contain only TranscriptionWord instances")
            if word.start_ms < previous_end_ms or word.end_ms > self.end_ms:
                raise ValueError(
                    "words must be ordered, non-overlapping and inside the segment"
                )
            previous_end_ms = word.end_ms


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """Canonical path-free output returned by every transcription provider."""

    segments: tuple[TranscriptionSegment, ...]
    language: str | None = None

    def __post_init__(self) -> None:
        raw_segments = cast(object, self.segments)
        if not isinstance(raw_segments, tuple):
            raise TypeError("segments must be a tuple")
        segments = cast(tuple[object, ...], raw_segments)
        previous_end_ms = 0
        for segment in segments:
            if not isinstance(segment, TranscriptionSegment):
                raise TypeError(
                    "segments must contain only TranscriptionSegment instances"
                )
            if segment.start_ms < previous_end_ms:
                raise ValueError("segments must be ordered and non-overlapping")
            previous_end_ms = segment.end_ms
        _validate_language(self.language)

    @property
    def text(self) -> str:
        """Join provider spans without altering their literal text."""

        return "".join(segment.text for segment in self.segments)


@dataclass(frozen=True, slots=True)
class TranscriptionClip:
    """Global timeline bounds for one recoverable provider invocation."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("clip offsets must be integer milliseconds")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("clip offsets must be non-negative and increasing")


@dataclass(frozen=True, slots=True)
class TranscriptionOptions:
    """Small canonical request independent of engine-specific tuning flags."""

    model: ModelDescriptor
    language: str | None = None
    clip: TranscriptionClip | None = None
    word_timestamps: bool = True

    def __post_init__(self) -> None:
        raw_model = cast(object, self.model)
        if not isinstance(raw_model, ModelDescriptor):
            raise TypeError("model must be a ModelDescriptor")
        if not raw_model.supports(ModelCapability.TRANSCRIPTION):
            raise ValueError("model must declare the transcription capability")
        _validate_language(self.language)
        raw_clip = cast(object, self.clip)
        if raw_clip is not None and not isinstance(raw_clip, TranscriptionClip):
            raise TypeError("clip must be a TranscriptionClip or None")
        if type(self.word_timestamps) is not bool:
            raise TypeError("word_timestamps must be a bool")


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Transcribe opened inference audio under a canonical model contract."""

    @property
    def provider_id(self) -> str:
        """Return the stable identifier used by this provider's descriptors."""
        ...

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        """Transcribe an opened audio descriptor without exposing host paths."""
        ...


__all__ = [
    "TranscriptionCancellationToken",
    "TranscriptionClip",
    "TranscriptionError",
    "TranscriptionFailureCode",
    "TranscriptionOptions",
    "TranscriptionProvider",
    "TranscriptionResult",
    "TranscriptionSegment",
    "TranscriptionWord",
    "clamp_words",
]
