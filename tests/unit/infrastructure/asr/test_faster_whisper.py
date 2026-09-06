"""Unit tests for the local-only Faster Whisper adapter."""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from threading import Event, Lock
from typing import BinaryIO

import pytest

from voz.application.asr_device_selection import (
    ComputeDevice,
    ExecutionDecision,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider


@dataclass
class _Segment:
    start: float
    end: float
    text: str


@dataclass
class _Info:
    language: str | None


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        assert descriptor == DESCRIPTOR
        return self.path


class _Engine:
    def __init__(
        self,
        segments: list[_Segment],
        language: str | None = "es",
        expected_language: str | None = None,
    ) -> None:
        self.segments = segments
        self.language = language
        self.expected_language = expected_language

    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
    ) -> tuple[Iterable[_Segment], _Info]:
        assert audio.read() == b"pcm"
        assert language == self.expected_language
        assert word_timestamps is False
        assert clip_timestamps == "0"
        return iter(self.segments), _Info(self.language)


class _Cancellation:
    def __init__(self, values: list[bool]) -> None:
        self._values = iter(values)

    def is_cancelled(self) -> bool:
        return next(self._values, True)


DESCRIPTOR = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="fixture",
    display_name="Fixture model",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
    source="example/faster-whisper-fixture",
    revision="0123456789abcdef0123456789abcdef01234567",
)
CPU_EXECUTION = ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8)


def test_adapter_uses_exact_local_path_and_maps_canonical_result(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        calls.append(
            {
                "model_path": model_path,
                "device": device,
                "compute_type": compute_type,
                "local_files_only": local_files_only,
            }
        )
        return _Engine([_Segment(0.0, 0.5, "hola"), _Segment(0.5, 1.25, " mundo")])

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )

    result = provider.transcribe(
        audio=BytesIO(b"pcm"),
        options=TranscriptionOptions(model=DESCRIPTOR),
    )

    assert result.text == "hola mundo"
    assert result.language == "es"
    assert [(item.start_ms, item.end_ms) for item in result.segments] == [
        (0, 500),
        (500, 1_250),
    ]
    assert calls == [
        {
            "model_path": str(tmp_path),
            "device": "cpu",
            "compute_type": "int8",
            "local_files_only": True,
        }
    ]


def test_adapter_reuses_loaded_engine_for_recoverable_chunks(tmp_path: Path) -> None:
    factory_calls = 0

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        nonlocal factory_calls
        factory_calls += 1
        return _Engine([_Segment(0.0, 0.5, "hola")])

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )

    for _ in range(2):
        provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=DESCRIPTOR),
        )

    assert factory_calls == 1


def test_adapter_loads_each_model_once_under_concurrent_calls(tmp_path: Path) -> None:
    factory_calls = 0
    calls_lock = Lock()
    first_factory_started = Event()
    duplicate_factory_started = Event()
    release_factory = Event()

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        nonlocal factory_calls
        with calls_lock:
            factory_calls += 1
            if factory_calls > 1:
                duplicate_factory_started.set()
        first_factory_started.set()
        assert release_factory.wait(timeout=2)
        return _Engine([_Segment(0.0, 0.5, "hola")])

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )

    def transcribe() -> str:
        return provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=DESCRIPTOR),
        ).text

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(transcribe)
        assert first_factory_started.wait(timeout=2)
        second = executor.submit(transcribe)
        try:
            assert not duplicate_factory_started.wait(timeout=0.2)
        finally:
            release_factory.set()
        assert first.result(timeout=2) == "hola"
        assert second.result(timeout=2) == "hola"

    assert factory_calls == 1


