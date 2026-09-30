"""Faster Whisper adapter that loads only explicitly installed local snapshots."""

from __future__ import annotations

import ctypes
import importlib
import math
from collections.abc import Generator, Iterable
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
)
from voz.domain.entities.model_descriptor import ModelDescriptor


class _EngineSegment(Protocol):
    start: float
    end: float
    text: str


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


def _preload_cuda_libraries() -> None:
    """Make the optional pip CUDA 12 wheels visible to CTranslate2.

    CTranslate2 dlopens ``libcublas.so.12``/``libcudnn*.so.9`` by soname. The
    ``asr-local`` extra ships them as ``nvidia-*`` wheels instead of touching
    the host; loading them RTLD_GLOBAL first lets those sonames resolve.
    Missing packages are fine: a system CUDA install or the CPU path remains.
    """
    libraries: list[Path] = []
    for package in _NVIDIA_RUNTIME_PACKAGES:
        try:
            module = importlib.import_module(package)
        except ImportError:
            continue
        for root in getattr(module, "__path__", ()):
            libraries.extend(sorted((Path(root) / "lib").glob("lib*.so.*")))
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
            return
        pending = failed


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
    if device == "cuda":
        _preload_cuda_libraries()
    return cast(
        _Engine,
        model_type(
            model_path,
            device=device,
            compute_type=compute_type,
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
        raw_segments: Iterable[_EngineSegment] | None = None
        try:
            engine = self._engine_for(options.model, cancellation)
            self._raise_if_cancelled(cancellation)
            raw_segments, info = engine.transcribe(
                audio,
                language=options.language,
                word_timestamps=False,
                clip_timestamps=(
                    "0"
                    if options.clip is None
                    else [
                        options.clip.start_ms / 1_000,
                        options.clip.end_ms / 1_000,
                    ]
                ),
            )
            try:
                self._raise_if_cancelled(cancellation)
                segments: list[TranscriptionSegment] = []
                for raw_segment in raw_segments:
                    self._raise_if_cancelled(cancellation)
                    segments.append(self._canonical_segment(raw_segment))
            finally:
                # Faster Whisper yields lazily; a retained cancellation traceback
                # must not keep its suspended generator and resources alive.
                if isinstance(raw_segments, Generator):
                    raw_segments.close()
            language = info.language if info.language is not None else options.language
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
            raw_segments = None

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
    def _canonical_segment(raw_segment: _EngineSegment) -> TranscriptionSegment:
        start = float(raw_segment.start)
        end = float(raw_segment.end)
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("provider returned non-finite offsets")
        return TranscriptionSegment(
            start_ms=round(start * 1_000),
            end_ms=round(end * 1_000),
            text=raw_segment.text,
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
