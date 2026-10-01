"""Namespaced model keys: ``"<provider_id>:<model_id>"`` (MODELS-UI-002).

Bare model ids collide across providers (``small`` exists in faster-whisper and
whisper.cpp), so the model APIs address models by key. A bare id keeps meaning
faster-whisper for backward compatibility.
"""

from __future__ import annotations

from voz.domain.entities.model_descriptor import ModelDescriptor

DEFAULT_PROVIDER_ID = "faster-whisper"


def model_key(descriptor: ModelDescriptor) -> str:
    return f"{descriptor.provider_id}:{descriptor.model_id}"


def normalize_key(key: str) -> str:
    """Return the full key; an id without ``:`` belongs to faster-whisper."""
    return key if ":" in key else f"{DEFAULT_PROVIDER_ID}:{key}"


__all__ = ["DEFAULT_PROVIDER_ID", "model_key", "normalize_key"]
