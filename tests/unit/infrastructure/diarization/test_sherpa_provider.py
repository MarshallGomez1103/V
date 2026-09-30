"""Sherpa-onnx diarization adapter with an injected fake engine (no models)."""

from __future__ import annotations

import io
import os
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

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
    assert loads == [2]

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
