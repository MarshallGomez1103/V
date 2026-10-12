"""What the user asked a speech synthesis engine to say (ADR-0010)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Final, cast

from voz.domain.entities._validation import require_non_blank

# ponytail: one flat cap instead of per-engine limits. 20 000 characters is about
# 20 minutes of speech (~1 000 characters per minute), ~55 MB of PCM16 mono at
# 24 kHz: long enough for an article or a chapter, small enough to hold in memory
# and to finish on a laptop CPU. Long text is chunked by V (V2-04), so engines
# never see this length. Ceiling: a per-model limit from the catalog if a user
# needs a whole book in one job.
MAX_SYNTHESIS_TEXT_CHARS: Final = 20_000
MIN_SYNTHESIS_SPEED: Final = 0.5
MAX_SYNTHESIS_SPEED: Final = 2.0


class SynthesisOutputFormat(StrEnum):
    """Output contract of every engine: WAV, PCM signed 16-bit LE, mono."""

    WAV_PCM16_MONO = "wav_pcm16_mono"


def _require_text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("synthesis text must be a string")
    text = value.strip()
    if not text:
        raise ValueError("synthesis text must not be blank")
    if len(text) > MAX_SYNTHESIS_TEXT_CHARS:
        raise ValueError(
            f"synthesis text must have at most {MAX_SYNTHESIS_TEXT_CHARS} characters"
        )
    if "\x00" in text:
        raise ValueError("synthesis text must not contain NUL characters")
    return text


def _require_speed(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("synthesis speed must be a real number")
    if not isfinite(value) or not MIN_SYNTHESIS_SPEED <= value <= MAX_SYNTHESIS_SPEED:
        raise ValueError(
            f"synthesis speed must be between {MIN_SYNTHESIS_SPEED} "
            f"and {MAX_SYNTHESIS_SPEED}"
        )
    return float(value)


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """Immutable synthesis input; text is stored trimmed.

    The sample rate is not a request option: it is a property of the model.
    """

    text: str
    provider_id: str
    model_id: str
    voice_id: str
    model_revision: str | None = None
    """Pinned revision of the model; ``None`` for user-added models."""
    language: str | None = None
    speed: float = 1.0
    output_format: SynthesisOutputFormat = SynthesisOutputFormat.WAV_PCM16_MONO

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _require_text(self.text))
        for name in ("provider_id", "model_id", "voice_id"):
            object.__setattr__(
                self, name, require_non_blank(getattr(self, name), field=name)
            )
        for name in ("model_revision", "language"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_non_blank(value, field=name))
        object.__setattr__(self, "speed", _require_speed(self.speed))
        if not isinstance(cast(object, self.output_format), SynthesisOutputFormat):
            raise TypeError("output_format must be a SynthesisOutputFormat")