def test_adapter_cache_separates_distinct_model_sources(tmp_path: Path) -> None:
    first_descriptor = replace(DESCRIPTOR, source="organization-a/model")
    second_descriptor = replace(DESCRIPTOR, source="organization-b/model")
    resolved_sources: list[str | None] = []
    factory_paths: list[str] = []

    class Resolver:
        def resolve_path(self, descriptor: ModelDescriptor) -> Path:
            resolved_sources.append(descriptor.source)
            return tmp_path / str(descriptor.source)

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del device, compute_type, local_files_only
        factory_paths.append(model_path)
        return _Engine([_Segment(0.0, 0.5, "hola")])

    provider = FasterWhisperProvider(
        model_resolver=Resolver(),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )
    for descriptor in (first_descriptor, second_descriptor, first_descriptor):
        provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=descriptor),
        )

    assert resolved_sources == [
        first_descriptor.source,
        second_descriptor.source,
        first_descriptor.source,
    ]
    assert len(factory_paths) == 3
    assert len(set(factory_paths)) == 2


def test_adapter_does_not_load_second_model_during_active_inference(
    tmp_path: Path,
) -> None:
    first_descriptor = replace(DESCRIPTOR, source="organization-a/model")
    second_descriptor = replace(DESCRIPTOR, source="organization-b/model")
    inference_started = Event()
    release_inference = Event()
    second_model_loaded = Event()
    factory_calls = 0

    class Resolver:
        def resolve_path(self, descriptor: ModelDescriptor) -> Path:
            return tmp_path / str(descriptor.source)

    class BlockingEngine(_Engine):
        def transcribe(
            self,
            audio: BinaryIO,
            *,
            language: str | None,
            word_timestamps: bool,
            clip_timestamps: str | list[float],
        ) -> tuple[Iterable[_Segment], _Info]:
            inference_started.set()
            assert release_inference.wait(timeout=2)
            return super().transcribe(
                audio,
                language=language,
                word_timestamps=word_timestamps,
                clip_timestamps=clip_timestamps,
            )

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            return BlockingEngine([_Segment(0.0, 0.5, "first")])
        second_model_loaded.set()
        return _Engine([_Segment(0.0, 0.5, "second")])

    provider = FasterWhisperProvider(
        model_resolver=Resolver(),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )

    def transcribe(descriptor: ModelDescriptor) -> str:
        return provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=descriptor),
        ).text

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(transcribe, first_descriptor)
        assert inference_started.wait(timeout=2)
        second = executor.submit(transcribe, second_descriptor)
        try:
            assert not second_model_loaded.wait(timeout=0.2)
        finally:
            release_inference.set()
        assert first.result(timeout=2) == "first"
        assert second.result(timeout=2) == "second"


def test_adapter_preserves_language_hint_when_engine_cannot_detect_it(
    tmp_path: Path,
) -> None:
    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        return _Engine(
            [_Segment(0.0, 0.5, "hello")],
            language=None,
            expected_language="en",
        )

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )

    result = provider.transcribe(
        audio=BytesIO(b"pcm"),
        options=TranscriptionOptions(model=DESCRIPTOR, language="en"),
    )

    assert result.language == "en"


def test_adapter_cancels_before_loading_or_between_lazy_segments(
    tmp_path: Path,
) -> None:
    factory_called = False

    def unused_factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        nonlocal factory_called
        factory_called = True
        raise AssertionError

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
        engine_factory=unused_factory,
    )
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=DESCRIPTOR),
            cancellation=_Cancellation([True]),
        )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert not factory_called

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        return _Engine([_Segment(0.0, 0.5, "hola"), _Segment(0.5, 1.0, " mundo")])

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=DESCRIPTOR),
            cancellation=_Cancellation([False, False, True]),
        )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED


def test_adapter_maps_engine_failures_without_exposing_paths(tmp_path: Path) -> None:
    private_path = tmp_path / "private-model"

    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        raise RuntimeError(f"failure at {private_path}")

    provider = FasterWhisperProvider(
        model_resolver=_Resolver(private_path),
        execution=CPU_EXECUTION,
        engine_factory=factory,
    )

    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=DESCRIPTOR),
        )

    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert str(private_path) not in raised.value.user_message
    assert raised.value.retryable


def test_adapter_rejects_descriptor_for_another_provider(tmp_path: Path) -> None:
    descriptor = ModelDescriptor(
        provider_id="other-asr",
        model_id="fixture",
        display_name="Fixture",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    )
    provider = FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU_EXECUTION,
    )

    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(b"pcm"),
            options=TranscriptionOptions(model=descriptor),
        )

    assert raised.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
