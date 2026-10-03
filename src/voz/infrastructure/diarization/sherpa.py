"""Local speaker diarization with sherpa-onnx (pyannote segmentation + WeSpeaker).

The runtime is an optional extra (``diarization``): it is imported lazily and a
missing wheel surfaces as ``diarization_runtime_unavailable``. Models are never
downloaded here; callers pass installed paths (see ``models.py``).
"""

from __future__ import annotations

import importlib
import os
import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, BinaryIO, Protocol, cast

from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationOptions,
    DiarizationResult,
    DiarizedTurn,
    SpeakerCountHint,
)
from voz.application.ports.transcription import TranscriptionCancellationToken

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    Samples = npt.NDArray[np.float32]

_Code = DiarizationFailureCode
_SAMPLE_RATE = 16_000
# Measured on real Spanish dialogue: 0.5 merges distinct voices, 0.3 separates
# A/B/A. Over-segmenting is preferable: merging two speakers in the UI is easy.
DEFAULT_THRESHOLD = 0.3
Progress = Callable[[int, int], int]
"""``(processed_chunks, num_chunks)``; a non-zero return aborts the run."""
MAX_DEFAULT_THREADS = 8
"""Measured on 11 min of audio (20-core CPU): 2 threads 147 s, 4 -> 85 s, 8 -> 70 s,
19 -> 79 s. More threads stop paying off (and contend with ASR/the UI)."""


def default_diarization_threads() -> int:
    """All cores but one, capped where adding threads stopped helping."""
    return min(MAX_DEFAULT_THREADS, max(1, (os.cpu_count() or 2) - 1))


class _RawTurn(Protocol):
    start: float
    end: float
    speaker: int


class _Engine(Protocol):
    """Loaded models. ``num_clusters`` -1 means "estimate with the threshold"."""

    def diarize(
        self,
        samples: Samples,
        *,
        num_clusters: int,
        threshold: float,
        progress: Progress,
    ) -> Sequence[_RawTurn]: ...


class _EngineFactory(Protocol):
    def __call__(
        self, segmentation_model: Path, embedding_model: Path, num_threads: int, /
    ) -> _Engine: ...


class _SherpaEngine:
    """Models are loaded once; only the clustering stage changes between runs."""

    def __init__(
        self, module: object, segmentation: Path, embedding: Path, threads: int
    ):
        self._m = module
        self._segmentation = str(segmentation)
        self._embedding = str(embedding)
        self._threads = threads
        self._engine = self._m_attr("OfflineSpeakerDiarization")(
            self._config(-1, DEFAULT_THRESHOLD)
        )

    def _m_attr(self, name: str) -> Callable[..., object]:
        return cast(Callable[..., object], vars(self._m)[name])

    def _config(self, num_clusters: int, threshold: float) -> object:
        segmentation = self._m_attr("OfflineSpeakerSegmentationModelConfig")(
            pyannote=self._m_attr("OfflineSpeakerSegmentationPyannoteModelConfig")(
                model=self._segmentation
            ),
            num_threads=self._threads,
        )
        embedding = self._m_attr("SpeakerEmbeddingExtractorConfig")(
            model=self._embedding, num_threads=self._threads
        )
        clustering = self._m_attr("FastClusteringConfig")(
            num_clusters=num_clusters, threshold=threshold
        )
        return self._m_attr("OfflineSpeakerDiarizationConfig")(
            segmentation=segmentation,
            embedding=embedding,
            clustering=clustering,
            min_duration_on=0.3,
            min_duration_off=0.5,
        )

    def diarize(
        self,
        samples: Samples,
        *,
        num_clusters: int,
        threshold: float,
        progress: Progress,
    ) -> Sequence[_RawTurn]:
        engine = cast(_SherpaPipeline, self._engine)
        engine.set_config(self._config(num_clusters, threshold))  # keeps the models
        return engine.process(samples, progress).sort_by_start_time()


class _SherpaPipeline(Protocol):
    def set_config(self, config: object) -> None: ...

    def process(self, samples: Samples, callback: Progress) -> _SherpaResult: ...


class _SherpaResult(Protocol):
    def sort_by_start_time(self) -> Sequence[_RawTurn]: ...


def _default_engine_factory(
    segmentation_model: Path, embedding_model: Path, num_threads: int
) -> _Engine:
    try:
        module = importlib.import_module("sherpa_onnx")
    except ImportError as error:
        raise DiarizationError(
            _Code.RUNTIME_UNAVAILABLE,
            "The local diarization runtime is not installed.",
        ) from error
    return _SherpaEngine(module, segmentation_model, embedding_model, num_threads)


def _invalid_audio(detail: str) -> DiarizationError:
    return DiarizationError(_Code.INVALID_AUDIO, detail)


