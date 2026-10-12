"""Speech synthesis engines (ADR-0010); engine types stay private to this package."""

from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
    fake_tts_descriptor,
)

__all__ = [
    "FAKE_TTS_PROVIDER_ID",
    "FakeSpeechSynthesisProvider",
    "fake_tts_descriptor",
]
