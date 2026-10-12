"""Pipe protocol between VOZ and a speech synthesis child process (ADR-0010).

Generalizes ``diarization/worker.py`` for TTS. The request is ONE JSON line on
the child's stdin (the user's text travels only inside it, never in argv and
never as a command). The child answers on stdout, one record per line:

* ``V P <fraction>``: progress of the chunk, ``0.0``-``1.0``;
* ``V A <n_bytes> <sample_rate> <format>``: followed by exactly ``n_bytes`` of
  raw little-endian mono PCM (``format`` is ``int16`` or ``float32``);
* ``V END``: the chunk is complete;
* ``V ERR <code> <message>``: the chunk failed (the message is sanitized).

Any other line (native library logs) is ignored; so is a malformed ``V P`` or
``V ERR``. A malformed ``V A`` cannot be skipped without losing the byte
framing, so it is a :class:`ProtocolError`. Pure functions: no processes here.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import IO, Final

from voz.application.ports.speech_synthesis import PcmAudio, PcmSampleFormat

PREFIX: Final = "V"
MAX_PCM_BYTES: Final = 256 * 1024 * 1024
MAX_LINE_BYTES: Final = 4096
MAX_MESSAGE_CHARS: Final = 200
MAX_SAMPLE_RATE: Final = 384_000
_CODE = re.compile(r"[a-z][a-z0-9_]{0,39}", re.ASCII)
_PATH_LIKE = re.compile(r"\S*[/\\]\S*")


class ProtocolError(ValueError):
    """The peer broke the framing; the stream cannot be trusted any more."""


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    """What the child needs to render one chunk."""

    family: str
    files: Mapping[str, str]
    voice_id: str
    speed: float
    text: str
    num_threads: int


@dataclass(frozen=True, slots=True)
class Progress:
    fraction: float


@dataclass(frozen=True, slots=True)
class AudioChunk:
    audio: PcmAudio


@dataclass(frozen=True, slots=True)
class End:
    pass


@dataclass(frozen=True, slots=True)
class WorkerError:
    code: str
    message: str


WorkerEvent = Progress | AudioChunk | End | WorkerError


@dataclass(frozen=True, slots=True)
class _AudioHeader:
    n_bytes: int
    sample_rate: int
    sample_format: PcmSampleFormat


# --- request (parent -> child) -------------------------------------------------


def encode_request(request: WorkerRequest) -> bytes:
    """One newline-terminated JSON line; ASCII-escaped so it can never span lines."""
    payload = {
        "family": request.family,
        "files": dict(request.files),
        "voice_id": request.voice_id,
        "speed": request.speed,
        "text": request.text,
        "num_threads": request.num_threads,
    }
    return json.dumps(payload, ensure_ascii=True, allow_nan=False).encode() + b"\n"


def decode_request(line: bytes | str) -> WorkerRequest:
    """Parse and validate a request line; every defect is a ``ProtocolError``."""
    try:
        data = json.loads(line)
    except (ValueError, UnicodeDecodeError) as error:
        raise ProtocolError("the request is not valid JSON") from error
    if not isinstance(data, dict):
        raise ProtocolError("the request must be a JSON object")
    fields: dict[str, object] = {str(key): value for key, value in data.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    family, voice_id, text = (fields.get(k) for k in ("family", "voice_id", "text"))
    files, speed, threads = (fields.get(k) for k in ("files", "speed", "num_threads"))
    if not (isinstance(family, str) and family.strip()):
        raise ProtocolError("family must be a non-blank string")
    if not (isinstance(voice_id, str) and voice_id.strip()):
        raise ProtocolError("voice_id must be a non-blank string")
    if not (isinstance(text, str) and text.strip()):
        raise ProtocolError("text must be a non-blank string")
    if not isinstance(files, dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in files.items()  # pyright: ignore[reportUnknownVariableType]
    ):
        raise ProtocolError("files must map names to paths")
    if (
        isinstance(speed, bool)
        or not isinstance(speed, int | float)
        or not math.isfinite(speed)
        or speed <= 0
    ):
        raise ProtocolError("speed must be a positive number")
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ProtocolError("num_threads must be a positive integer")
    return WorkerRequest(
        family=family,
        files={str(k): str(v) for k, v in files.items()},  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        voice_id=voice_id,
        speed=float(speed),
        text=text,
        num_threads=threads,
    )


# --- response (child -> parent) ------------------------------------------------


def sanitize_message(message: object) -> str:
    """Single printable line, host paths redacted, bounded length."""
    text = " ".join(str(message).split())
    text = "".join(char for char in text if char.isprintable())
    return _PATH_LIKE.sub("<path>", text)[:MAX_MESSAGE_CHARS]


def encode_progress(fraction: float) -> bytes:
    return f"{PREFIX} P {min(1.0, max(0.0, fraction)):.6f}\n".encode()


def encode_audio(audio: PcmAudio) -> bytes:
    """Header line plus exactly ``len(audio.samples)`` bytes of PCM."""
    header = (
        f"{PREFIX} A {len(audio.samples)} {audio.sample_rate} "
        f"{audio.sample_format.value}\n"
    )
    return header.encode() + audio.samples


def encode_end() -> bytes:
    return f"{PREFIX} END\n".encode()


def encode_error(code: str, message: str = "") -> bytes:
    if not _CODE.fullmatch(code):
        raise ValueError("error code must be a lowercase identifier")
    text = sanitize_message(message)
    return f"{PREFIX} ERR {code}{' ' + text if text else ''}\n".encode()


def _parse_audio_header(fields: list[str]) -> _AudioHeader:
    try:
        if len(fields) != 5:
            raise ValueError
        n_bytes, sample_rate = int(fields[2]), int(fields[3])
        sample_format = PcmSampleFormat(fields[4])
    except ValueError as error:
        raise ProtocolError("malformed audio header") from error
    if not 0 < sample_rate <= MAX_SAMPLE_RATE:
        raise ProtocolError("audio sample rate out of range")
    if not 0 < n_bytes <= MAX_PCM_BYTES or n_bytes % sample_format.width:
        raise ProtocolError("audio length out of range")
    return _AudioHeader(n_bytes, sample_rate, sample_format)


def _read_line(stream: IO[bytes]) -> bytes | None:
    """Next line without its newline, ``None`` at EOF; overlong lines are dropped."""
    line = stream.readline(MAX_LINE_BYTES + 1)
    if not line:
        return None
    if line.endswith(b"\n"):
        return line.rstrip(b"\r\n")
    if len(line) <= MAX_LINE_BYTES:  # EOF inside a line: keep what arrived
        return line
    while True:  # overlong: it is not ours, discard up to its newline
        rest = stream.readline(MAX_LINE_BYTES)
        if not rest or rest.endswith(b"\n"):
            return b""


def _read_exact(stream: IO[bytes], count: int) -> bytes:
    parts: list[bytes] = []
    remaining = count
    while remaining:
        part = stream.read(remaining)
        if not part:
            raise ProtocolError("the stream ended inside the audio payload")
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)


def read_events(stream: IO[bytes]) -> Iterator[WorkerEvent]:
    """Yield events until ``END``/``ERR`` or EOF; PCM is read with exact length."""
    while (raw := _read_line(stream)) is not None:
        fields = raw.decode("utf-8", "replace").split()
        if len(fields) < 2 or fields[0] != PREFIX:
            continue  # native log noise
        kind = fields[1]
        if kind == "P" and len(fields) == 3:
            try:
                fraction = float(fields[2])
            except ValueError:
                continue
            if math.isfinite(fraction):
                yield Progress(min(1.0, max(0.0, fraction)))
        elif kind == "A":
            header = _parse_audio_header(fields)
            samples = _read_exact(stream, header.n_bytes)
            yield AudioChunk(
                PcmAudio(samples, header.sample_rate, header.sample_format)
            )
        elif kind == "END" and len(fields) == 2:
            yield End()
            return
        elif kind == "ERR" and len(fields) >= 3 and _CODE.fullmatch(fields[2]):
            yield WorkerError(fields[2], sanitize_message(" ".join(fields[3:])))
            return


__all__ = [
    "MAX_PCM_BYTES",
    "PREFIX",
    "AudioChunk",
    "End",
    "Progress",
    "ProtocolError",
    "WorkerError",
    "WorkerEvent",
    "WorkerRequest",
    "decode_request",
    "encode_audio",
    "encode_end",
    "encode_error",
    "encode_progress",
    "encode_request",
    "read_events",
    "sanitize_message",
]
