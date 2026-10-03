"""Faster Whisper adapter that loads only explicitly installed local snapshots."""

from __future__ import annotations

import ctypes
import importlib
import logging
import math
import os
import sys
from collections.abc import Callable, Generator, Iterable, Sequence
from pathlib import Path
from threading import RLock
from traceback import clear_frames
from typing import BinaryIO, Protocol, cast

from voz.application.asr_device_selection import ExecutionDecision
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

_logger = logging.getLogger(__name__)


class _EngineWord(Protocol):
    start: float
    end: float
    word: str
    probability: float


class _EngineSegment(Protocol):
    start: float
    end: float
    text: str
    # Confidence metrics are read with getattr: word-less/older engines omit them.


class _EngineInfo(Protocol):
    language: str | None


class _Engine(Protocol):
    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
    ) -> tuple[Iterable[_EngineSegment], _EngineInfo]: ...


class _EngineFactory(Protocol):
    def __call__(
        self,
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine: ...


class _ModelResolver(Protocol):
    def resolve_path(self, descriptor: ModelDescriptor) -> Path: ...


def _default_invalid_audio_errors() -> tuple[type[Exception], ...]:
    try:
        module = importlib.import_module("av.error")
    except ImportError:
        return ()
    error_types: list[type[Exception]] = []
    for name in ("InvalidDataError", "EOFError"):
        candidate = vars(module).get(name)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, Exception)
            and candidate not in error_types
        ):
            error_types.append(candidate)
    return tuple(error_types)


_NVIDIA_RUNTIME_PACKAGES = ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc")
# Windows loads these by name through PATH / AddDllDirectory.
_WINDOWS_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")
_dll_directory_handles: list[object] = []  # AddDllDirectory dies with its handle


def _nvidia_package_roots() -> list[Path]:
    roots: list[Path] = []
    for package in _NVIDIA_RUNTIME_PACKAGES:
        try:
            module = importlib.import_module(package)
        except ImportError:
            continue
        roots.extend(Path(root) for root in getattr(module, "__path__", ()))
    return roots


def _preload_cuda_libraries() -> bool:
    """Make the optional pip CUDA 12 wheels visible to CTranslate2.

    Linux: CTranslate2 dlopens ``libcublas.so.12``/``libcudnn*.so.9`` by soname.
    The ``asr-local`` extra ships them as ``nvidia-*`` wheels instead of touching
    the host; loading them RTLD_GLOBAL first lets those sonames resolve.
    Windows: the same wheels carry DLLs in ``nvidia/<pkg>/bin``; those folders
    are registered for DLL search and added to ``PATH``, then the two entry DLLs
    are loaded to prove CUDA works before a model is built.

    Missing packages are fine: a system CUDA install or the CPU path remains.
    Returns ``False`` only when the Windows DLLs are present but cannot load.
    """
    if sys.platform == "win32":
        return _preload_cuda_dlls()
    libraries: list[Path] = []
    for root in _nvidia_package_roots():
        libraries.extend(sorted((root / "lib").glob("lib*.so.*")))
    # ponytail: retry passes resolve inter-library order without a dependency
    # graph; each pass loads at least one library or stops.
    pending = libraries
    while pending:
        failed: list[Path] = []
        for library in pending:
            try:
                ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                failed.append(library)
        if len(failed) == len(pending):
            return True
        pending = failed
    return True


def _preload_cuda_dlls() -> bool:
    if sys.platform != "win32":
        return False
    for directory in (root / "bin" for root in _nvidia_package_roots()):
        if not directory.is_dir():
            continue
        _dll_directory_handles.append(os.add_dll_directory(str(directory)))
        path = os.environ.get("PATH", "")
        if str(directory) not in path.split(os.pathsep):
            os.environ["PATH"] = str(directory) + os.pathsep + path
    try:
        for name in _WINDOWS_CUDA_DLLS:
            ctypes.WinDLL(name)
    except OSError:
        return False
    return True


