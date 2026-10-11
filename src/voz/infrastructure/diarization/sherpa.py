"""Local speaker diarization with sherpa-onnx (pyannote segmentation + WeSpeaker).

The runtime is an optional extra (``diarization``): it is imported lazily and a
missing wheel surfaces as ``diarization_runtime_unavailable``. Models are never
downloaded here; callers pass installed paths (see ``models.py``).
"""

from __future__ import annotations

import importlib
import os
import queue
import subprocess
import sys
import threading
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import IO, TYPE_CHECKING, BinaryIO, Protocol, cast

from voz.application.diarization_cleanup import merge_residual_clusters
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
# Measured on a real 1 h 47 min class (teacher + a few students), raw clusters ->
# after folding residual speakers:
#   0.3 -> 11 -> 5  two clusters of 36 % + 33 % (together the 69 % that a single
#                   cluster holds from 0.4 up: the teacher, split in two)
#   0.4 ->  6 -> 3  teacher 69 %, students 27 % + 3.5 %
#   0.45 -> 5 -> 2, 0.5 -> 3 -> 2, 0.6 -> 2 -> 2, 0.7 -> 1 -> 1
# 0.4 keeps the teacher whole plus a third voice; merging two speakers in the UI
# is easy, splitting one is not.
DEFAULT_THRESHOLD = 0.4
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


class SherpaEngine:
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


@dataclass(slots=True)
class _Turn:
    start: float
    end: float
    speaker: int


_POLL_SECONDS = 0.2


def _feed(stdin: IO[bytes], samples: Samples) -> None:
    try:
        stdin.write(memoryview(samples).cast("B"))
        stdin.close()
    except OSError:  # the child died or was killed: the reader reports it
        pass


def _pump(stdout: IO[bytes], lines: queue.Queue[str | None]) -> None:
    for raw in stdout:
        lines.put(raw.decode("utf-8", "replace").rstrip())
    lines.put(None)


class _ChildEngine:
    """One child process per run: its native, GIL-holding call cannot stall VOZ.

    ponytail: the models are reloaded on every run (about a second) instead of
    keeping a warm worker; runs last minutes, so a persistent worker is not worth
    its lifecycle.
    """

    def __init__(self, segmentation: Path, embedding: Path, threads: int) -> None:
        self._segmentation = segmentation
        self._embedding = embedding
        self._threads = threads

    def diarize(
        self,
        samples: Samples,
        *,
        num_clusters: int,
        threshold: float,
        progress: Progress,
    ) -> Sequence[_RawTurn]:
        command = [
            sys.executable,
            "-m",
            "voz.infrastructure.diarization.worker",
            str(self._segmentation),
            str(self._embedding),
            str(self._threads),
            str(num_clusters),
            str(threshold),
            str(len(samples)),
        ]
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows
        )
        assert child.stdin is not None and child.stdout is not None
        lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=_pump, args=(child.stdout, lines), daemon=True).start()
        threading.Thread(target=_feed, args=(child.stdin, samples), daemon=True).start()
        turns: list[_Turn] = []
        finished = False
        try:
            while True:
                try:
                    line = lines.get(timeout=_POLL_SECONDS)
                except queue.Empty:
                    if progress(0, 0):  # idle tick: lets a cancel kill a silent phase
                        return []
                    continue
                if line is None:
                    break
                fields = line.split()
                if len(fields) < 2 or fields[0] != "VOZ":
                    continue  # native log noise
                if fields[1] == "P" and progress(int(fields[2]), int(fields[3])):
                    return []
                if fields[1] == "R":
                    turns.append(
                        _Turn(float(fields[2]), float(fields[3]), int(fields[4]))
                    )
                elif fields[1] == "END":
                    finished = True
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
        if not finished:
            raise RuntimeError("the diarization worker ended without a result")
        return turns


def _default_engine_factory(
    segmentation_model: Path, embedding_model: Path, num_threads: int
) -> _Engine:
    try:
        importlib.import_module("sherpa_onnx")
    except ImportError as error:
        raise DiarizationError(
            _Code.RUNTIME_UNAVAILABLE,
            "The local diarization runtime is not installed.",
        ) from error
    return _ChildEngine(segmentation_model, embedding_model, num_threads)


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
        merge_residual: bool = True,
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
        self._merge_residual = merge_residual
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
        clustering pass for a speaker-count hint starts again from 0. Residual
        clusters (almost no speech) are folded into their nearest neighbour,
        never below the requested exact/minimum count.
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

            turns = _solve(run, options.speakers)
            if self._merge_residual:
                hint = options.speakers
                turns = merge_residual_clusters(
                    turns, keep_at_least=hint.exact or hint.minimum or 1
                )
            return DiarizationResult(turns=tuple(turns))

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
            except Exception as error:  # native loader errors are untyped
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
            # Native engine errors are untyped; an abort via the progress
            # callback surfaces here as cancellation. Else chained, typed.
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
