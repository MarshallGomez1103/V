"""Provider-neutral model identity and capability metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from unicodedata import category

from voz.domain.entities.processing_profile import ProcessingProfile

_SAFE_PROVIDER_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
_IMMUTABLE_REVISION = re.compile(r"[0-9a-f]{40}", re.ASCII)


class ModelCapability(StrEnum):
    """Capabilities that VOZ may use without knowing provider internals.

    Values are persisted (manifests) and serialized (``GET /api/models``): never
    rename one, only add. ``synthesis``, ``alignment`` and ``wake_word`` are part
    of the vocabulary (ADR-0010 section 8) but no engine implements them yet, so
    no catalog entry may declare them (see ``ENGINE_CAPABILITIES``).
    """

    TRANSCRIPTION = "transcription"
    TRANSLATION = "translation"
    WORD_TIMESTAMPS = "word_timestamps"
    DIARIZATION = "diarization"
    SYNTHESIS = "synthesis"
    ALIGNMENT = "alignment"
    WAKE_WORD = "wake_word"
    LANGUAGE_DETECTION = "language_detection"
    REALTIME = "realtime"
    GPU = "gpu"
    CPU = "cpu"


def _require_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _require_trimmed_text(
    value: object,
    *,
    field_name: str,
    maximum_length: int,
) -> str:
    text = _require_string(value, field_name=field_name)
    if not text or text != text.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    if len(text) > maximum_length:
        raise ValueError(f"{field_name} is too long")
    if any(category(character).startswith("C") for character in text):
        raise ValueError(f"{field_name} cannot contain control characters")
    return text


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Immutable identity and capabilities shared by all model providers."""

    provider_id: str
    model_id: str
    display_name: str
    capabilities: frozenset[ModelCapability]
    source: str | None = None
    revision: str | None = None
    profile: ProcessingProfile | None = None

    def __post_init__(self) -> None:
        provider_id = _require_string(self.provider_id, field_name="provider_id")
        if not provider_id or provider_id != provider_id.strip():
            raise ValueError("provider_id must be a non-empty trimmed identifier")
        if _SAFE_PROVIDER_ID.fullmatch(provider_id) is None:
            raise ValueError("provider_id must be a safe identifier")

        object.__setattr__(
            self,
            "model_id",
            _require_trimmed_text(
                self.model_id,
                field_name="model_id",
                maximum_length=255,
            ),
        )
        object.__setattr__(
            self,
            "display_name",
            _require_trimmed_text(
                self.display_name,
                field_name="display_name",
                maximum_length=128,
            ),
        )

        raw_capabilities = cast(object, self.capabilities)
        if not isinstance(raw_capabilities, frozenset):
            raise TypeError("capabilities must be a frozenset")
        capabilities = cast(frozenset[object], raw_capabilities)
        if not capabilities:
            raise ValueError("capabilities must contain at least one capability")
        if any(not isinstance(item, ModelCapability) for item in capabilities):
            raise TypeError("capabilities must contain only ModelCapability instances")

        if (self.source is None) != (self.revision is None):
            raise ValueError("source and revision must be provided together")
        if self.source is not None:
            object.__setattr__(
                self,
                "source",
                _require_trimmed_text(
                    self.source,
                    field_name="source",
                    maximum_length=512,
                ),
            )
            revision = _require_trimmed_text(
                self.revision,
                field_name="revision",
                maximum_length=255,
            )
            if _IMMUTABLE_REVISION.fullmatch(revision) is None:
                raise ValueError("revision must be a 40-character lowercase commit SHA")
            object.__setattr__(self, "revision", revision)
        raw_profile = cast(object, self.profile)
        if raw_profile is not None and not isinstance(
            raw_profile,
            ProcessingProfile,
        ):
            raise TypeError("profile must be a ProcessingProfile or None")

    @property
    def identity(self) -> tuple[str, str]:
        """Return the registry-safe provider/model composite identity."""

        return (self.provider_id, self.model_id)

    def supports(self, capability: ModelCapability) -> bool:
        """Return whether this model advertises a canonical capability."""

        return capability in self.capabilities

    @property
    def provenance(self) -> tuple[str, str] | None:
        """Return pinned upstream identity when this descriptor is installable."""

        if self.source is None or self.revision is None:
            return None
        return (self.source, self.revision)


__all__ = ["ModelCapability", "ModelDescriptor"]