def _cpu_fallback_notice(reason: str) -> None:
    _logger.warning(
        "CUDA no está disponible (%s); VOZ usa la CPU (int8). Es más lento pero "
        "funciona. Revisa el driver NVIDIA o instala con la opción asr-local.",
        reason,
    )


def _metric(
    raw_segment: object,
    name: str,
    low: float | None = None,
    high: float | None = None,
) -> float | None:
    """Optional finite engine metric; anything unusable becomes ``None``."""
    value = getattr(raw_segment, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if (low is not None and number < low) or (high is not None and number > high):
        return None
    return number


def _decoding_arguments(options: TranscriptionOptions) -> dict[str, object]:
    """Engine keyword arguments for the quality profile and glossary (S13.01-03).

    No profile and no glossary add nothing, so the engine keeps its own defaults.
    The glossary goes in ``hotwords`` rather than ``initial_prompt``: Faster
    Whisper prepends hotwords to the prompt of *every* decoding window, while
    ``initial_prompt`` only seeds the first one, and it leaves ``initial_prompt``
    free for the user's style prompt. The library truncates oversized hotwords
    itself. VAD is ignored by the library when explicit ``clip_timestamps`` are
    used (``options.clip``).
    """
    arguments: dict[str, object] = {}
    profile = options.quality_profile
    if profile is not None:
        arguments.update(
            beam_size=profile.beam_size,
            temperature=list(profile.temperature),
            condition_on_previous_text=profile.condition_on_previous_text,
            no_speech_threshold=profile.no_speech_threshold,
            vad_filter=profile.vad is not None,
        )
        if profile.vad is not None:
            arguments["vad_parameters"] = profile.vad.to_dict()
    if options.glossary:
        arguments["hotwords"] = ", ".join(options.glossary)
    if options.prompt:
        # The style prompt seeds the first window after the hotwords the library
        # prepends to every window (``hotwords`` then ``initial_prompt``).
        arguments["initial_prompt"] = options.prompt
    return arguments


def _default_engine_factory(
    model_path: str,
    *,
    device: str,
    compute_type: str,
    local_files_only: bool,
) -> _Engine:
    try:
        module = importlib.import_module("faster_whisper")
        model_type = vars(module)["WhisperModel"]
    except (ImportError, AttributeError) as error:
        raise TranscriptionError(
            TranscriptionFailureCode.PROVIDER_FAILED,
            "The Faster Whisper runtime is not installed.",
        ) from error
    if device == "cuda" and not _preload_cuda_libraries():
        _cpu_fallback_notice("no se pudieron cargar las bibliotecas cuBLAS/cuDNN")
        device, compute_type = "cpu", "int8"
    try:
        return cast(
            _Engine,
            model_type(
                model_path,
                device=device,
                compute_type=compute_type,
                local_files_only=local_files_only,
            ),
        )
    except (RuntimeError, ValueError) as error:
        if device != "cuda":
            raise
        # A broken CUDA stack must degrade to CPU, never fail the job.
        _cpu_fallback_notice(type(error).__name__)
        return cast(
            _Engine,
            model_type(
                model_path,
                device="cpu",
                compute_type="int8",
                local_files_only=local_files_only,
            ),
        )


class FasterWhisperProvider:
    """Map Faster Whisper output to VOZ canonical, path-free result types."""

    provider_id = "faster-whisper"

    def __init__(
        self,
        *,
        model_resolver: _ModelResolver,
        execution: ExecutionDecision,
        engine_factory: _EngineFactory = _default_engine_factory,
        invalid_audio_errors: tuple[type[Exception], ...] | None = None,
        configured_model: ModelDescriptor | None = None,
    ) -> None:
        self._model_resolver = model_resolver
        self._engine_factory = engine_factory
        self._execution = execution
        self._invalid_audio_errors = (
            _default_invalid_audio_errors()
            if invalid_audio_errors is None
            else invalid_audio_errors
        )
        self._configured_model = configured_model
        self._engine_key: tuple[str, str, str | None, str | None] | None = None
        self._engine: _Engine | None = None
        self._engine_lock = RLock()
        self._closed = False

    def close(self) -> None:
        """Wait for active inference, release the cache, and permanently close.

        The infrastructure owner must call this during shutdown. Repeated calls
        are safe; closing does not interrupt an in-flight native engine call.
        """
        with self._engine_lock:
            self._closed = True
            self._release_engine()

    def _release_engine(self) -> None:
        """Drop owned references under the engine lock, before another load."""
        self._engine_key = None
        self._engine = None

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        """Transcribe with a local snapshot and never resolve a remote model ID."""
        if options.model.provider_id != self.provider_id:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected model does not belong to Faster Whisper.",
            )
        if (
            self._configured_model is not None
            and options.model != self._configured_model
        ):
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected model does not match this local ASR runtime.",
            )
        self._raise_if_cancelled(cancellation)
        with self._engine_lock:
            if self._closed:
                raise TranscriptionError(
                    TranscriptionFailureCode.PROVIDER_FAILED,
                    "The Faster Whisper provider is closed.",
                )
            self._raise_if_cancelled(cancellation)
            return self._transcribe_locked(
                audio=audio,
                options=options,
                cancellation=cancellation,
            )

    def _transcribe_locked(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None,
    ) -> TranscriptionResult:
        engine: _Engine | None = None
        try:
            engine = self._engine_for(options.model, cancellation)
            self._raise_if_cancelled(cancellation)
            try:
                segments, language = self._run_engine(
                    engine, audio, options, options.word_timestamps, cancellation
                )
            except Exception as error:
                # Word timing is best-effort: when the alignment step breaks, redo
                # the chunk once without words so the job still completes.
                # ponytail: retry only when the audio can be rewound; other
                # failures (cancel, invalid audio, closed stream) keep their code.
                if not (
                    options.word_timestamps
                    and not isinstance(error, TranscriptionError)
                    and not isinstance(error, self._invalid_audio_errors)
                    and audio.seekable()
                ):
                    raise
                self._clear_failure_frames(error)
                audio.seek(0)
                segments, language = self._run_engine(
                    engine, audio, options, False, cancellation
                )
            self._raise_if_cancelled(cancellation)
            return TranscriptionResult(segments=tuple(segments), language=language)
        except TranscriptionError as error:
            self._clear_failure_frames(error)
            raise
        except Exception as error:
            self._clear_failure_frames(error)
            if isinstance(error, self._invalid_audio_errors):
                raise TranscriptionError(
                    TranscriptionFailureCode.INVALID_AUDIO,
                    "The selected audio is invalid.",
                ) from error
            if isinstance(error, (OSError, TypeError, ValueError)):
                raise TranscriptionError(
                    TranscriptionFailureCode.PROVIDER_FAILED,
                    "Faster Whisper could not transcribe the selected audio.",
                ) from error
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED,
                "Faster Whisper failed while processing the audio.",
                retryable=True,
            ) from error
        finally:
            # Exceptions can outlive this call. Do not retain our local engine
            # or iterable references in their traceback frames.
            engine = None

    def _run_engine(
        self,
        engine: _Engine,
        audio: BinaryIO,
        options: TranscriptionOptions,
        word_timestamps: bool,
        cancellation: TranscriptionCancellationToken | None,
    ) -> tuple[list[TranscriptionSegment], str | None]:
        # Profile/glossary arguments are optional engine keywords; the minimal
        # protocol above stays unchanged, so call through a loose signature.
        transcribe = cast(
            "Callable[..., tuple[Iterable[_EngineSegment], _EngineInfo]]",
            engine.transcribe,
        )
        raw_segments, info = transcribe(
            audio,
            language=options.language,
            word_timestamps=word_timestamps,
            clip_timestamps=(
                "0"
                if options.clip is None
                else [
                    options.clip.start_ms / 1_000,
                    options.clip.end_ms / 1_000,
                ]
            ),
            **_decoding_arguments(options),
        )
        try:
            self._raise_if_cancelled(cancellation)
            segments: list[TranscriptionSegment] = []
            for raw_segment in raw_segments:
                self._raise_if_cancelled(cancellation)
                segment = self._canonical_segment(raw_segment, word_timestamps)
                segments.append(segment)
                if options.on_position is not None:
                    options.on_position(segment.end_ms)
        finally:
            # Faster Whisper yields lazily; a retained cancellation traceback
            # must not keep its suspended generator and resources alive.
            if isinstance(raw_segments, Generator):
                raw_segments.close()
        return (
            segments,
            info.language if info.language is not None else options.language,
        )

    def _engine_for(
        self,
        descriptor: ModelDescriptor,
        cancellation: TranscriptionCancellationToken | None,
    ) -> _Engine:
        key = (
            descriptor.provider_id,
            descriptor.model_id,
            descriptor.source,
            descriptor.revision,
        )
        with self._engine_lock:
            if self._engine is None or self._engine_key != key:
                model_path = self._model_resolver.resolve_path(descriptor)
                self._raise_if_cancelled(cancellation)
                self._release_engine()
                self._engine = self._engine_factory(
                    str(model_path),
                    device=self._execution.device.value,
                    compute_type=self._execution.precision.value,
                    local_files_only=True,
                )
                self._engine_key = key
            return self._engine

    @staticmethod
    def _clear_failure_frames(error: BaseException) -> None:
        """Keep diagnostic stacks, not engine references in completed SDK frames."""
        pending = [error]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            clear_frames(current.__traceback__)
            pending.extend(
                linked
                for linked in (current.__cause__, current.__context__)
                if linked is not None
            )

    @staticmethod
    def _canonical_segment(
        raw_segment: _EngineSegment,
        with_words: bool = False,
    ) -> TranscriptionSegment:
        start = float(raw_segment.start)
        end = float(raw_segment.end)
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("provider returned non-finite offsets")
        start_ms = round(start * 1_000)
        end_ms = round(end * 1_000)
        words = ()
        if with_words:
            # Optional on the protocol (so word-less engines still fit) and None
            # when the engine could not align a span.
            raw_words = cast(
                "Sequence[_EngineWord]", getattr(raw_segment, "words", None) or ()
            )
            words = clamp_words(
                tuple(
                    word
                    for word in map(FasterWhisperProvider._canonical_word, raw_words)
                    if word is not None
                ),
                start_ms,
                end_ms,
            )
        return TranscriptionSegment(
            start_ms=start_ms,
            end_ms=end_ms,
            text=raw_segment.text,
            words=words,
            avg_logprob=_metric(raw_segment, "avg_logprob"),
            no_speech_prob=_metric(raw_segment, "no_speech_prob", 0.0, 1.0),
            compression_ratio=_metric(raw_segment, "compression_ratio", 0.0),
        )

    @staticmethod
    def _canonical_word(raw_word: _EngineWord) -> TranscriptionWord | None:
        """Map one engine word; an unusable word is skipped, never fatal."""
        start = float(raw_word.start)
        end = float(raw_word.end)
        if not (math.isfinite(start) and math.isfinite(end)) or not raw_word.word:
            return None
        start_ms = max(0, round(start * 1_000))
        probability = float(raw_word.probability)
        return TranscriptionWord(
            start_ms=start_ms,
            end_ms=max(start_ms, round(end * 1_000)),
            text=raw_word.word,
            probability=(
                min(1.0, max(0.0, probability)) if math.isfinite(probability) else None
            ),
        )

    @staticmethod
    def _raise_if_cancelled(
        cancellation: TranscriptionCancellationToken | None,
    ) -> None:
        if cancellation is not None and cancellation.is_cancelled():
            raise TranscriptionError(
                TranscriptionFailureCode.CANCELLED,
                "Transcription was cancelled.",
            )


__all__ = ["FasterWhisperProvider"]
