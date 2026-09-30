"""Visible, never automatic, suggestion to try whisper.cpp instead of Faster Whisper."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from voz.application.ports.transcription_options import RuntimeAvailability

WHISPER_CPP_PROVIDER_ID = "whisper-cpp"


class ProviderSuggestionReason(StrEnum):
    """Stable codes for the UI; they explain why whisper.cpp is suggested."""

    FASTER_WHISPER_RUNTIME_MISSING = "faster_whisper_runtime_missing"
    FASTER_WHISPER_NO_CUDA = "faster_whisper_no_cuda"


@dataclass(frozen=True, slots=True)
class ProviderSuggestion:
    """A hint only: the user (or job selection) still chooses the provider."""

    provider_id: str
    reason: ProviderSuggestionReason


def suggest_whisper_cpp(
    *,
    faster_whisper: RuntimeAvailability,
    whisper_cpp_available: bool,
) -> ProviderSuggestion | None:
    """Return a local whisper.cpp suggestion when Faster Whisper cannot shine.

    Pure policy: it never switches provider and never proposes a cloud provider.
    Unknown hardware (no probe data) yields no suggestion.
    """
    if not whisper_cpp_available:
        return None
    if not faster_whisper.available:
        return ProviderSuggestion(
            WHISPER_CPP_PROVIDER_ID,
            ProviderSuggestionReason.FASTER_WHISPER_RUNTIME_MISSING,
        )
    hardware = faster_whisper.hardware
    if hardware is not None and not hardware.cuda_compute_types:
        return ProviderSuggestion(
            WHISPER_CPP_PROVIDER_ID,
            ProviderSuggestionReason.FASTER_WHISPER_NO_CUDA,
        )
    return None


__all__ = [
    "WHISPER_CPP_PROVIDER_ID",
    "ProviderSuggestion",
    "ProviderSuggestionReason",
    "suggest_whisper_cpp",
]
