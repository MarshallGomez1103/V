"""Named, versioned decoding parameters so a transcription can be repeated."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import cast

_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}", re.ASCII)


def _finite(value: object, *, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return number


def _integer(value: object, *, field: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return value


@dataclass(frozen=True, slots=True)
class VadSettings:
    """Voice activity detection knobs (Silero VAD in Faster Whisper)."""

    threshold: float = 0.5
    min_speech_duration_ms: int = 0
    min_silence_duration_ms: int = 2000
    speech_pad_ms: int = 400

    def __post_init__(self) -> None:
        _finite(self.threshold, field="vad.threshold", low=0.01, high=0.99)
        _integer(
            self.min_speech_duration_ms,
            field="vad.min_speech_duration_ms",
            low=0,
            high=10_000,
        )
        _integer(
            self.min_silence_duration_ms,
            field="vad.min_silence_duration_ms",
            low=50,
            high=30_000,
        )
        _integer(self.speech_pad_ms, field="vad.speech_pad_ms", low=0, high=5_000)

    def to_dict(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "min_speech_duration_ms": self.min_speech_duration_ms,
            "min_silence_duration_ms": self.min_silence_duration_ms,
            "speech_pad_ms": self.speech_pad_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> VadSettings:
        # Field validation lives in __post_init__; the casts only satisfy typing.
        return cls(
            threshold=cast(float, data.get("threshold")),
            min_speech_duration_ms=cast(int, data.get("min_speech_duration_ms")),
            min_silence_duration_ms=cast(int, data.get("min_silence_duration_ms")),
            speech_pad_ms=cast(int, data.get("speech_pad_ms")),
        )


@dataclass(frozen=True, slots=True)
class QualityProfile:
    """Immutable decoding recipe. Changing a value means a new ``version``.

    A job stores the whole profile (not just its name), so repeating the job
    later uses exactly the same parameters even if the built-in recipes change.
    ``vad=None`` means VAD is off.
    """

    name: str
    version: int
    beam_size: int
    temperature: tuple[float, ...]
    condition_on_previous_text: bool
    no_speech_threshold: float
    vad: VadSettings | None = None

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.name), str) or not _NAME.fullmatch(
            self.name
        ):
            raise ValueError("name must be a short lowercase identifier")
        _integer(self.version, field="version", low=1, high=10_000)
        _integer(self.beam_size, field="beam_size", low=1, high=10)
        raw_temperature = cast(object, self.temperature)
        if not isinstance(raw_temperature, tuple) or not raw_temperature:
            raise ValueError("temperature must be a non-empty tuple")
        for value in cast(tuple[object, ...], raw_temperature):
            _finite(value, field="temperature", low=0.0, high=1.0)
        if type(self.condition_on_previous_text) is not bool:
            raise TypeError("condition_on_previous_text must be a bool")
        _finite(
            self.no_speech_threshold, field="no_speech_threshold", low=0.0, high=1.0
        )
        if self.vad is not None and not isinstance(cast(object, self.vad), VadSettings):
            raise TypeError("vad must be VadSettings or None")

    def to_dict(self) -> dict[str, object]:
        """Stable JSON-able form stored with the job and shown by the API."""
        return {
            "name": self.name,
            "version": self.version,
            "beam_size": self.beam_size,
            "temperature": list(self.temperature),
            "condition_on_previous_text": self.condition_on_previous_text,
            "no_speech_threshold": self.no_speech_threshold,
            "vad": None if self.vad is None else self.vad.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> QualityProfile:
        """Rebuild (and re-validate) a stored profile; raises on bad data."""
        raw_temperature = data.get("temperature")
        if not isinstance(raw_temperature, list):
            raise TypeError("temperature must be a list")
        raw_vad = data.get("vad")
        if raw_vad is not None and not isinstance(raw_vad, dict):
            raise TypeError("vad must be an object or null")
        return cls(
            name=cast(str, data.get("name")),
            version=cast(int, data.get("version")),
            beam_size=cast(int, data.get("beam_size")),
            temperature=tuple(cast(list[float], raw_temperature)),
            condition_on_previous_text=cast(
                bool, data.get("condition_on_previous_text")
            ),
            no_speech_threshold=cast(float, data.get("no_speech_threshold")),
            vad=None
            if raw_vad is None
            else VadSettings.from_dict(cast(dict[str, object], raw_vad)),
        )


__all__ = ["QualityProfile", "VadSettings"]
