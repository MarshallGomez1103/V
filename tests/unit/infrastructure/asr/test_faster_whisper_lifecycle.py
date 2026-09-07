"""Behavioral regressions for engine ownership and standalone cancellation."""

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from threading import Event, RLock
from typing import BinaryIO
from weakref import ReferenceType, ref

import pytest

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider

MODEL = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="fixture",
    display_name="Synthetic fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


@dataclass
class _Segment:
    start: float = 0.0
    end: float = 0.5
    text: str = "hola"


@dataclass
class _Info:
    language: str | None = "es"


class _Cancellation:
    def __init__(self) -> None:
        self.event = Event()

    def is_cancelled(self) -> bool:
        return self.event.is_set()


class _Engine:
    def __init__(self, run: Callable[[], Iterable[_Segment]]) -> None:
        self.run = run

    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
    ) -> tuple[Iterable[_Segment], _Info]:
        del audio, language, word_timestamps, clip_timestamps
        return self.run(), _Info()


class _Factory:
    def __init__(self) -> None:
        self.references: list[ReferenceType[_Engine]] = []
        self.alive_at_load: list[int] = []
        self.fail = False
        self.fail_after_allocation = False
        self.on_load: Callable[[], None] = lambda: None
        self.run: Callable[[], Iterable[_Segment]] = lambda: [_Segment()]

    def __call__(
        self,
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        self.alive_at_load.append(sum(item() is not None for item in self.references))
        self.on_load()
        if self.fail:
            raise RuntimeError("synthetic load failure")
        engine = _Engine(self.run)
        self.references.append(ref(engine))
        if self.fail_after_allocation:
            raise RuntimeError("synthetic failure after allocation")
        return engine


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        return self.path / descriptor.model_id


def _provider(tmp_path: Path, factory: _Factory) -> FasterWhisperProvider:
    return FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8),
        engine_factory=factory,
        invalid_audio_errors=(),
    )


def test_replacement_releases_old_engine_before_factory_starts(tmp_path: Path) -> None:
    factory = _Factory()
    provider = _provider(tmp_path, factory)
    for model in (MODEL, replace(MODEL, model_id="second"), MODEL):
        assert (
            provider.transcribe(
                audio=BytesIO(), options=TranscriptionOptions(model=model)
            ).text
            == "hola"
        )
        assert sum(item() is not None for item in factory.references) == 1

    assert factory.alive_at_load == [0, 0, 0]


@pytest.mark.parametrize("retry_original", [False, True])
def test_failed_replacement_leaves_empty_cache_and_can_retry(
    tmp_path: Path, retry_original: bool
) -> None:
    factory = _Factory()
    provider = _provider(tmp_path, factory)
    provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=MODEL))
    second = replace(MODEL, model_id="second")
    factory.fail = True
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=second))
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert all(item() is None for item in factory.references)
    factory.fail = False
    result = provider.transcribe(
        audio=BytesIO(),
        options=TranscriptionOptions(model=MODEL if retry_original else second),
    )
    assert result.text == "hola"
    assert factory.alive_at_load == [0, 0, 0]


@pytest.mark.parametrize("load_first", [False, True])
def test_close_releases_engine_is_idempotent_and_prevents_reloading(
    tmp_path: Path, load_first: bool
) -> None:
    factory = _Factory()
    provider = _provider(tmp_path, factory)
    if load_first:
        provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=MODEL))
    provider.close()
    provider.close()
    assert all(item() is None for item in factory.references)
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=MODEL))
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert not raised.value.retryable
    assert len(factory.references) == int(load_first)


def test_close_waits_for_lazy_inference_and_then_releases_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _Factory()
    inference_started = Event()
    close_waiting = Event()
    release_inference = Event()
    order: list[str] = []

    def generate() -> Iterator[_Segment]:
        inference_started.set()
        assert release_inference.wait(timeout=5)
        assert factory.references[0]() is not None
        yield _Segment()
        order.append("inference-finished")

    factory.run = generate
    provider = _provider(tmp_path, factory)

    class ObservedLock:
        """Observe actual contention without thread scheduling sleeps."""

        def __init__(self) -> None:
            self.lock = RLock()

        def __enter__(self) -> None:
            if not self.lock.acquire(blocking=False):
                close_waiting.set()
                self.lock.acquire()

        def __exit__(self, *args: object) -> None:
            self.lock.release()

    monkeypatch.setattr(provider, "_engine_lock", ObservedLock())

    def close() -> None:
        provider.close()
        order.append("closed")

    with ThreadPoolExecutor(max_workers=2) as executor:
        inference = executor.submit(
            provider.transcribe,
            audio=BytesIO(),
            options=TranscriptionOptions(model=MODEL),
        )
        try:
            assert inference_started.wait(timeout=5)
            closing = executor.submit(close)
            assert close_waiting.wait(timeout=5)
        finally:
            release_inference.set()
        assert inference.result(timeout=5).text == "hola"
        closing.result(timeout=5)
    assert order == ["inference-finished", "closed"]
    assert factory.references[0]() is None


