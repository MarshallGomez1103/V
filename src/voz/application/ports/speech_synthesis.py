"""Provider-neutral application contract for speech synthesis (ADR-0010)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast, runtime_checkable

from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.voice import Voice

_SAFE_PROVIDER_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)


class SynthesisFailureCode(StrEnum):
    """Stable engine failures suitable for job and API translation."""

    VOICE_NOT_FOUND = "voice_not_found"
    MODEL_NOT_INSTALLED = "model_not_installed"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    SYNTHESIS_FAILED = "synthesis_failed"
    CANCELLED = "cancelled"
    TEXT_TOO_LONG = "text_too_long"


class SynthesisError(RuntimeError):
    """Typed synthesis failure with a path-safe user message."""

    def __init__(
        self,
        code: SynthesisFailureCode,
        user_message: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        super().__init__(user_message)


@runtime_checkable
class SynthesisCancellationToken(Protocol):
    """Cooperative cancellation polled by engines while they render a chunk."""

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        ...


SynthesisProgressCallback = Callable[[float], None]
"""Receives the fraction (0.0-1.0, non-decreasing) of the current chunk rendered."""


class SynthesisLocality(StrEnum):
    """Where the engine runs; ``cloud`` requires consent (ADR-0006)."""

    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(frozen=True, slots=True)
class SynthesisProviderInfo:
    """What an engine declares about itself, independent of any model."""

    provider_id: str
    display_name: str
    locality: SynthesisLocality = SynthesisLocality.LOCAL
    streaming: bool = False
    """Only an engine declaring it may deliver partial audio before a chunk ends."""
    max_chunk_chars: int = 400
    """Longest chunk ``synthesize`` accepts; the chunker (V2-04) uses it as cap."""

    def __post_init__(self) -> None:
        provider_id = cast(object, self.provider_id)
        if not isinstance(provider_id, str) or not _SAFE_PROVIDER_ID.fullmatch(
            provider_id
        ):
            raise ValueError("provider_id must be a safe stable identifier")
        display_name = cast(object, self.display_name)
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("display_name must be a non-blank string")
        if not isinstance(cast(object, self.locality), SynthesisLocality):
            raise TypeError("locality must be a SynthesisLocality")
        if type(self.streaming) is not bool:
            raise TypeError("streaming must be a bool")
        if type(self.max_chunk_chars) is not int or self.max_chunk_chars < 1:
            raise ValueError("max_chunk_chars must be a positive integer")


@dataclass(frozen=True, slots=True)
class SynthesisRequirements:
    """Runtime readiness and resource hints of one model; ``None`` = unknown."""

    runtime_ready: bool
    ram_bytes: int | None = None
    disk_bytes: int | None = None

    def __post_init__(self) -> None:
        if type(self.runtime_ready) is not bool:
            raise TypeError("runtime_ready must be a bool")
        for name in ("ram_bytes", "disk_bytes"):
            value = cast(object, getattr(self, name))
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")


class PcmSampleFormat(StrEnum):
    """Little-endian mono sample encodings an engine may return."""

    INT16 = "int16"
    FLOAT32 = "float32"

    @property
    def width(self) -> int:
        """Bytes per sample."""
        return 2 if self is PcmSampleFormat.INT16 else 4


@dataclass(frozen=True, slots=True)
class PcmAudio:
    """One rendered chunk: raw mono PCM at the model's native sample rate."""

    samples: bytes
    sample_rate: int
    sample_format: PcmSampleFormat = PcmSampleFormat.INT16

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.samples), bytes):
            raise TypeError("samples must be bytes")
        if not isinstance(cast(object, self.sample_format), PcmSampleFormat):
            raise TypeError("sample_format must be a PcmSampleFormat")
        if type(self.sample_rate) is not int or self.sample_rate <= 0:
            raise ValueError("sample_rate must be a positive integer")
        if not self.samples or len(self.samples) % self.sample_format.width:
            raise ValueError("samples must hold at least one whole sample")

    @property
    def frame_count(self) -> int:
        """Number of mono samples."""
        return len(self.samples) // self.sample_format.width

    @property
    def duration_seconds(self) -> float:
        """Playback length at the native sample rate."""
        return self.frame_count / self.sample_rate


@runtime_checkable
class SpeechSynthesisProvider(Protocol):
    """Render one text chunk to PCM with a model of this engine.

    ``model`` is always a descriptor of this engine with the ``synthesis``
    capability. Failures are :class:`SynthesisError`; engines poll
    ``cancellation`` while rendering and stop with ``cancelled``.
    """

    def describe(self) -> SynthesisProviderInfo:
        """Return the engine identity and declared capabilities."""
        ...

    def voices(self, model: ModelDescriptor) -> tuple[Voice, ...]:
        """Return the voices of an installed model, stable per revision."""
        ...

    def languages(self, model: ModelDescriptor) -> tuple[str, ...]:
        """Return the languages the model can speak (may be empty if unknown)."""
        ...

    def requirements(self, model: ModelDescriptor) -> SynthesisRequirements:
        """Return runtime readiness and resource hints for the model."""
        ...

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
        """Render one chunk; never longer than ``describe().max_chunk_chars``."""
        ...

    def close(self) -> None:
        """Release engine resources; calling it again is a no-op."""
        ...


__all__ = [
    "PcmAudio",
    "PcmSampleFormat",
    "SpeechSynthesisProvider",
    "SynthesisCancellationToken",
    "SynthesisError",
    "SynthesisFailureCode",
    "SynthesisLocality",
    "SynthesisProgressCallback",
    "SynthesisProviderInfo",
    "SynthesisRequirements",
]
