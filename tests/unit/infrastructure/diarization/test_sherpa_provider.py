"""Sherpa-onnx diarization adapter with an injected fake engine (no models)."""

from __future__ import annotations

import io
import os
import threading
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationOptions,
    DiarizationProvider,
    SpeakerCountHint,
)
from voz.infrastructure.diarization import sherpa
from voz.infrastructure.diarization.sherpa import SherpaOnnxDiarizationProvider

pytest.importorskip("numpy")
import numpy as np
import numpy.typing as npt

_CODE = DiarizationFailureCode


@dataclass
class _Raw:
    start: float
    end: float
    speaker: int


class _Engine:
    """Answers with as many speakers as ``num_clusters`` asks for (3 when auto)."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, float, int]] = []

    def diarize(
        self,
        samples: npt.NDArray[np.float32],
        *,
        num_clusters: int,
        threshold: float,
        progress: sherpa.Progress,
    ) -> Sequence[_Raw]:
        assert samples.dtype == np.float32
        self.calls.append((num_clusters, threshold, len(samples)))
        speakers = 3 if num_clusters == -1 else num_clusters
        return [_Raw(i * 1.0, i * 1.0 + 0.9996, i % speakers) for i in range(6, -1, -1)]


class _Token:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


def _wav(
    *, rate: int = 16_000, channels: int = 1, width: int = 2, seconds: float = 1
) -> io.BytesIO:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x40" * int(rate * seconds) * channels)
    buffer.seek(0)
    return buffer


@pytest.fixture
def models(tmp_path: Path) -> tuple[Path, Path]:
    segmentation, embedding = tmp_path / "seg.onnx", tmp_path / "emb.onnx"
    segmentation.write_bytes(b"x")
    embedding.write_bytes(b"x")
    return segmentation, embedding


def _provider(
    models: tuple[Path, Path],
    engine: _Engine | None = None,
    threshold: float = 0.3,
) -> tuple[SherpaOnnxDiarizationProvider, _Engine, list[int]]:
    fake = engine or _Engine()
    loads: list[int] = []

    def factory(seg: Path, emb: Path, threads: int) -> _Engine:
        loads.append(threads)
        return fake

    return (
        SherpaOnnxDiarizationProvider(
            segmentation_model=models[0],
            embedding_model=models[1],
            engine_factory=factory,
            threshold=threshold,
        ),
        fake,
        loads,
    )


def _clusters(provider: SherpaOnnxDiarizationProvider, hint: SpeakerCountHint) -> int:
    result = provider.diarize(audio=_wav(), options=DiarizationOptions(hint))
    return len({turn.cluster for turn in result.turns})


def test_satisfies_the_port_and_maps_sorted_integer_milliseconds(
    models: tuple[Path, Path],
) -> None:
    provider, engine, _ = _provider(models)
    assert isinstance(provider, DiarizationProvider)

    result = provider.diarize(audio=_wav(seconds=2), options=DiarizationOptions())

    starts = [turn.start_ms for turn in result.turns]
    assert starts == sorted(starts) == [i * 1000 for i in range(7)]
    assert result.turns[0].end_ms == 1000  # 0.9996 s rounds, never truncates
    assert {turn.cluster for turn in result.turns} == {"0", "1", "2"}
    assert engine.calls == [(-1, 0.3, 32_000)]
    assert sherpa.DEFAULT_THRESHOLD == 0.4  # measured, see the table in sherpa.py


def test_auto_uses_the_threshold_and_keeps_the_override(
    models: tuple[Path, Path],
) -> None:
    provider, engine, _ = _provider(models, threshold=0.45)

    provider.diarize(audio=_wav(), options=DiarizationOptions())

    assert engine.calls[0][:2] == (-1, 0.45)


def test_exact_count_fixes_the_clusters(models: tuple[Path, Path]) -> None:
    provider, engine, _ = _provider(models)

    assert _clusters(provider, SpeakerCountHint(exact=2)) == 2
    assert [call[0] for call in engine.calls] == [2]


@pytest.mark.parametrize(
    ("hint", "expected", "runs"),
    [
        (SpeakerCountHint(minimum=2, maximum=4), 3, [-1]),  # already inside
        (SpeakerCountHint(minimum=5), 5, [-1, 5]),  # too few: raise to minimum
        (SpeakerCountHint(maximum=2), 2, [-1, 2]),  # too many: clamp to maximum
        (SpeakerCountHint(minimum=3, maximum=3), 3, [-1]),
    ],
)
def test_range_reruns_clamped_without_reloading_models(
    models: tuple[Path, Path], hint: SpeakerCountHint, expected: int, runs: list[int]
) -> None:
    provider, engine, loads = _provider(models)

    assert _clusters(provider, hint) == expected
    assert [call[0] for call in engine.calls] == runs
    assert len(loads) == 1


def test_engine_is_cached_between_runs_and_released_on_close(
    models: tuple[Path, Path],
) -> None:
    provider, _, loads = _provider(models)
    provider.diarize(audio=_wav(), options=DiarizationOptions())
    provider.diarize(audio=_wav(), options=DiarizationOptions())
    assert loads == [sherpa.default_diarization_threads()]

    provider.close()
    provider.close()
    with pytest.raises(DiarizationError) as closed:
        provider.diarize(audio=_wav(), options=DiarizationOptions())
    assert closed.value.code == _CODE.PROVIDER_FAILED


@pytest.mark.parametrize(
    "audio",
    [
        _wav(channels=2),
        _wav(rate=8_000),
        _wav(width=1),
        io.BytesIO(b"not a wav at all"),
        io.BytesIO(b""),
        _wav(seconds=0),
    ],
    ids=["stereo", "8khz", "8bit", "garbage", "empty", "no-samples"],
)
def test_non_normalized_audio_is_invalid(
    models: tuple[Path, Path], audio: io.BytesIO
) -> None:
    provider, engine, loads = _provider(models)

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=audio, options=DiarizationOptions())

    assert failure.value.code == _CODE.INVALID_AUDIO
    assert not engine.calls and not loads


def test_missing_model_files_are_model_unavailable(tmp_path: Path) -> None:
    provider = SherpaOnnxDiarizationProvider(
        segmentation_model=tmp_path / "missing.onnx",
        embedding_model=tmp_path / "missing2.onnx",
    )

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions())

    assert failure.value.code == _CODE.MODEL_UNAVAILABLE
    assert str(tmp_path) not in failure.value.user_message


def test_missing_runtime_is_runtime_unavailable(
    models: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sherpa.importlib.import_module

    def fake_import(name: str) -> object:
        if name == "sherpa_onnx":
            raise ImportError(name)
        return real(name)

    monkeypatch.setattr(sherpa.importlib, "import_module", fake_import)
    provider = SherpaOnnxDiarizationProvider(
        segmentation_model=models[0], embedding_model=models[1]
    )

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions())

    assert failure.value.code == _CODE.RUNTIME_UNAVAILABLE


def test_pre_cancelled_token_never_loads_models(models: tuple[Path, Path]) -> None:
    provider, _, loads = _provider(models)

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(
            audio=_wav(), options=DiarizationOptions(), cancellation=_Token(True)
        )

    assert failure.value.code == _CODE.CANCELLED
    assert not loads


def test_progress_callback_aborts_when_cancelled(models: tuple[Path, Path]) -> None:
    token = _Token()
    observed: list[int] = []

    class Aborting(_Engine):
        def diarize(
            self,
            samples: npt.NDArray[np.float32],
            *,
            num_clusters: int,
            threshold: float,
            progress: sherpa.Progress,
        ) -> Sequence[_Raw]:
            observed.append(progress(1, 10))
            token.cancelled = True
            observed.append(progress(2, 10))
            return []  # what sherpa returns when the callback aborts

    provider, _, _ = _provider(models, Aborting())

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions(), cancellation=token)

    assert failure.value.code == _CODE.CANCELLED
    assert observed == [0, 1]


def test_engine_failure_is_a_typed_path_free_error(models: tuple[Path, Path]) -> None:
    class Broken(_Engine):
        def diarize(
            self,
            samples: npt.NDArray[np.float32],
            *,
            num_clusters: int,
            threshold: float,
            progress: sherpa.Progress,
        ) -> Sequence[_Raw]:
            raise RuntimeError(f"boom at {models[0]}")

    provider, _, _ = _provider(models, Broken())

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions())

    assert failure.value.code == _CODE.PROVIDER_FAILED
    assert str(models[0]) not in failure.value.user_message


def test_load_failure_is_provider_failed(models: tuple[Path, Path]) -> None:
    def factory(seg: Path, emb: Path, threads: int) -> _Engine:
        raise RuntimeError("corrupt model")

    provider = SherpaOnnxDiarizationProvider(
        segmentation_model=models[0], embedding_model=models[1], engine_factory=factory
    )

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions())

    assert failure.value.code == _CODE.PROVIDER_FAILED


_MODELS_DIR = os.environ.get("VOZ_DIARIZATION_E2E_MODELS")
_AUDIO = os.environ.get("VOZ_DIARIZATION_E2E_AUDIO")


@pytest.mark.skipif(
    not (_MODELS_DIR and _AUDIO),
    reason="opt-in: set VOZ_DIARIZATION_E2E_MODELS and VOZ_DIARIZATION_E2E_AUDIO",
)
def test_real_engine_finds_at_least_two_speakers() -> None:
    pytest.importorskip("sherpa_onnx")
    assert _MODELS_DIR and _AUDIO
    root = Path(_MODELS_DIR)
    provider = SherpaOnnxDiarizationProvider(
        segmentation_model=root / "pyannote-segmentation-3-0.onnx",
        embedding_model=root / "wespeaker_en_voxceleb_resnet34_LM.onnx",
    )
    try:
        with Path(_AUDIO).open("rb") as audio:
            result = provider.diarize(audio=audio, options=DiarizationOptions())
    finally:
        provider.close()

    assert len({turn.cluster for turn in result.turns}) >= 2


@pytest.mark.parametrize(
    ("cpus", "expected"),
    [(None, 1), (1, 1), (2, 1), (4, 3), (9, 8), (20, 8), (64, 8)],
)
def test_default_threads_use_all_cores_but_one_up_to_the_measured_cap(
    monkeypatch: pytest.MonkeyPatch, cpus: int | None, expected: int
) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: cpus)

    assert sherpa.default_diarization_threads() == expected


def test_explicit_thread_count_wins_over_the_default(models: tuple[Path, Path]) -> None:
    loads: list[int] = []

    def factory(seg: Path, emb: Path, threads: int) -> _Engine:
        loads.append(threads)
        return _Engine()

    SherpaOnnxDiarizationProvider(
        segmentation_model=models[0],
        embedding_model=models[1],
        num_threads=3,
        engine_factory=factory,
    ).diarize(audio=_wav(), options=DiarizationOptions())

    assert loads == [3]


def test_on_progress_receives_fractions_from_the_engine_callback(
    models: tuple[Path, Path],
) -> None:
    class Reporting(_Engine):
        def diarize(
            self,
            samples: npt.NDArray[np.float32],
            *,
            num_clusters: int,
            threshold: float,
            progress: sherpa.Progress,
        ) -> Sequence[_Raw]:
            for done in (1, 5, 10):
                progress(done, 10)
            return []

    provider, _, _ = _provider(models, Reporting())
    fractions: list[float] = []

    provider.diarize(
        audio=_wav(), options=DiarizationOptions(), on_progress=fractions.append
    )

    assert fractions == [0.1, 0.5, 1.0]


class _ResidualEngine:
    """A teacher of 60 s and a 1 s stray voice that clustering called a speaker."""

    def diarize(
        self,
        samples: npt.NDArray[np.float32],
        *,
        num_clusters: int,
        threshold: float,
        progress: sherpa.Progress,
    ) -> Sequence[_Raw]:
        del samples, num_clusters, threshold, progress
        return [_Raw(0.0, 60.0, 0), _Raw(61.0, 62.0, 1)]


def test_residual_speakers_are_folded_unless_a_count_is_demanded(
    models: tuple[Path, Path],
) -> None:
    def clusters(hint: SpeakerCountHint, merge: bool = True) -> int:
        provider = SherpaOnnxDiarizationProvider(
            segmentation_model=models[0],
            embedding_model=models[1],
            engine_factory=lambda seg, emb, threads: _ResidualEngine(),
            merge_residual=merge,
        )
        return len(
            {
                t.cluster
                for t in provider.diarize(
                    audio=_wav(), options=DiarizationOptions(hint)
                ).turns
            }
        )

    assert clusters(SpeakerCountHint()) == 1
    assert clusters(SpeakerCountHint(), merge=False) == 2
    assert clusters(SpeakerCountHint(minimum=2)) == 2


_FAKE_CHILD = """
import sys
data = sys.stdin.buffer.read(int(sys.argv[6]) * 4)
assert len(data) == int(sys.argv[6]) * 4
mode = sys.argv[7]
print("native log noise", flush=True)
if mode == "hang":
    import time
    time.sleep(60)
