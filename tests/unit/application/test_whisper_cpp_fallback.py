"""Fallback policy: visible suggestion only, never local-to-cloud, never silent."""

import pytest

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription_options import RuntimeAvailability
from voz.application.whisper_cpp_fallback import (
    ProviderSuggestion,
    ProviderSuggestionReason,
    suggest_whisper_cpp,
)
from voz.domain.entities.processing_profile import ComputePrecision


def _hardware(*cuda: ComputePrecision) -> HardwareCapabilities:
    return HardwareCapabilities(frozenset(cuda), frozenset({ComputePrecision.INT8}))


def test_suggests_whisper_cpp_when_faster_whisper_runtime_is_missing() -> None:
    suggestion = suggest_whisper_cpp(
        faster_whisper=RuntimeAvailability(False), whisper_cpp_available=True
    )

    assert suggestion == ProviderSuggestion(
        "whisper-cpp", ProviderSuggestionReason.FASTER_WHISPER_RUNTIME_MISSING
    )


def test_suggests_whisper_cpp_when_faster_whisper_has_no_cuda() -> None:
    suggestion = suggest_whisper_cpp(
        faster_whisper=RuntimeAvailability(True, _hardware()),
        whisper_cpp_available=True,
    )

    assert suggestion is not None
    assert suggestion.reason is ProviderSuggestionReason.FASTER_WHISPER_NO_CUDA


@pytest.mark.parametrize(
    "faster",
    [
        RuntimeAvailability(True, _hardware(ComputePrecision.FLOAT16)),
        RuntimeAvailability(True),  # unknown hardware is not a reason to switch
    ],
)
def test_keeps_faster_whisper_when_it_is_healthy(faster: RuntimeAvailability) -> None:
    assert (
        suggest_whisper_cpp(faster_whisper=faster, whisper_cpp_available=True) is None
    )


def test_no_suggestion_when_whisper_cpp_is_unavailable() -> None:
    assert (
        suggest_whisper_cpp(
            faster_whisper=RuntimeAvailability(False), whisper_cpp_available=False
        )
        is None
    )
