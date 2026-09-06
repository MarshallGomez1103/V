"""Local speech-recognition adapters."""

from voz.infrastructure.asr.catalog import (
    faster_whisper_fast_descriptor,
    faster_whisper_quality_descriptor,
)
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe

__all__ = [
    "CTranslate2HardwareProbe",
    "FasterWhisperProvider",
    "faster_whisper_fast_descriptor",
    "faster_whisper_quality_descriptor",
]
