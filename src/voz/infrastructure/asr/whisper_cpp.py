"""whisper.cpp adapter: drives an external ``whisper-cli`` executable, no shell.

Only this module knows the executable's flags and JSON layout. The audio is
copied to a private temporary directory, ``whisper-cli`` writes its full JSON
there, and everything is mapped to the canonical, path-free result types.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
    clamp_words,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.asr.whisper_cpp_catalog import PROVIDER_ID, model_filename

BINARY_ENV_VAR = "VOZ_WHISPER_CPP_BIN"
_BINARY_NAME = "whisper-cli"
# whisper.cpp >= 1.7 ships ``whisper-cli`` with all of these long options.
_REQUIRED_FLAGS = (
    "--model",
    "--file",
    "--language",
    "--output-json-full",
    "--output-file",
    "--no-gpu",
    "--no-prints",
    "--offset-t",
    "--duration",
)
_VERSION = re.compile(r"\bversion[: ]+v?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
_LANGUAGE = re.compile(r"[a-z]{2,3}", re.ASCII)


class WhisperCppUnavailableReason(StrEnum):
    """Stable reasons for the options/diagnostics UI; never contain paths."""

    NOT_FOUND = "whisper_cpp_not_found"
    NOT_EXECUTABLE = "whisper_cpp_not_executable"
    PROBE_TIMEOUT = "whisper_cpp_probe_timeout"
    MISSING_FLAGS = "whisper_cpp_missing_flags"


@dataclass(frozen=True, slots=True)
class WhisperCppAvailability:
    """Typed probe outcome. ``binary`` is for wiring only, never for the API."""

    available: bool
    reason: WhisperCppUnavailableReason | None = None
    version: str | None = None
    binary: Path | None = field(default=None, repr=False)


def locate_whisper_cli(env: Mapping[str, str] | None = None) -> Path | None:
    """Find ``whisper-cli``: ``$VOZ_WHISPER_CPP_BIN`` wins, else ``$PATH``."""
    environment = os.environ if env is None else env
    explicit = environment.get(BINARY_ENV_VAR)
    if explicit:
        # An explicit choice is never silently replaced by a PATH lookup.
        candidate = Path(explicit)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        return None
    found = shutil.which(_BINARY_NAME, path=environment.get("PATH", os.defpath))
    return None if found is None else Path(found)


def probe_whisper_cpp(
    *,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = 5.0,
) -> WhisperCppAvailability:
    """Validate the executable by running ``--help`` and checking its flags."""
    binary = locate_whisper_cli(env)
    if binary is None:
        return WhisperCppAvailability(False, WhisperCppUnavailableReason.NOT_FOUND)
    try:
        completed = subprocess.run(
            [str(binary), "--help"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return WhisperCppAvailability(False, WhisperCppUnavailableReason.PROBE_TIMEOUT)
    except OSError:
        return WhisperCppAvailability(False, WhisperCppUnavailableReason.NOT_EXECUTABLE)
    # whisper-cli prints its usage on stderr.
    help_text = f"{completed.stdout}\n{completed.stderr}"
    if any(flag not in help_text for flag in _REQUIRED_FLAGS):
        return WhisperCppAvailability(False, WhisperCppUnavailableReason.MISSING_FLAGS)
    version = _VERSION.search(help_text)
    return WhisperCppAvailability(
        True, version=None if version is None else version.group(1), binary=binary
    )


class _ModelResolver(Protocol):
    def resolve_path(self, descriptor: ModelDescriptor) -> Path: ...


def _failed(message: str, *, retryable: bool = False) -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.PROVIDER_FAILED, message, retryable=retryable
    )


def _invalid_output() -> TranscriptionError:
    return _failed("whisper.cpp returned an unreadable result.")


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected an integer")
    return value


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected an object")
    return cast(dict[str, object], value)


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected an array")
    return cast(list[object], value)


class WhisperCppProvider:
    """Map ``whisper-cli`` JSON output to VOZ canonical, path-free result types."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        binary: Path,
        model_resolver: _ModelResolver,
        force_cpu: bool = False,
        temp_root: Path | None = None,
        poll_seconds: float = 0.1,
    ) -> None:
        self._binary = binary
        self._model_resolver = model_resolver
        self._force_cpu = force_cpu
        self._temp_root = temp_root
        self._poll_seconds = poll_seconds

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        """Run ``whisper-cli`` on the audio and never leave temporaries behind."""
        if options.model.provider_id != self.provider_id:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected model does not belong to whisper.cpp.",
            )
        self._raise_if_cancelled(cancellation)
        model_file = self._model_file(options.model)
        self._raise_if_cancelled(cancellation)
        # TemporaryDirectory is created 0700 and removed on every exit path.
        with tempfile.TemporaryDirectory(
            prefix="voz-whisper-cpp-", dir=self._temp_root
        ) as work:
            work_dir = Path(work)
            wav = work_dir / "audio.wav"
            try:
                with wav.open("wb") as target:
                    shutil.copyfileobj(audio, target)
            except (OSError, ValueError) as error:
                raise _failed("The audio could not be prepared.") from error
            self._require_normalized_wav(wav)
            self._raise_if_cancelled(cancellation)
            self._run(self._command(model_file, wav, options), work_dir, cancellation)
            self._raise_if_cancelled(cancellation)
            return self._read_result(work_dir / "result.json", options)

    def _model_file(self, descriptor: ModelDescriptor) -> Path:
        try:
            name = model_filename(descriptor)
        except ValueError as error:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected transcription model is not installed.",
            ) from error
        path = self._model_resolver.resolve_path(descriptor) / name
        if path.is_symlink() or not path.is_file():
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected transcription model is not installed.",
            )
        return path

    @staticmethod
    def _require_normalized_wav(path: Path) -> None:
        try:
            with wave.open(str(path), "rb") as normalized:
                valid = (
                    normalized.getnchannels() == 1
                    and normalized.getframerate() == 16_000
                    and normalized.getsampwidth() == 2
                )
        except (EOFError, wave.Error, OSError):
            valid = False
        if not valid:
            raise TranscriptionError(
                TranscriptionFailureCode.INVALID_AUDIO,
                "The selected audio is invalid.",
            )

    def _command(
        self, model_file: Path, wav: Path, options: TranscriptionOptions
    ) -> list[str]:
        language = "auto" if options.language is None else options.language
        command = [
            str(self._binary),
            "--model",
            str(model_file),
            "--file",
            str(wav),
            "--language",
            language.split("-")[0].lower(),
            "--output-json-full",
            "--output-file",
            str(wav.with_name("result")),  # whisper-cli appends ".json"
            "--no-prints",
        ]
        if self._force_cpu:
            command.append("--no-gpu")
        if options.clip is not None:
            command += [
                "--offset-t",
                str(options.clip.start_ms),
                "--duration",
                str(options.clip.end_ms - options.clip.start_ms),
            ]
        return command

    def _run(
        self,
        command: list[str],
        work_dir: Path,
        cancellation: TranscriptionCancellationToken | None,
    ) -> None:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=work_dir,
            )
        except OSError as error:
            raise _failed("The whisper.cpp executable could not be started.") from error
        try:
            while True:
                try:
                    code = process.wait(timeout=self._poll_seconds)
                    break
                except subprocess.TimeoutExpired:
                    self._raise_if_cancelled(cancellation)
        finally:
            # Cancellation, KeyboardInterrupt or any bug: never orphan the child.
            if process.poll() is None:
                self._stop(process)
        if code != 0:
            raise _failed("whisper.cpp failed while processing the audio.")

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def _read_result(
        self, path: Path, options: TranscriptionOptions
    ) -> TranscriptionResult:
        try:
            payload = _mapping(json.loads(path.read_text(encoding="utf-8")))
            language = None
            result = payload.get("result")
            if isinstance(result, dict):
                candidate = cast(dict[str, object], result).get("language")
                if isinstance(candidate, str) and _LANGUAGE.fullmatch(candidate):
                    language = candidate
            segments: list[TranscriptionSegment] = []
            previous_end_ms = 0
            for raw in _sequence(payload["transcription"]):
                item = _mapping(raw)
                text = item["text"]
                if not isinstance(text, str) or not text.strip():
                    continue
                offsets = _mapping(item["offsets"])
                # Keep the word-boundary space but drop other padding.
                text = (" " if text[0].isspace() else "") + text.strip()
                # whisper.cpp may overlap neighbours by a few ms; keep them ordered.
                start_ms = max(_int(offsets["from"]), previous_end_ms, 0)
                end_ms = _int(offsets["to"])
                if end_ms <= start_ms:
                    continue
                words = (
                    self._words(item.get("tokens"), start_ms, end_ms)
                    if options.word_timestamps
                    else ()
                )
                segments.append(TranscriptionSegment(start_ms, end_ms, text, words))
                previous_end_ms = end_ms
            return TranscriptionResult(
                segments=tuple(segments),
                language=language if language is not None else options.language,
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise _invalid_output() from error

    @staticmethod
    def _words(
        raw_tokens: object, start_ms: int, end_ms: int
    ) -> tuple[TranscriptionWord, ...]:
        """Merge sub-word tokens into words; any unusable token voids the hint.

        A token that starts with a space opens a word. Special tokens such as
        ``[_BEG_]`` are skipped. Word timing is best-effort: without token
        offsets the segment keeps its text and simply has no words.
        """
        if not isinstance(raw_tokens, list):
            return ()
        # ponytail: t_dtw is ignored; token offsets are enough for the word hint
        # and DTW start times would need per-model alignment-head flags.
        pieces: list[tuple[str, int, int, float | None]] = []
        for raw in cast(list[object], raw_tokens):
            token = _mapping(raw)
            text = token.get("text")
            if not isinstance(text, str) or text == "":
                continue
            if text.startswith("[_") and text.endswith("]"):
                continue
            offsets = token.get("offsets")
            if not isinstance(offsets, dict):
                return ()
            bounds = cast(dict[str, object], offsets)
            start, end = bounds.get("from"), bounds.get("to")
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end < start
            ):
                return ()
            probability = token.get("p")
            pieces.append(
                (
                    text,
                    start,
                    end,
                    float(probability)
                    if isinstance(probability, (int, float))
                    and not isinstance(probability, bool)
                    and math.isfinite(probability)
                    else None,
                )
            )
        words: list[TranscriptionWord] = []
        group: list[tuple[str, int, int, float | None]] = []

        def flush() -> None:
            if not group:
                return
            chances = [p for *_, p in group if p is not None]
            words.append(
                TranscriptionWord(
                    start_ms=group[0][1],
                    end_ms=group[-1][2],
                    text="".join(piece[0] for piece in group),
                    # ponytail: mean token probability stands in for the word's.
                    probability=(
                        min(1.0, max(0.0, sum(chances) / len(chances)))
                        if chances
                        else None
                    ),
                )
            )
            group.clear()

        for piece in pieces:
            if piece[0][0].isspace():
                flush()
            group.append(piece)
        flush()
        return clamp_words(tuple(words), start_ms, end_ms)

    @staticmethod
    def _raise_if_cancelled(
        cancellation: TranscriptionCancellationToken | None,
    ) -> None:
        if cancellation is not None and cancellation.is_cancelled():
            raise TranscriptionError(
                TranscriptionFailureCode.CANCELLED,
                "Transcription was cancelled.",
            )


__all__ = [
    "BINARY_ENV_VAR",
    "WhisperCppAvailability",
    "WhisperCppProvider",
    "WhisperCppUnavailableReason",
    "locate_whisper_cli",
    "probe_whisper_cpp",
]
