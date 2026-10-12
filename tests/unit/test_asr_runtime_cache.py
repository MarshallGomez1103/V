"""One resident local ASR runtime: model switch closes it, idleness frees it."""

import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, BinaryIO, cast

import pytest

from voz import bootstrap
from voz.application.ports.transcription import (
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.infrastructure.asr.catalog import (
    faster_whisper_fast_descriptor,
    faster_whisper_quality_descriptor,
)
from voz.infrastructure.asr.runtime_cache import SingleRuntimeCache
from voz.infrastructure.paths import VozPaths


@dataclass
class _Engines:
    """Counts loads/closes and how many fake engines are resident at once."""

    loaded: list[str] = field(default_factory=list[str])
    closed: list[str] = field(default_factory=list[str])
    peak: int = 0

    @property
    def resident(self) -> int:
        return len(self.loaded) - len(self.closed)

    def create(self, name: str) -> "_Runtime":
        self.loaded.append(name)
        self.peak = max(self.peak, self.resident)
        return _Runtime(name, self)


class _Runtime:
    def __init__(self, name: str, engines: _Engines) -> None:
        self.name = name
        self.engines = engines
        self.providers = TranscriptionProviderRegistry((_Provider(name),))

    def close(self) -> None:
        self.engines.closed.append(self.name)


class _Provider:
    provider_id = "faster-whisper"

    def __init__(self, name: str) -> None:
        self.name = name

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: object = None,
    ) -> TranscriptionResult:
        del audio, options, cancellation
        return TranscriptionResult((TranscriptionSegment(0, 1, self.name),), "es")


def _wait(condition: Any, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return bool(condition())


# -- the cache on its own ----------------------------------------------------


def test_asking_for_another_key_closes_the_resident_one_first() -> None:
    engines = _Engines()
    cache = SingleRuntimeCache[str, _Runtime](idle_seconds=60)

    with cache.use("tiny", lambda: engines.create("tiny")):
        pass
    with cache.use("large", lambda: engines.create("large")):
        assert engines.closed == ["tiny"]

    assert engines.peak == 1
    cache.close()
    assert engines.closed == ["tiny", "large"]


def test_same_key_reuses_the_runtime_and_close_is_idempotent() -> None:
    engines = _Engines()
    cache = SingleRuntimeCache[str, _Runtime](idle_seconds=60)
    for _ in range(3):
        with cache.use("tiny", lambda: engines.create("tiny")):
            pass
    assert engines.loaded == ["tiny"]
    cache.close()
    cache.close()  # idempotent
    assert engines.closed == ["tiny"]


def test_idle_runtime_is_closed_and_reloaded_on_demand() -> None:
    engines = _Engines()
    cache = SingleRuntimeCache[str, _Runtime](idle_seconds=0.05)
    with cache.use("tiny", lambda: engines.create("tiny")):
        pass
    assert _wait(lambda: engines.closed == ["tiny"])
    with cache.use("tiny", lambda: engines.create("tiny")):
        pass
    assert engines.loaded == ["tiny", "tiny"]
    cache.close()


def test_runtime_in_use_is_never_closed_by_the_idle_timer() -> None:
    engines = _Engines()
    cache = SingleRuntimeCache[str, _Runtime](idle_seconds=0.02)
    with cache.use("tiny", lambda: engines.create("tiny")):
        time.sleep(0.15)
        assert engines.closed == []
    assert _wait(lambda: engines.closed == ["tiny"])


def test_a_new_use_cancels_the_pending_idle_close() -> None:
    engines = _Engines()
    cache = SingleRuntimeCache[str, _Runtime](idle_seconds=0.1)
    with cache.use("tiny", lambda: engines.create("tiny")):
        pass
    time.sleep(0.05)
    with cache.use("tiny", lambda: engines.create("tiny")):
        time.sleep(0.2)
        assert engines.closed == []
    cache.close()


# -- the composition root ----------------------------------------------------


def _selection(model: Any) -> JobSelection:
    return cast(JobSelection, SimpleNamespace(model=model))


def _runner_with_fake_asr(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, engines: _Engines
) -> Any:
    captured: list[Any] = []

    def fake_runtime(descriptor: Any, **_: object) -> _Runtime:
        return engines.create(descriptor.model_id)

    def capture(**wiring: Any) -> Any:
        runner = SimpleNamespace(**wiring)
        captured.append(runner)
        return runner

    monkeypatch.setattr(bootstrap, "create_local_asr_runtime", fake_runtime)
    monkeypatch.setattr(bootstrap, "JobRunner", capture)
    paths = VozPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        cache=tmp_path / "cache",
        state=tmp_path / "state",
    )
    bootstrap.create_app(paths=paths)
    return captured[0]


def _transcribe(provider: TranscriptionProvider) -> str:
    result = provider.transcribe(audio=cast(BinaryIO, None), options=cast(Any, None))
    return result.segments[0].text


def test_two_jobs_with_different_models_never_leave_two_engines_loaded(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engines = _Engines()
    runner = _runner_with_fake_asr(tmp_path, monkeypatch, engines)
    fast = faster_whisper_fast_descriptor(revision="a" * 40)
    quality = faster_whisper_quality_descriptor(revision="b" * 40)

    assert _transcribe(runner.provider_for(_selection(fast))) == fast.model_id
    assert _transcribe(runner.provider_for(_selection(quality))) == quality.model_id

    assert engines.loaded == [fast.model_id, quality.model_id]
    assert engines.closed == [fast.model_id]
    assert engines.peak == 1


def test_release_asr_before_diarization_closes_the_runtime(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engines = _Engines()
    runner = _runner_with_fake_asr(tmp_path, monkeypatch, engines)
    fast = faster_whisper_fast_descriptor(revision="a" * 40)
    selection = _selection(fast)

    _transcribe(runner.provider_for(selection))
    runner.release_asr(selection)
    runner.release_asr(selection)  # idempotent

    assert engines.closed == [fast.model_id]


def test_runner_left_idle_releases_the_runtime(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engines = _Engines()
    monkeypatch.setattr(bootstrap, "ASR_IDLE_SECONDS", 0.05)
    runner = _runner_with_fake_asr(tmp_path, monkeypatch, engines)
    fast = faster_whisper_fast_descriptor(revision="a" * 40)
    provider = runner.provider_for(_selection(fast))

    assert _transcribe(provider) == fast.model_id
    assert _wait(lambda: engines.closed == [fast.model_id])
    # A late chunk of the same provider reloads instead of using a closed engine.
    assert _transcribe(provider) == fast.model_id
    assert engines.loaded == [fast.model_id, fast.model_id]
