"""Failures shared by the cloud transcription adapters."""

from __future__ import annotations

from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)


def invalid_audio_error() -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.INVALID_AUDIO, "The selected audio is invalid."
    )
