"""Tests for Faster Whisper fast and quality descriptors."""

from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    ProcessingProfileName,
)
from voz.infrastructure.asr.catalog import (
    faster_whisper_fast_descriptor,
    faster_whisper_quality_descriptor,
)


def test_fast_profile_uses_turbo_and_gpu_first_precisions() -> None:
    descriptor = faster_whisper_fast_descriptor(revision="a" * 40)

    assert descriptor.model_id == "turbo"
    assert descriptor.source == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    assert descriptor.revision == "a" * 40
    assert descriptor.profile is not None
    assert descriptor.profile.name is ProcessingProfileName.FAST
    assert descriptor.profile.gpu_precisions == (
        ComputePrecision.FLOAT16,
        ComputePrecision.INT8_FLOAT16,
    )
    assert descriptor.supports(ModelCapability.GPU)


def test_quality_profile_uses_large_v3_and_preserves_revision() -> None:
    descriptor = faster_whisper_quality_descriptor(revision="b" * 40)

    assert descriptor.model_id == "large-v3"
    assert descriptor.source == "Systran/faster-whisper-large-v3"
    assert descriptor.revision == "b" * 40
    assert descriptor.profile is not None
    assert descriptor.profile.name is ProcessingProfileName.QUALITY
    assert descriptor.profile.cpu_precision is ComputePrecision.INT8