def _read_samples(audio: BinaryIO) -> Samples:
    """Decode WAV PCM s16 mono 16 kHz into float32 in [-1, 1)."""
    try:
        numpy = importlib.import_module("numpy")
    except ImportError as error:
        raise DiarizationError(
            _Code.RUNTIME_UNAVAILABLE,
            "The local diarization runtime is not installed.",
        ) from error
    try:
        with wave.open(audio, "rb") as reader:
            if (
                reader.getnchannels() != 1
                or reader.getframerate() != _SAMPLE_RATE
                or reader.getsampwidth() != 2
            ):
                raise _invalid_audio("Audio must be WAV PCM 16-bit mono at 16 kHz.")
            frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as error:
        raise _invalid_audio("Audio must be a readable WAV PCM file.") from error
    if not frames:
        raise _invalid_audio("The audio contains no samples.")
    pcm = numpy.frombuffer(frames, dtype="<i2")
    return cast("Samples", pcm.astype(numpy.float32) / 32768.0)


class SherpaOnnxDiarizationProvider:
    """Map sherpa-onnx speaker turns to canonical ``DiarizationResult``."""

    provider_id = "sherpa-onnx"

    def __init__(
        self,
        *,
        segmentation_model: Path,
        embedding_model: Path,
        threshold: float = DEFAULT_THRESHOLD,
        num_threads: int | None = None,
        engine_factory: _EngineFactory = _default_engine_factory,
    ) -> None:
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        self._segmentation_model = Path(segmentation_model)
        self._embedding_model = Path(embedding_model)
        self._threshold = threshold
        self._num_threads = (
            default_diarization_threads() if num_threads is None else num_threads
        )
        self._engine_factory = engine_factory
        self._engine: _Engine | None = None
        self._lock = RLock()
        self._closed = False

    def close(self) -> None:
        """Wait for the active run, release the models and permanently close."""
        with self._lock:
            self._closed = True
            self._engine = None

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> DiarizationResult:
        """Return acoustic turns for normalized audio; honour the speaker hint.

        ``on_progress`` receives 0..1 while the speaker embeddings are computed
        (the first seconds, loading and segmentation, report nothing). A second
        clustering pass for a speaker-count hint starts again from 0.
        """
        self._raise_if_cancelled(cancellation)
        samples = _read_samples(audio)
        with self._lock:
            if self._closed:
                raise DiarizationError(
                    _Code.PROVIDER_FAILED, "The diarization provider is closed."
                )
            self._raise_if_cancelled(cancellation)
            engine = self._engine_for()

            def run(num_clusters: int) -> list[DiarizedTurn]:
                return self._run(
                    engine, samples, num_clusters, cancellation, on_progress
                )

            return DiarizationResult(turns=tuple(_solve(run, options.speakers)))

    def _engine_for(self) -> _Engine:
        if self._engine is None:
            for model in (self._segmentation_model, self._embedding_model):
                if not model.is_file():
                    raise DiarizationError(
                        _Code.MODEL_UNAVAILABLE,
                        "The local diarization models are not installed.",
                    )
            try:
                self._engine = self._engine_factory(
                    self._segmentation_model, self._embedding_model, self._num_threads
                )
            except DiarizationError:
                raise
            except Exception as error:
                raise DiarizationError(
                    _Code.PROVIDER_FAILED, "The diarization models could not be loaded."
                ) from error
        return self._engine

    def _run(
        self,
        engine: _Engine,
        samples: Samples,
        num_clusters: int,
        cancellation: TranscriptionCancellationToken | None,
        on_progress: Callable[[float], None] | None = None,
    ) -> list[DiarizedTurn]:
        def progress(done: int, total: int) -> int:
            if cancellation is not None and cancellation.is_cancelled():
                return 1
            if on_progress is not None and total > 0:
                on_progress(min(1.0, done / total))
            return 0

        try:
            raw = engine.diarize(
                samples,
                num_clusters=num_clusters,
                threshold=self._threshold,
                progress=progress,
            )
        except Exception as error:
            self._raise_if_cancelled(cancellation)
            raise DiarizationError(
                _Code.PROVIDER_FAILED, "Speaker diarization failed."
            ) from error
        self._raise_if_cancelled(cancellation)  # an aborted run returns nothing
        turns: list[DiarizedTurn] = []
        for item in raw:
            start, end = round(item.start * 1000), round(item.end * 1000)
            if end > start >= 0:
                turns.append(DiarizedTurn(start, end, str(item.speaker)))
        return sorted(
            turns, key=lambda turn: (turn.start_ms, turn.end_ms, turn.cluster)
        )

    @staticmethod
    def _raise_if_cancelled(
        cancellation: TranscriptionCancellationToken | None,
    ) -> None:
        if cancellation is not None and cancellation.is_cancelled():
            raise DiarizationError(_Code.CANCELLED, "Diarization was cancelled.")


def _solve(
    run: Callable[[int], list[DiarizedTurn]], hint: SpeakerCountHint
) -> list[DiarizedTurn]:
    """Exact -> fixed clusters; auto -> threshold; range -> auto, then clamp."""
    if hint.exact is not None:
        return run(hint.exact)
    turns = run(-1)
    found = len({turn.cluster for turn in turns})
    if hint.minimum is not None and found < hint.minimum:
        return run(hint.minimum)
    if hint.maximum is not None and found > hint.maximum:
        return run(hint.maximum)
    return turns


__all__ = ["DEFAULT_THRESHOLD", "SherpaOnnxDiarizationProvider"]
