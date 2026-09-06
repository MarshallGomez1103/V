"""Unit tests for explicit ASR device and compute selection."""

import pytest

from voz.application.asr_device_selection import (
    ComputeDevice,
    FallbackReason,
    HardwareCapabilities,
    select_execution,
)
from voz.application.ports.transcription import TranscriptionError
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)

PROFILE = ProcessingProfile(
    name=ProcessingProfileName.FAST,
    device_preference=DevicePreference.GPU_PREFERRED,
    gpu_precisions=(ComputePrecision.FLOAT16, ComputePrecision.INT8_FLOAT16),
    cpu_precision=ComputePrecision.INT8,
)


def test_prefers_first_supported_gpu_precision() -> None:
    decision = select_execution(
        PROFILE,
        HardwareCapabilities(
            cuda_compute_types=frozenset(
                {ComputePrecision.FLOAT16, ComputePrecision.INT8_FLOAT16}
            ),
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        ),
    )

    assert decision.device is ComputeDevice.CUDA
    assert decision.precision is ComputePrecision.FLOAT16
    assert decision.fallback_reason is None


def test_cuda_absence_falls_back_to_cpu_with_observable_reason() -> None:
    decision = select_execution(
        PROFILE,
        HardwareCapabilities(
            cuda_compute_types=frozenset(),
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        ),
    )

    assert decision.device is ComputeDevice.CPU
    assert decision.precision is ComputePrecision.INT8
    assert decision.fallback_reason is FallbackReason.CUDA_UNAVAILABLE


def test_incompatible_cuda_falls_back_with_distinct_reason() -> None:
    decision = select_execution(
        PROFILE,
        HardwareCapabilities(
            cuda_compute_types=frozenset({ComputePrecision.INT8}),
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        ),
    )

    assert decision.device is ComputeDevice.CPU
    assert decision.fallback_reason is FallbackReason.CUDA_PRECISION_UNSUPPORTED


def test_no_compatible_device_is_a_typed_failure() -> None:
    with pytest.raises(TranscriptionError, match="no supported compute type"):
        select_execution(
            PROFILE,
            HardwareCapabilities(
                cuda_compute_types=frozenset(),
                cpu_compute_types=frozenset(),
            ),
        )
