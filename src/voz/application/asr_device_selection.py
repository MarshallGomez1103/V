"""Deterministic, observable selection of an ASR execution device."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
)


class ComputeDevice(StrEnum):
    CUDA = "cuda"
    CPU = "cpu"


class FallbackReason(StrEnum):
    CUDA_UNAVAILABLE = "cuda_unavailable"
    CUDA_PRECISION_UNSUPPORTED = "cuda_precision_unsupported"


@dataclass(frozen=True, slots=True)
class HardwareCapabilities:
    """Compute types reported by the installed local runtime."""

    cuda_compute_types: frozenset[ComputePrecision]
    cpu_compute_types: frozenset[ComputePrecision]


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    """Selected device plus an explicit reason whenever CPU is a fallback."""

    device: ComputeDevice
    precision: ComputePrecision
    fallback_reason: FallbackReason | None = None


def select_execution(
    profile: ProcessingProfile,
    hardware: HardwareCapabilities,
) -> ExecutionDecision:
    """Resolve a profile deterministically without hiding GPU fallback."""
    if profile.device_preference is DevicePreference.GPU_PREFERRED:
        for precision in profile.gpu_precisions:
            if precision in hardware.cuda_compute_types:
                return ExecutionDecision(ComputeDevice.CUDA, precision)
        reason = (
            FallbackReason.CUDA_UNAVAILABLE
            if not hardware.cuda_compute_types
            else FallbackReason.CUDA_PRECISION_UNSUPPORTED
        )
    else:
        reason = None

    if profile.cpu_precision in hardware.cpu_compute_types:
        return ExecutionDecision(
            ComputeDevice.CPU,
            profile.cpu_precision,
            fallback_reason=reason,
        )
    raise TranscriptionError(
        TranscriptionFailureCode.PROVIDER_FAILED,
        "The local runtime has no supported compute type for this profile.",
    )


__all__ = [
    "ComputeDevice",
    "ExecutionDecision",
    "FallbackReason",
    "HardwareCapabilities",
    "select_execution",
]
