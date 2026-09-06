"""Faster Whisper adapter that loads only explicitly installed local snapshots."""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterable
from pathlib import Path
from threading import RLock
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
        try:
            engine = self._engine_for(options.model)
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
            segments: list[TranscriptionSegment] = []
            for raw_segment in raw_segments:
                self._raise_if_cancelled(cancellation)
                segments.append(self._canonical_segment(raw_segment))
            language = info.language if info.language is not None else options.language
            return TranscriptionResult(segments=tuple(segments), language=language)
        except TranscriptionError:
            raise
        except Exception as error:
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

    def _engine_for(self, descriptor: ModelDescriptor) -> _Engine:
        key = (
            descriptor.provider_id,
            descriptor.model_id,
            descriptor.source,
            descriptor.revision,
        )
        with self._engine_lock:
            if self._engine is None or self._engine_key != key:
                model_path = self._model_resolver.resolve_path(descriptor)
                self._engine = self._engine_factory(
                    str(model_path),
                    device=self._execution.device.value,
                    compute_type=self._execution.precision.value,
                    local_files_only=True,
                )
                self._engine_key = key
            return self._engine

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
