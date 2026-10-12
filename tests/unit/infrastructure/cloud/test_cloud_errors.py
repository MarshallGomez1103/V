"""Failure shared by the cloud transcription adapters."""

from __future__ import annotations

from voz.application.ports.transcription import TranscriptionFailureCode
from voz.infrastructure.cloud._errors import invalid_audio_error


def test_invalid_audio_error_has_stable_code_and_message() -> None:
    error = invalid_audio_error()
    assert error.code is TranscriptionFailureCode.INVALID_AUDIO
    assert error.user_message == "The selected audio is invalid."
    assert not error.retryable