def test_replacement_after_cancel_does_not_retain_engine_in_traceback(
    tmp_path: Path,
) -> None:
    factory = _Factory()
    token = _Cancellation()

    def generate() -> Iterator[_Segment]:
        yield _Segment()
        token.event.set()
        yield _Segment(start=0.5, end=1.0)

    factory.run = generate
    provider = _provider(tmp_path, factory)
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(),
            options=TranscriptionOptions(model=MODEL),
            cancellation=token,
        )
    factory.run = lambda: [_Segment()]
    result = provider.transcribe(
        audio=BytesIO(),
        options=TranscriptionOptions(model=replace(MODEL, model_id="second")),
    )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert result.text == "hola"
    assert factory.references[0]() is None
    assert factory.alive_at_load == [0, 0]


@pytest.mark.parametrize(
    "phase",
    [
        "before-load",
        "loading",
        "invoke",
        "invoke-empty",
        "empty",
        "iteration",
        "exhaustion",
    ],
)
def test_standalone_cancellation_at_each_engine_boundary(
    tmp_path: Path, phase: str
) -> None:
    factory = _Factory()
    token = _Cancellation()
    invoked = False
    visited: list[str] = []

    def generate() -> Iterator[_Segment]:
        try:
            visited.append("started")
            if phase == "empty":
                token.event.set()
                return
            yield _Segment()
            token.event.set()
            if phase == "iteration":
                yield _Segment(start=0.5, end=1.0)
                visited.append("must-not-reach")
        finally:
            visited.append("released")

    def run() -> Iterable[_Segment]:
        nonlocal invoked
        invoked = True
        if phase in {"invoke", "invoke-empty"}:
            token.event.set()
            return [] if phase == "invoke-empty" else [_Segment()]
        return generate()

    factory.run = run
    if phase == "before-load":
        token.event.set()
    if phase == "loading":
        factory.on_load = token.event.set
    provider = _provider(tmp_path, factory)
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(),
            options=TranscriptionOptions(model=MODEL),
            cancellation=token,
        )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    if phase in {"before-load", "loading"}:
        assert not invoked
    if phase == "before-load":
        assert not factory.references
    if phase in {"empty", "iteration", "exhaustion"}:
        assert visited == ["started", "released"]
    # Keeping the exception alive must not keep the adapter's frame/generator
    # references alive after explicit shutdown.
    provider.close()
    assert all(item() is None for item in factory.references)


def test_empty_success_without_cancellation_is_preserved(tmp_path: Path) -> None:
    factory = _Factory()
    factory.run = lambda: []
    result = _provider(tmp_path, factory).transcribe(
        audio=BytesIO(), options=TranscriptionOptions(model=MODEL)
    )
    assert result.segments == ()
    assert result.language == "es"


def test_cancellation_during_resolution_prevents_engine_loading(tmp_path: Path) -> None:
    factory = _Factory()
    token = _Cancellation()

    class CancellingResolver(_Resolver):
        def resolve_path(self, descriptor: ModelDescriptor) -> Path:
            token.event.set()
            return super().resolve_path(descriptor)

    provider = FasterWhisperProvider(
        model_resolver=CancellingResolver(tmp_path),
        execution=ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8),
        engine_factory=factory,
        invalid_audio_errors=(),
    )
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(),
            options=TranscriptionOptions(model=MODEL),
            cancellation=token,
        )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert factory.alive_at_load == []


def test_close_after_failed_load_is_safe_and_terminal(tmp_path: Path) -> None:
    factory = _Factory()
    factory.fail = True
    provider = _provider(tmp_path, factory)
    with pytest.raises(TranscriptionError):
        provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=MODEL))
    provider.close()
    provider.close()
    factory.fail = False
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=MODEL))
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert not raised.value.retryable
    assert factory.alive_at_load == [0]


@pytest.mark.parametrize("phase", ["invoke", "invoke-chained", "load-after-allocation"])
@pytest.mark.parametrize("finish", ["replace", "close"])
def test_retained_sdk_failure_does_not_keep_engine_alive_on_replace_or_close(
    tmp_path: Path, phase: str, finish: str
) -> None:
    factory = _Factory()

    def native_failure() -> None:
        # A chained exception's deepest SDK frame can own the engine too.
        owner = factory.references[-1]()
        assert owner is not None
        raise RuntimeError("synthetic SDK failure")

    def fail() -> Iterable[_Segment]:
        try:
            native_failure()
        except RuntimeError as error:
            if phase == "invoke-chained":
                raise ValueError("synthetic wrapper") from error
            raise
        return []

    if phase == "load-after-allocation":
        factory.fail_after_allocation = True
    else:
        factory.run = fail
    provider = _provider(tmp_path, factory)
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(audio=BytesIO(), options=TranscriptionOptions(model=MODEL))

    factory.fail_after_allocation = False
    factory.run = lambda: [_Segment()]
    if finish == "replace":
        result = provider.transcribe(
            audio=BytesIO(),
            options=TranscriptionOptions(model=replace(MODEL, model_id="second")),
        )
        assert result.text == "hola"
        assert factory.alive_at_load == [0, 0]
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert raised.value.__cause__ is not None
    assert raised.value.__cause__.__traceback__ is not None
    provider.close()
    assert all(item() is None for item in factory.references)
