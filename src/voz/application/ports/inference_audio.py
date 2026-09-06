"""Path-free access to one inference-ready normalized audio asset."""

from contextlib import AbstractContextManager
from enum import StrEnum
from typing import BinaryIO, Protocol, runtime_checkable

from voz.application.ports.transcription import TranscriptionClip


class InferenceAudioFailureCode(StrEnum):
    """Stable failures for reopening a normalized derivative."""

    NOT_FOUND = "inference_audio_not_found"
    INVALID_AUDIO = "inference_audio_invalid"
    UNSAFE_STORAGE_PATH = "inference_audio_unsafe_storage_path"
    IO_ERROR = "inference_audio_io_error"


class InferenceAudioError(RuntimeError):
    """Path-safe failure raised by an inference-audio adapter."""

    def __init__(
        self,
        code: InferenceAudioFailureCode,
        user_message: str,
    ) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@runtime_checkable
class InferenceAudioSource(Protocol):
    """Open a fresh descriptor for each recoverable ASR chunk."""

    def open(
        self,
        clip: TranscriptionClip | None = None,
    ) -> AbstractContextManager[BinaryIO]:
        """Open all or one bounded PCM clip without returning its host path."""
        ...


__all__ = [
    "InferenceAudioError",
    "InferenceAudioFailureCode",
    "InferenceAudioSource",
]
