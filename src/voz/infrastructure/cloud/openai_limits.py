"""Versioned OpenAI transcription limits and prices (S11.04, S11.08).

These constants are a dated snapshot of the public documentation. They are
**not verified live**: VOZ never calls OpenAI to discover them. When OpenAI
changes a limit or price, bump ``LIMITS_DATE`` and the entry, or override
``max_upload_bytes`` / the price table at the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from voz.application.estimate_cloud_cost import CloudPrice
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor

PROVIDER_ID: Final = "openai"
LIMITS_DATE: Final = "2026-09-30"
LIMITS_SOURCE: Final = (
    "https://platform.openai.com/docs/guides/speech-to-text (no verificado en vivo)"
)
PRICE_SOURCE: Final = "https://platform.openai.com/pricing (no verificado en vivo)"
DEFAULT_MODEL_ID: Final = "whisper-1"
DIARIZE_MODEL_ID: Final = "gpt-4o-transcribe-diarize"


@dataclass(frozen=True, slots=True)
class OpenAIModelSpec:
    model_id: str
    display_name: str
    response_format: str
    max_upload_bytes: int
    usd_per_minute: Decimal
    diarized: bool = False


OPENAI_MODELS: Final = (
    OpenAIModelSpec(
        DEFAULT_MODEL_ID,
        "OpenAI Whisper (nube)",
        "verbose_json",
        25_000_000,  # documented "25 MB"; decimal reading is the safe one
        Decimal("0.006"),
    ),
    OpenAIModelSpec(
        DIARIZE_MODEL_ID,
        "OpenAI GPT-4o Transcribe Diarize (nube)",
        "diarized_json",
        25_000_000,  # documented "25 MB"; decimal reading is the safe one
        Decimal("0.006"),  # ponytail: assumed equal to gpt-4o-transcribe; unverified
        diarized=True,
    ),
)


def openai_spec(model_id: str) -> OpenAIModelSpec | None:
    return next((spec for spec in OPENAI_MODELS if spec.model_id == model_id), None)


def openai_descriptors() -> tuple[ModelDescriptor, ...]:
    """Cloud descriptors carry no source/revision: nothing is installed locally."""
    return tuple(
        ModelDescriptor(
            provider_id=PROVIDER_ID,
            model_id=spec.model_id,
            display_name=spec.display_name,
            capabilities=frozenset(
                {ModelCapability.TRANSCRIPTION, ModelCapability.LANGUAGE_DETECTION}
                | ({ModelCapability.DIARIZATION} if spec.diarized else set())
            ),
        )
        for spec in OPENAI_MODELS
    )


def openai_prices() -> dict[tuple[str, str], CloudPrice]:
    return {
        (PROVIDER_ID, spec.model_id): CloudPrice(
            spec.usd_per_minute, PRICE_SOURCE, LIMITS_DATE
        )
        for spec in OPENAI_MODELS
    }


__all__ = [
    "DEFAULT_MODEL_ID",
    "DIARIZE_MODEL_ID",
    "LIMITS_DATE",
    "LIMITS_SOURCE",
    "OPENAI_MODELS",
    "PRICE_SOURCE",
    "PROVIDER_ID",
    "OpenAIModelSpec",
    "openai_descriptors",
    "openai_prices",
    "openai_spec",
]
