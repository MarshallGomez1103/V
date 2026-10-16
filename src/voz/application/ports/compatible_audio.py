"""Transport-independent contracts for local compatible audio requests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from voz.application.ports.transcription import TranscriptionSegment


@dataclass(frozen=True, slots=True)
class CompatibleModel:
    id: str
    owned_by: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompatibleTranscription:
    source: Path
    model: str
    language: str | None = None
    prompt: str | None = None


@dataclass(frozen=True, slots=True)
class CompatibleTranscript:
    text: str
    language: str | None
    duration_seconds: float
    segments: tuple[TranscriptionSegment, ...]


@dataclass(frozen=True, slots=True)
class CompatibleSpeech:
    model: str
    input: str
    voice: str
    speed: float = 1.0


class CompatibleAudioError(Exception):
    """Only fixed safe messages supplied by the service cross this boundary."""

    def __init__(
        self, code: str, message: str, status: int = 400, param: str | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.param = param
        super().__init__(message)


class CompatibleAudioService(Protocol):
    def models(self) -> tuple[CompatibleModel, ...]: ...

    def transcribe(
        self,
        request: CompatibleTranscription,
        *,
        cancelled: Callable[[], bool],
    ) -> CompatibleTranscript: ...

    def speech(
        self, request: CompatibleSpeech, *, cancelled: Callable[[], bool]
    ) -> BinaryIO:
        """Return a WAV handle whose ownership and closing belong to the caller."""
        ...
