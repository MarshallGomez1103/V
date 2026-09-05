"""Application contract for inspecting media without exposing host paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO, Protocol, runtime_checkable

_SAFE_METADATA_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}", re.ASCII)


class MediaStreamKind(StrEnum):
    """Media stream families relevant to the transcription workspace."""

    AUDIO = "audio"
    VIDEO = "video"


@dataclass(frozen=True, slots=True)
class ProbedMediaStream:
    """Whitelisted, UI-safe metadata for one audio or video stream."""

    index: int
    kind: MediaStreamKind
    codec_name: str
    is_decodable: bool
    sample_rate_hz: int | None = None
    channels: int | None = None

    def __post_init__(self) -> None:
        if type(self.index) is bool or self.index < 0:
            raise ValueError("index must be a non-negative integer")

        codec_name = self.codec_name.strip().lower()
        if _SAFE_METADATA_TOKEN.fullmatch(codec_name) is None:
            raise ValueError("codec_name must be a safe codec identifier")
        object.__setattr__(self, "codec_name", codec_name)

        if type(self.is_decodable) is not bool:
            raise TypeError("is_decodable must be a boolean")

        for field_name in ("sample_rate_hz", "channels"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{field_name} must be a positive integer")

        if self.kind is MediaStreamKind.VIDEO and (
            self.sample_rate_hz is not None or self.channels is not None
        ):
            raise ValueError("video streams cannot contain audio metadata")


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    """Safe probe result; deliberately contains no source or storage path."""

    format_names: tuple[str, ...]
    streams: tuple[ProbedMediaStream, ...]
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        normalized_formats: list[str] = []
        for format_name in self.format_names:
            normalized = format_name.strip().lower()
            if _SAFE_METADATA_TOKEN.fullmatch(normalized) is None:
                raise ValueError("format_names must contain safe identifiers")
            normalized_formats.append(normalized)
        object.__setattr__(self, "format_names", tuple(normalized_formats))

        if self.duration_ms is not None and (
            type(self.duration_ms) is not int or self.duration_ms <= 0
        ):
            raise ValueError("duration_ms must be a positive integer")

        if not any(
            stream.kind is MediaStreamKind.AUDIO and stream.is_decodable
            for stream in self.streams
        ):
            raise ValueError("a probe result requires decodable audio")

    @property
    def audio_streams(self) -> tuple[ProbedMediaStream, ...]:
        """Return audio streams while preserving their ffprobe order."""

        return tuple(
            stream for stream in self.streams if stream.kind is MediaStreamKind.AUDIO
        )


class MediaProbeFailureCode(StrEnum):
    """Stable failure categories suitable for use-case and API translation."""

    TOOL_UNAVAILABLE = "media_probe_tool_unavailable"
    TIMED_OUT = "media_probe_timed_out"
    INVALID_RESPONSE = "media_probe_invalid_response"
    INVALID_MEDIA = "media_probe_invalid_media"
    NO_DECODABLE_AUDIO = "media_probe_no_decodable_audio"


class MediaProbeError(RuntimeError):
    """Typed probe failure with a user-safe message and no source path."""

    def __init__(self, code: MediaProbeFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@runtime_checkable
class MediaProbePort(Protocol):
    """Inspect an already-open immutable original and return safe metadata."""

    def probe(self, source: BinaryIO) -> MediaProbeResult:
        """Inspect a seekable descriptor without relying on a host path."""
        ...


__all__ = [
    "MediaProbeError",
    "MediaProbeFailureCode",
    "MediaProbePort",
    "MediaProbeResult",
    "MediaStreamKind",
    "ProbedMediaStream",
]
