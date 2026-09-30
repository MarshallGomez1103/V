"""Local speaker-diarization adapters (ADR-0007)."""

from voz.infrastructure.diarization.models import (
    DiarizationModelPaths,
    DiarizationModelStore,
)
from voz.infrastructure.diarization.sherpa import SherpaOnnxDiarizationProvider

__all__ = [
    "DiarizationModelPaths",
    "DiarizationModelStore",
    "SherpaOnnxDiarizationProvider",
]
