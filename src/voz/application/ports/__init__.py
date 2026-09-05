"""Application ports exposed without infrastructure dependencies."""

from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
    MediaNormalizationPort,
    MediaNormalizationProgress,
    MediaNormalizationProgressCallback,
    NormalizedAudio,
)
from voz.application.ports.media_probe import (
    MediaProbeError,
    MediaProbeFailureCode,
    MediaProbePort,
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)
from voz.application.ports.media_storage import (
    ImportedOriginal,
    MediaStorageError,
    MediaStorageErrorCode,
    MediaStoragePort,
)
from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    SegmentRepository,
    SpeakerRepository,
    SpeakerTurnRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
    WordRepository,
)

__all__ = [
    "ImportedOriginal",
    "MediaAssetRepository",
    "MediaNormalizationCancellationToken",
    "MediaNormalizationError",
    "MediaNormalizationFailureCode",
    "MediaNormalizationPort",
    "MediaNormalizationProgress",
    "MediaNormalizationProgressCallback",
    "MediaProbeError",
    "MediaProbeFailureCode",
    "MediaProbePort",
    "MediaProbeResult",
    "MediaStorageError",
    "MediaStorageErrorCode",
    "MediaStoragePort",
    "MediaStreamKind",
    "NormalizedAudio",
    "ProbedMediaStream",
    "ProjectRepository",
    "SegmentRepository",
    "SpeakerRepository",
    "SpeakerTurnRepository",
    "TranscriptRepository",
    "TranscriptionJobRepository",
    "WordRepository",
]
