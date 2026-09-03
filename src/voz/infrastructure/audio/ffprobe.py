"""Subprocess adapter for the application media-probe port."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from voz.application.ports.media_probe import (
    MediaProbeError,
    MediaProbeFailureCode,
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)

_DECODER_LINE = re.compile(r"^\s*[AV][A-Z.]{5}\s+([a-zA-Z0-9_.-]+)(?:\s|$)")
_SAFE_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}", re.ASCII)
_UNUSABLE_CODEC_NAMES = frozenset({"none", "null", "unknown"})
_PROBE_ENTRIES = (
    "format=format_name,duration:"
    "stream=index,codec_name,codec_type,sample_rate,channels"
)


@dataclass(slots=True)
class FfprobeMediaProbe:
    """Inspect media with ffprobe using bounded, non-shell subprocess calls."""

    executable: str = "ffprobe"
    timeout_seconds: float = 15.0
    _decoder_names: frozenset[str] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValueError("executable must not be blank")
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def probe(self, source: Path) -> MediaProbeResult:
        """Return whitelisted metadata or a stable typed failure."""

        completed = self._run(
            [
                self.executable,
                "-v",
                "error",
                "-show_entries",
                _PROBE_ENTRIES,
                "-of",
                "json",
                str(source.absolute()),
            ]
        )
        if completed.returncode != 0:
            raise MediaProbeError(
                MediaProbeFailureCode.INVALID_MEDIA,
                "The selected file is not readable media.",
            )

        payload = _load_payload(completed.stdout)
        decoder_names = self._load_decoder_names()
        streams = _parse_streams(payload, decoder_names)
        if not any(
            stream.kind is MediaStreamKind.AUDIO and stream.is_decodable
            for stream in streams
        ):
            raise MediaProbeError(
                MediaProbeFailureCode.NO_DECODABLE_AUDIO,
                "The selected file has no decodable audio stream.",
            )

        raw_format = payload.get("format")
        format_data = (
            cast(dict[str, object], raw_format) if isinstance(raw_format, dict) else {}
        )
        return MediaProbeResult(
            format_names=_parse_format_names(format_data.get("format_name")),
            duration_ms=_parse_duration_ms(format_data.get("duration")),
            streams=streams,
        )

    def _load_decoder_names(self) -> frozenset[str]:
        if self._decoder_names is not None:
            return self._decoder_names

        completed = self._run([self.executable, "-v", "error", "-decoders"])
        if completed.returncode != 0:
            raise MediaProbeError(
                MediaProbeFailureCode.INVALID_RESPONSE,
                "The media inspection tool returned an invalid response.",
            )

        decoder_names = frozenset(
            match.group(1).lower()
            for line in completed.stdout.splitlines()
            if (match := _DECODER_LINE.match(line)) is not None
        )
        if not decoder_names:
            raise MediaProbeError(
                MediaProbeFailureCode.INVALID_RESPONSE,
                "The media inspection tool returned an invalid response.",
            )
        self._decoder_names = decoder_names
        return decoder_names

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise MediaProbeError(
                MediaProbeFailureCode.TOOL_UNAVAILABLE,
                "The media inspection tool is not installed.",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise MediaProbeError(
                MediaProbeFailureCode.TIMED_OUT,
                "Media inspection took too long.",
            ) from error
        except OSError as error:
            raise MediaProbeError(
                MediaProbeFailureCode.TOOL_UNAVAILABLE,
                "The media inspection tool could not be started.",
            ) from error


def _load_payload(stdout: str) -> dict[str, object]:
    try:
        payload: object = json.loads(stdout)
    except (json.JSONDecodeError, RecursionError) as error:
        raise MediaProbeError(
            MediaProbeFailureCode.INVALID_RESPONSE,
            "The media inspection tool returned an invalid response.",
        ) from error
    if not isinstance(payload, dict):
        raise MediaProbeError(
            MediaProbeFailureCode.INVALID_RESPONSE,
            "The media inspection tool returned an invalid response.",
        )
    return cast(dict[str, object], payload)


def _parse_streams(
    payload: dict[str, object],
    decoder_names: frozenset[str],
) -> tuple[ProbedMediaStream, ...]:
    raw_streams = payload.get("streams")
    if not isinstance(raw_streams, list):
        raise MediaProbeError(
            MediaProbeFailureCode.INVALID_RESPONSE,
            "The media inspection tool returned an invalid response.",
        )

    streams: list[ProbedMediaStream] = []
    for raw_stream in cast(list[object], raw_streams):
        if not isinstance(raw_stream, dict):
            continue
        stream = _parse_stream(cast(dict[str, object], raw_stream), decoder_names)
        if stream is not None:
            streams.append(stream)
    return tuple(streams)


def _parse_stream(
    raw_stream: dict[str, object],
    decoder_names: frozenset[str],
) -> ProbedMediaStream | None:
    raw_index = raw_stream.get("index")
    raw_kind = raw_stream.get("codec_type")
    raw_codec = raw_stream.get("codec_name")
    if (
        isinstance(raw_index, bool)
        or not isinstance(raw_index, int)
        or raw_index < 0
        or not isinstance(raw_kind, str)
        or not isinstance(raw_codec, str)
    ):
        return None

    try:
        kind = MediaStreamKind(raw_kind)
    except ValueError:
        return None

    codec_name = raw_codec.strip().lower()
    if codec_name in _UNUSABLE_CODEC_NAMES or _SAFE_TOKEN.fullmatch(codec_name) is None:
        return None

    return ProbedMediaStream(
        index=raw_index,
        kind=kind,
        codec_name=codec_name,
        is_decodable=codec_name in decoder_names,
        sample_rate_hz=(
            _parse_positive_int(raw_stream.get("sample_rate"))
            if kind is MediaStreamKind.AUDIO
            else None
        ),
        channels=(
            _parse_positive_int(raw_stream.get("channels"))
            if kind is MediaStreamKind.AUDIO
            else None
        ),
    )


def _parse_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _parse_duration_ms(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        seconds = Decimal(str(value))
    except InvalidOperation:
        return None
    if not seconds.is_finite() or seconds <= 0:
        return None
    milliseconds = int((seconds * 1000).to_integral_value(rounding=ROUND_HALF_UP))
    return milliseconds if milliseconds > 0 else None


def _parse_format_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        token
        for item in value.split(",")
        if (token := item.strip().lower()) and _SAFE_TOKEN.fullmatch(token) is not None
    )


__all__ = ["FfprobeMediaProbe"]