if mode == "crash":
    sys.exit(3)
print("VOZ P 1 2", flush=True)
print("VOZ P 2 2", flush=True)
print("VOZ R 0.0 2.5 0")
print("VOZ R 3.0 4.0 1")
print("VOZ END", flush=True)
"""


def _child_provider(
    monkeypatch: pytest.MonkeyPatch, models: tuple[Path, Path], mode: str
) -> SherpaOnnxDiarizationProvider:
    """The real child-process engine, with a fake worker speaking its protocol."""
    import subprocess
    import sys

    real_popen = subprocess.Popen

    def popen(command: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
        # Patching ``sherpa.subprocess`` patches the module for everyone: other
        # spawns (``taskkill`` from ``kill_tree`` on Windows) must stay real.
        if command[1:3] != ["-m", "voz.infrastructure.diarization.worker"]:
            return real_popen(command, **kwargs)
        assert "env" in kwargs and "start_new_session" in kwargs
        return real_popen(
            [sys.executable, "-c", _FAKE_CHILD, *command[3:], mode], **kwargs
        )

    monkeypatch.setattr(sherpa.subprocess, "Popen", popen)
    real_import = sherpa.importlib.import_module

    def fake_import(name: str) -> object:
        return object() if name == "sherpa_onnx" else real_import(name)

    monkeypatch.setattr(sherpa.importlib, "import_module", fake_import)
    return SherpaOnnxDiarizationProvider(
        segmentation_model=models[0], embedding_model=models[1], merge_residual=False
    )


def test_child_engine_streams_progress_and_turns(
    monkeypatch: pytest.MonkeyPatch, models: tuple[Path, Path]
) -> None:
    provider = _child_provider(monkeypatch, models, "ok")
    seen: list[float] = []

    result = provider.diarize(
        audio=_wav(seconds=1), options=DiarizationOptions(), on_progress=seen.append
    )

    assert seen == [0.5, 1.0]
    assert [(t.start_ms, t.end_ms, t.cluster) for t in result.turns] == [
        (0, 2500, "0"),
        (3000, 4000, "1"),
    ]


def test_child_engine_crash_is_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch, models: tuple[Path, Path]
) -> None:
    provider = _child_provider(monkeypatch, models, "crash")

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions())

    assert failure.value.code == _CODE.PROVIDER_FAILED


def test_cancelling_kills_a_silent_child_quickly(
    monkeypatch: pytest.MonkeyPatch, models: tuple[Path, Path]
) -> None:
    import time

    provider = _child_provider(monkeypatch, models, "hang")
    token = _Token()
    threading.Timer(0.5, lambda: setattr(token, "cancelled", True)).start()
    started = time.monotonic()

    with pytest.raises(DiarizationError) as failure:
        provider.diarize(audio=_wav(), options=DiarizationOptions(), cancellation=token)

    assert failure.value.code == _CODE.CANCELLED
    assert time.monotonic() - started < 10
