"""Experimental ONNX ASR transcription through one private child per call."""

from __future__ import annotations

import contextlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
import wave
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.asr.sherpa_onnx_options import (
    PROVIDER_ID,
    nemo_transducer_files,
    observed_language,
    whisper_files,
)
from voz.infrastructure.audio.media_args import NO_WINDOW
from voz.infrastructure.child_env import child_environment
from voz.infrastructure.process_tree import kill_tree

_MAX_AUDIO_BYTES = 256 * 1024**2
_MAX_RESULT_BYTES = 8 * 1024**2
_MAX_LINE_BYTES = 65_536


class ModelPathResolver(Protocol):
    def resolve_path(self, descriptor: ModelDescriptor) -> Path: ...


def _failure() -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.PROVIDER_FAILED,
        "The ONNX ASR provider could not process the audio.",
    )


def _invalid_audio() -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.INVALID_AUDIO, "The selected audio is invalid."
    )


def _cancelled(token: TranscriptionCancellationToken | None) -> None:
    if token is not None and token.is_cancelled():
        raise TranscriptionError(
            TranscriptionFailureCode.CANCELLED, "Transcription was cancelled."
        )


class SherpaOnnxProvider:
    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        model_resolver: ModelPathResolver,
        temp_root: Path,
        worker_argv: Sequence[str] | None = None,
        timeout_seconds: float = 1800,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Timeout must be positive.")
        self._resolver = model_resolver
        self._temp_root = temp_root
        self._argv = tuple(
            worker_argv
            or (sys.executable, "-m", "voz.infrastructure.asr.sherpa_onnx_worker")
        )
        self._timeout = timeout_seconds

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        _cancelled(cancellation)
        if options.model.provider_id != self.provider_id:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected model does not belong to this ONNX ASR provider.",
            )
        if (
            options.prompt is not None
            or options.glossary
            or options.quality_profile is not None
        ):
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED,
                "This ONNX ASR provider does not support prompts, glossaries "
                "or decoding profiles.",
            )
        directory = self._resolver.resolve_path(options.model)
        family, roles = self._roles(directory)
        if family == "nemo_transducer" and options.language is not None:
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED,
                "This model does not support a language override; choose Auto.",
            )
        files = (whisper_files if family == "whisper" else nemo_transducer_files)(
            directory, roles
        )
        _cancelled(cancellation)
        try:
            self._temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="voz-sherpa-asr-", dir=self._temp_root
            ) as temporary:
                work = Path(temporary)
                wav = work / "audio.wav"
                with wav.open("xb") as target:
                    os.chmod(wav, 0o600)
                    count = 0
                    while block := audio.read(65536):
                        _cancelled(cancellation)
                        count += len(block)
                        if count > _MAX_AUDIO_BYTES:
                            raise _invalid_audio()
                        target.write(block)
                end_ms = self._validate_audio(wav)
                start_ms = options.clip.start_ms if options.clip is not None else 0
                end_ms = (
                    min(end_ms, options.clip.end_ms)
                    if options.clip is not None
                    else end_ms
                )
                if start_ms >= end_ms:
                    raise _invalid_audio()
                request = work / "request.json"
                document = {
                    "family": family,
                    "files": {key: str(path) for key, path in files.items()},
                    "audio": str(wav),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "language": None
                    if options.language is None
                    else options.language.split("-")[0].lower(),
                }
                with request.open("x", encoding="utf-8") as output:
                    os.chmod(request, 0o600)
                    json.dump(document, output)
                return self._run(request, work, options, start_ms, end_ms, cancellation)
        except (OSError, ValueError):
            raise _failure() from None

    @staticmethod
    def _roles(directory: Path) -> tuple[str, Mapping[str, str] | None]:
        manifest = directory / ".voz-custom.json"
        if not manifest.exists() and not manifest.is_symlink():
            return "whisper", None
        try:
            if (
                manifest.is_symlink()
                or not manifest.is_file()
                or manifest.stat().st_size > 1024**2
            ):
                raise ValueError
            document: object = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError
            metadata = cast(dict[str, object], document)
            family = metadata.get("family")
            if family not in {"whisper", "nemo_transducer"}:
                raise ValueError
            roles = metadata.get("file_roles")
            if not isinstance(roles, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in cast(dict[object, object], roles).items()
            ):
                raise ValueError
            return cast(str, family), cast(dict[str, str], roles)
        except (OSError, ValueError, TypeError):
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected ONNX ASR model manifest is invalid.",
            ) from None

    @staticmethod
    def _validate_audio(path: Path) -> int:
        try:
            with wave.open(str(path), "rb") as source:
                if (
                    source.getnchannels(),
                    source.getsampwidth(),
                    source.getframerate(),
                    source.getcomptype(),
                ) != (1, 2, 16000, "NONE") or source.getnframes() <= 0:
                    raise _invalid_audio()
                remaining = source.getnframes()
                while remaining:
                    count = min(remaining, 32768)
                    if len(source.readframes(count)) != count * 2:
                        raise _invalid_audio()
                    remaining -= count
                return (source.getnframes() + 15) // 16
        except (EOFError, wave.Error, OSError):
            raise _invalid_audio() from None

    def _run(
        self,
        request: Path,
        work: Path,
        options: TranscriptionOptions,
        start_ms: int,
        end_ms: int,
        cancellation: TranscriptionCancellationToken | None,
    ) -> TranscriptionResult:
        events_path = work / "events.jsonl"
        segments: list[TranscriptionSegment] = []
        language: str | None = None
        ended = False
        position = start_ms
        pending = b""
        total = 0
        deadline = time.monotonic() + self._timeout
        with events_path.open("xb") as output:
            os.chmod(events_path, 0o600)
            process = subprocess.Popen(
                [*self._argv, str(request)],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                cwd=work,
                start_new_session=os.name != "nt",
                creationflags=NO_WINDOW,
                env=child_environment(
                    {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
                ),
            )
            try:
                with events_path.open("rb") as incoming:
                    while True:
                        _cancelled(cancellation)
                        if time.monotonic() >= deadline:
                            raise _failure()
                        code = process.poll()
                        block = incoming.read(_MAX_LINE_BYTES + 1)
                        total += len(block)
                        if total > _MAX_RESULT_BYTES:
                            raise _failure()
                        pending += block
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            if len(line) > _MAX_LINE_BYTES or ended:
                                raise _failure()
                            event: object = json.loads(line)
                            if not isinstance(event, dict):
                                raise _failure()
                            item = cast(dict[str, object], event)
                            kind = item.get("type")
                            if kind == "segment":
                                start, end, text = (
                                    item.get("start_ms"),
                                    item.get("end_ms"),
                                    item.get("text"),
                                )
                                if (
                                    type(start) is not int
                                    or type(end) is not int
                                    or not isinstance(text, str)
                                    or not text
                                    or start < position
                                    or end <= start
                                    or end > end_ms
                                    or end - start > 30000
                                ):
                                    raise _failure()
                                segments.append(TranscriptionSegment(start, end, text))
                            elif kind == "progress":
                                current = item.get("position_ms")
                                if (
                                    type(current) is not int
                                    or not position < current <= end_ms
                                ):
                                    raise _failure()
                                position = current
                                if options.on_position is not None:
                                    options.on_position(position)
                            elif kind == "end":
                                candidate = item.get("language")
                                language = observed_language(candidate)
                                if (
                                    candidate is not None and language is None
                                ) or position != end_ms:
                                    raise _failure()
                                ended = True
                            else:
                                raise _failure()
                        if len(pending) > _MAX_LINE_BYTES:
                            raise _failure()
                        if code is not None and not block:
                            if code != 0 or pending or not ended:
                                raise _failure()
                            _cancelled(cancellation)
                            return TranscriptionResult(tuple(segments), language)
                        if not block:
                            time.sleep(0.02)
            except (OSError, ValueError, TypeError):
                raise _failure() from None
            finally:
                if os.name != "nt":
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                else:
                    kill_tree(process)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=2)

    def close(self) -> None:
        """No child remains resident between invocations."""
