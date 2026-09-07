"""Faster Whisper descriptors whose upstream revision is supplied explicitly."""

from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)

_CAPABILITIES = frozenset(
    {
        ModelCapability.TRANSCRIPTION,
        ModelCapability.TRANSLATION,
        ModelCapability.LANGUAGE_DETECTION,
        ModelCapability.CPU,
        ModelCapability.GPU,
    }
)


def faster_whisper_fast_descriptor(*, revision: str | None = None) -> ModelDescriptor:
    """Build the initial turbo profile without inventing an upstream revision."""
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="turbo",
        display_name="Faster Whisper Turbo (fast)",
        capabilities=_CAPABILITIES,
        source="mobiuslabsgmbh/faster-whisper-large-v3-turbo" if revision else None,
        revision=revision,
        profile=ProcessingProfile(
            name=ProcessingProfileName.FAST,
            device_preference=DevicePreference.GPU_PREFERRED,
            gpu_precisions=(
                ComputePrecision.FLOAT16,
                ComputePrecision.INT8_FLOAT16,
            ),
            cpu_precision=ComputePrecision.INT8,
        ),
    )


def faster_whisper_quality_descriptor(
    *, revision: str | None = None
) -> ModelDescriptor:
    """Build the initial large-v3 quality profile with pinned provenance."""
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="large-v3",
        display_name="Faster Whisper Large v3 (quality)",
        capabilities=_CAPABILITIES,
        source="Systran/faster-whisper-large-v3" if revision else None,
        revision=revision,
        profile=ProcessingProfile(
            name=ProcessingProfileName.QUALITY,
            device_preference=DevicePreference.GPU_PREFERRED,
            gpu_precisions=(ComputePrecision.FLOAT16,),
            cpu_precision=ComputePrecision.INT8,
        ),
    )


__all__ = [
    "faster_whisper_fast_descriptor",
    "faster_whisper_quality_descriptor",
]
